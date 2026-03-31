"""
notification_service.py — Multi-channel notification dispatcher for Resilo AIOps

Supports:
    - Email     via SMTP (TLS/STARTTLS)
    - Slack     via Incoming Webhooks
    - Telegram  via Bot API

Entry points (called by anomaly_engine.py):
    dispatch_alert_notification(db, org_id, alert, agent_label)
    dispatch_daily_summary(db, org_id)
    send_test_notification(channel) → {ok, error?}

Environment variable defaults (overridden per-channel via config JSON):
    SMTP_HOST       smtp.gmail.com
    SMTP_PORT       587
    SMTP_USER       (empty — must be set for email to work)
    SMTP_PASSWORD   (empty)
    SMTP_FROM       (falls back to SMTP_USER)
    DAILY_SUMMARY_HOUR   8   (UTC hour to send daily digest)
"""

import asyncio
import logging
import os
import smtplib
import ssl
import uuid
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiohttp
from sqlalchemy import select
from sqlalchemy import func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import or_

from database import (
    SessionLocal, Organization, Agent, User,
    MetricSnapshot, AlertRecord,
    NotificationChannel, NotificationLog,
)

log = logging.getLogger("notification_service")

# ── Environment defaults ───────────────────────────────────────────────────────

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", "") or SMTP_USER
DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "8"))

# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────

async def dispatch_alert_notification(
    db: AsyncSession,
    org_id: str,
    alert: AlertRecord,
    agent_label: str,
) -> None:
    """
    Send alert notifications to the right people:
      1. The device owner's personal channels (agent.owner_user_id / alert.owner_user_id)
      2. Every admin's personal channels in the org
      3. Org-wide channels (user_id IS NULL)

    Channels are filtered per-channel severity list before dispatch.
    Runs all dispatches concurrently; logs each attempt.
    """
    # ── Compute target user IDs (owner + all admins) ─────────────────────────
    target_user_ids: set[str] = set()

    # Device owner from the alert record (set at alert creation time)
    if alert.owner_user_id:
        target_user_ids.add(alert.owner_user_id)

    # Fallback: look up current owner from the agent row (handles manual alerts)
    if alert.agent_id:
        agent_r = await db.execute(select(Agent).where(Agent.id == alert.agent_id))
        ag = agent_r.scalar_one_or_none()
        if ag and ag.owner_user_id:
            target_user_ids.add(ag.owner_user_id)

    # All active admins in the org
    admin_r = await db.execute(
        select(User).where(
            User.org_id == org_id,
            User.role == "admin",
            User.is_active == True,
        )
    )
    for admin in admin_r.scalars().all():
        target_user_ids.add(admin.id)

    # ── Fetch relevant channels ───────────────────────────────────────────────
    # Include: org-wide (user_id IS NULL) + target users' personal channels
    chan_q = select(NotificationChannel).where(
        NotificationChannel.org_id == org_id,
        NotificationChannel.enabled == True,
    )
    if target_user_ids:
        chan_q = chan_q.where(
            or_(
                NotificationChannel.user_id == None,  # noqa: E711
                NotificationChannel.user_id.in_(target_user_ids),
            )
        )

    channels_result = await db.execute(chan_q)
    channels = list(channels_result.scalars().all())
    if not channels:
        return

    subject, html_body, plain_body = _build_alert_message(alert, agent_label)

    tasks = []
    for ch in channels:
        # Respect per-channel severity filter (default: critical + high)
        allowed = ch.severities or ["critical", "high"]
        if alert.severity not in allowed:
            continue
        tasks.append(
            _dispatch_to_channel(db, ch, alert.id, subject, html_body, plain_body, org_id)
        )

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log.error("Notification gather error: %s", r)


async def dispatch_daily_summary(db: AsyncSession, org_id: str) -> None:
    """Build and send the daily summary report for an org to all enabled channels."""
    summary = await _build_daily_summary(db, org_id)

    channels_result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.org_id == org_id,
            NotificationChannel.enabled == True,
        )
    )
    channels = list(channels_result.scalars().all())
    if not channels:
        return

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject   = f"Daily Operations Summary — {date_str}"
    html_body = _render_summary_html(summary)
    plain_body = _render_summary_plain(summary)

    tasks = [
        _dispatch_to_channel(
            db, ch, None, subject, html_body, plain_body, org_id,
            notification_type="summary",
        )
        for ch in channels
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def send_test_notification(channel: NotificationChannel) -> dict:
    """Send a test message to verify a channel is reachable. Returns {ok, error?}."""
    subject    = "Test Notification — Resilo AIOps"
    html_body  = (
        "<p>This is a <strong>test notification</strong> from <strong>Resilo AIOps</strong>. "
        "Your channel is configured correctly.</p>"
    )
    plain_body = "Test notification from Resilo AIOps. Your channel is configured correctly."
    try:
        await _send_to_channel(channel, subject, html_body, plain_body)
        return {"ok": True}
    except Exception as exc:
        log.warning("Test notification failed (channel=%s): %s", channel.id[:8], exc)
        return {"ok": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Internal: channel dispatch + persistence
# ─────────────────────────────────────────────────────────────────────────────

async def _dispatch_to_channel(
    db: AsyncSession,
    channel: NotificationChannel,
    alert_id: Optional[str],
    subject: str,
    html_body: str,
    plain_body: str,
    org_id: str,
    notification_type: str = "alert",
) -> None:
    recipient = _get_recipient_hint(channel)
    status    = "sent"
    error_msg = None

    try:
        await _send_to_channel(channel, subject, html_body, plain_body)
        log.info(
            "Notification sent: org=%s channel=%s type=%s",
            org_id[:8], channel.channel_type, notification_type,
        )
    except Exception as exc:
        status    = "failed"
        error_msg = str(exc)
        log.error(
            "Notification failed: org=%s channel=%s error=%s",
            org_id[:8], channel.channel_type, exc,
        )

    db.add(NotificationLog(
        id=str(uuid.uuid4()),
        org_id=org_id,
        alert_id=alert_id,
        channel_id=channel.id,
        channel_type=channel.channel_type,
        notification_type=notification_type,
        recipient=recipient,
        subject=subject,
        status=status,
        error=error_msg,
    ))
    await db.commit()


async def _send_to_channel(
    channel: NotificationChannel,
    subject: str,
    html_body: str,
    plain_body: str,
) -> None:
    t   = channel.channel_type
    cfg = channel.config or {}

    if t == "email":
        await _send_email(
            to=cfg["email"],
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
            smtp_host=cfg.get("smtp_host", SMTP_HOST),
            smtp_port=int(cfg.get("smtp_port", SMTP_PORT)),
            smtp_user=cfg.get("smtp_user", SMTP_USER),
            smtp_password=cfg.get("smtp_password", SMTP_PASSWORD),
            from_addr=cfg.get("smtp_from", SMTP_FROM),
        )
    elif t == "slack":
        await _send_slack(
            webhook_url=cfg["webhook_url"],
            subject=subject,
            plain_body=plain_body,
        )
    elif t == "telegram":
        await _send_telegram(
            bot_token=cfg["bot_token"],
            chat_id=str(cfg["chat_id"]),
            text=f"*{subject}*\n\n{plain_body}",
        )
    else:
        raise ValueError(f"Unknown channel type: {t!r}")


def _get_recipient_hint(channel: NotificationChannel) -> Optional[str]:
    cfg = channel.config or {}
    if channel.channel_type == "email":
        return cfg.get("email")
    if channel.channel_type == "telegram":
        return str(cfg.get("chat_id", ""))
    if channel.channel_type == "slack":
        url = cfg.get("webhook_url", "")
        return (url[:40] + "…") if len(url) > 40 else url
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Transport implementations
# ─────────────────────────────────────────────────────────────────────────────

async def _send_email(
    to: str,
    subject: str,
    html_body: str,
    plain_body: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_addr: str,
) -> None:
    """Send via SMTP with STARTTLS. Blocks in thread-pool to avoid stalling the event loop."""
    def _sync_send():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr or smtp_user
        msg["To"]      = to
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body,  "html",  "utf-8"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as srv:
            srv.ehlo()
            srv.starttls(context=ctx)
            srv.login(smtp_user, smtp_password)
            srv.sendmail(from_addr or smtp_user, to, msg.as_string())

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync_send)


async def _send_slack(webhook_url: str, subject: str, plain_body: str) -> None:
    """POST Slack Block Kit message to an Incoming Webhook URL."""
    payload = {
        "text": subject,  # fallback for notifications
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": subject[:150], "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": plain_body[:2900]},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "_Resilo AIOps automated notification_"},
                ],
            },
        ],
    }
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(webhook_url, json=payload) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(f"Slack HTTP {resp.status}: {body[:200]}")


async def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    """Send a message via Telegram Bot API sendMessage."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": "Markdown",
    }
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API error: {data.get('description', 'unknown')}")


# ─────────────────────────────────────────────────────────────────────────────
# Message builders
# ─────────────────────────────────────────────────────────────────────────────

_SEVERITY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
    "info":     "ℹ️",
}

_SEVERITY_COLOR = {
    "critical": "#dc2626",
    "high":     "#ea580c",
    "medium":   "#ca8a04",
    "low":      "#16a34a",
    "info":     "#2563eb",
}


def _build_alert_message(
    alert: AlertRecord, agent_label: str
) -> tuple[str, str, str]:
    """Returns (subject, html_body, plain_body) for an alert notification."""
    emoji = _SEVERITY_EMOJI.get(alert.severity, "⚠️")
    color = _SEVERITY_COLOR.get(alert.severity, "#374151")
    ts    = (
        alert.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        if alert.created_at else "unknown"
    )
    subject = f"{emoji} [{alert.severity.upper()}] {alert.title}"

    plain_body = (
        f"Alert:        {alert.title}\n"
        f"System:       {agent_label}\n"
        f"Severity:     {alert.severity.upper()}\n"
        f"Category:     {alert.category.upper()}\n"
        f"Metric Value: {alert.metric_value:.1f}%\n"
        f"Threshold:    {alert.threshold:.0f}%\n"
        f"Time:         {ts}\n"
        f"Status:       {alert.status.upper()}\n"
        f"\n{alert.detail}"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;font-family:Arial,Helvetica,sans-serif;background:#f3f4f6;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.1);">
    <div style="background:{color};padding:24px 28px;">
      <h2 style="margin:0;color:#fff;font-size:20px;">{emoji} {alert.title}</h2>
      <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:14px;">
        Severity: <strong>{alert.severity.upper()}</strong> &nbsp;·&nbsp; {ts}
      </p>
    </div>
    <div style="padding:24px 28px;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr>
          <td style="padding:10px 12px;color:#6b7280;width:130px;">System</td>
          <td style="padding:10px 12px;font-weight:600;color:#111827;">{agent_label}</td>
        </tr>
        <tr style="background:#f9fafb;">
          <td style="padding:10px 12px;color:#6b7280;">Category</td>
          <td style="padding:10px 12px;">{alert.category.upper()}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">Metric Value</td>
          <td style="padding:10px 12px;font-weight:700;color:{color};">{alert.metric_value:.1f}%</td>
        </tr>
        <tr style="background:#f9fafb;">
          <td style="padding:10px 12px;color:#6b7280;">Threshold</td>
          <td style="padding:10px 12px;">{alert.threshold:.0f}%</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;color:#6b7280;">Status</td>
          <td style="padding:10px 12px;">{alert.status.upper()}</td>
        </tr>
      </table>
      <p style="margin-top:20px;color:#374151;font-size:14px;line-height:1.6;">{alert.detail}</p>
    </div>
    <div style="padding:16px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;">
      Resilo AIOps Platform &nbsp;·&nbsp; Automated alert notification
    </div>
  </div>
</body></html>"""

    return subject, html_body, plain_body


# ─────────────────────────────────────────────────────────────────────────────
# Daily summary builders
# ─────────────────────────────────────────────────────────────────────────────

async def _build_daily_summary(db: AsyncSession, org_id: str) -> dict:
    """Aggregate last-24h metrics and incident counts per agent."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    # Fetch agents once.
    agents_result = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.is_active == True)
    )
    agents = list(agents_result.scalars().all())
    agent_index = {a.id: a for a in agents}

    # Single aggregation query replaces the previous N+1 loop.
    # Uses a time-bounded WHERE so TimescaleDB can skip older chunks entirely.
    metrics_result = await db.execute(
        select(
            MetricSnapshot.agent_id,
            sqlfunc.avg(MetricSnapshot.cpu).label("avg_cpu"),
            sqlfunc.avg(MetricSnapshot.memory).label("avg_memory"),
            sqlfunc.avg(MetricSnapshot.disk).label("avg_disk"),
            sqlfunc.max(MetricSnapshot.uptime_secs).label("max_uptime"),
        )
        .where(
            MetricSnapshot.org_id  == org_id,
            MetricSnapshot.timestamp >= cutoff,
        )
        .group_by(MetricSnapshot.agent_id)
    )
    metrics_by_agent = {row.agent_id: row for row in metrics_result.all()}

    # Single alert-count query for the same window.
    alerts_result = await db.execute(
        select(
            AlertRecord.agent_id,
            sqlfunc.count(AlertRecord.id).label("cnt"),
        ).where(
            AlertRecord.org_id     == org_id,
            AlertRecord.created_at >= cutoff,
        ).group_by(AlertRecord.agent_id)
    )
    alerts_by_agent = {row.agent_id: row.cnt for row in alerts_result.all()}

    agent_summaries = []
    for agent in agents:
        m = metrics_by_agent.get(agent.id)
        agent_summaries.append({
            "label":        agent.label,
            "status":       agent.status,
            "avg_cpu":      round((m.avg_cpu    if m else 0) or 0, 1),
            "avg_memory":   round((m.avg_memory if m else 0) or 0, 1),
            "avg_disk":     round((m.avg_disk   if m else 0) or 0, 1),
            "uptime_hours": round(((m.max_uptime if m else 0) or 0) / 3600, 1),
            "incidents":    alerts_by_agent.get(agent.id, 0),
        })

    total_result = await db.execute(
        select(sqlfunc.count(AlertRecord.id)).where(
            AlertRecord.org_id     == org_id,
            AlertRecord.created_at >= cutoff,
        )
    )
    return {
        "date":             datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "org_id":           org_id,
        "agents":           agent_summaries,
        "total_incidents":  total_result.scalar() or 0,
    }


def _render_summary_plain(summary: dict) -> str:
    lines = [
        f"Daily Operations Summary — {summary['date']}",
        f"Total incidents (24 h): {summary['total_incidents']}",
        "",
        "System breakdown:",
    ]
    for a in summary["agents"]:
        lines.append(
            f"  {a['label']} [{a['status'].upper()}]  "
            f"CPU {a['avg_cpu']}%  MEM {a['avg_memory']}%  "
            f"DISK {a['avg_disk']}%  Uptime {a['uptime_hours']}h  "
            f"Incidents {a['incidents']}"
        )
    lines.append("\nResilo AIOps · Automated daily report")
    return "\n".join(lines)


def _render_summary_html(summary: dict) -> str:
    def _color(val, warn, crit):
        if val >= crit:  return "#dc2626"
        if val >= warn:  return "#ca8a04"
        return "#16a34a"

    rows = ""
    for a in summary["agents"]:
        sc = "#16a34a" if a["status"] == "online" else "#dc2626" if a["status"] == "offline" else "#ca8a04"
        rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">{a['label']}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">
            <span style="color:{sc};font-weight:600;">{a['status'].upper()}</span>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:{_color(a['avg_cpu'],70,85)};">
            {a['avg_cpu']}%
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:{_color(a['avg_memory'],65,80)};">
            {a['avg_memory']}%
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:{_color(a['avg_disk'],70,85)};">
            {a['avg_disk']}%
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">{a['uptime_hours']}h</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">{a['incidents']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;font-family:Arial,Helvetica,sans-serif;background:#f3f4f6;">
  <div style="max-width:720px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.1);">
    <div style="background:#1e40af;padding:24px 28px;">
      <h2 style="margin:0;color:#fff;font-size:22px;">Daily Operations Summary</h2>
      <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:14px;">
        {summary['date']} &nbsp;·&nbsp; {summary['total_incidents']} total incidents in the last 24 h
      </p>
    </div>
    <div style="padding:24px 28px;overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="background:#f1f5f9;">
            <th style="padding:10px 12px;text-align:left;color:#475569;">System</th>
            <th style="padding:10px 12px;text-align:left;color:#475569;">Status</th>
            <th style="padding:10px 12px;text-align:left;color:#475569;">Avg CPU</th>
            <th style="padding:10px 12px;text-align:left;color:#475569;">Avg Mem</th>
            <th style="padding:10px 12px;text-align:left;color:#475569;">Avg Disk</th>
            <th style="padding:10px 12px;text-align:left;color:#475569;">Uptime</th>
            <th style="padding:10px 12px;text-align:left;color:#475569;">Incidents</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <div style="padding:16px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;">
      Resilo AIOps Platform &nbsp;·&nbsp; Automated daily report
    </div>
  </div>
</body></html>"""
