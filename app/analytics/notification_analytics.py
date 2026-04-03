#!/usr/bin/env python3
"""
AIOps Notification Analytics Dashboard
Comprehensive analytics for notification delivery, effectiveness, and optimization

Features:
- Delivery tracking and success rates
- Response time analysis
- Channel effectiveness metrics
- Escalation pattern analysis
- User engagement tracking
- Alert fatigue detection
- Performance optimization insights
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, Counter
import statistics
import sqlite3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('notification_analytics')

class NotificationStatus(Enum):
    """Notification delivery status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    EXPIRED = "expired"

class ChannelType(Enum):
    """Notification channel types"""
    DISCORD = "discord"
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    PUSH = "push"

class AnalyticsEvent(Enum):
    """Analytics event types"""
    NOTIFICATION_SENT = "notification_sent"
    NOTIFICATION_DELIVERED = "notification_delivered"
    NOTIFICATION_READ = "notification_read"
    NOTIFICATION_ACKNOWLEDGED = "notification_acknowledged"
    NOTIFICATION_FAILED = "notification_failed"
    USER_RESPONSE = "user_response"
    ESCALATION_TRIGGERED = "escalation_triggered"
    CHANNEL_CHANGED = "channel_changed"

@dataclass
class NotificationEvent:
    """Individual notification event"""
    event_id: str
    notification_id: str
    event_type: AnalyticsEvent
    channel: ChannelType
    timestamp: datetime
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    response_time_ms: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None

@dataclass
class NotificationRecord:
    """Complete notification record"""
    notification_id: str
    alert_id: str
    title: str
    severity: str
    channel: ChannelType
    recipients: List[str]
    sent_at: datetime
    status: NotificationStatus
    events: List[NotificationEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Timing metrics
    delivery_time_ms: Optional[int] = None
    read_time_ms: Optional[int] = None
    acknowledgment_time_ms: Optional[int] = None
    total_response_time_ms: Optional[int] = None

@dataclass
class ChannelMetrics:
    """Channel performance metrics"""
    channel: ChannelType
    total_sent: int = 0
    total_delivered: int = 0
    total_read: int = 0
    total_acknowledged: int = 0
    total_failed: int = 0
    
    # Rates (percentages)
    delivery_rate: float = 0.0
    read_rate: float = 0.0
    acknowledgment_rate: float = 0.0
    failure_rate: float = 0.0
    
    # Timing metrics (milliseconds)
    avg_delivery_time: float = 0.0
    avg_read_time: float = 0.0
    avg_acknowledgment_time: float = 0.0
    
    # Additional metrics
    peak_hour: int = 12  # Hour with most activity
    response_distribution: Dict[str, int] = field(default_factory=dict)
    user_engagement_score: float = 0.0

@dataclass
class UserMetrics:
    """User engagement metrics"""
    user_id: str
    total_notifications: int = 0
    read_notifications: int = 0
    acknowledged_notifications: int = 0
    avg_response_time_ms: float = 0.0
    preferred_channel: Optional[ChannelType] = None
    engagement_score: float = 0.0
    alert_fatigue_score: float = 0.0  # 0-100, higher = more fatigued
    last_activity: Optional[datetime] = None

class NotificationAnalytics:
    """Main analytics engine"""
    
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = None
        self.notifications = {}  # notification_id -> NotificationRecord
        self.events = []  # All events for analysis
        
        # Metrics caches
        self.channel_metrics = {}
        self.user_metrics = {}
        self.global_metrics = {}
        
        # Initialize database
        self._init_database()
        
        logger.info("Notification analytics system initialized")
    
    def _init_database(self):
        """Apply schema migrations for the notification analytics SQLite database."""
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _migrations_dir = _os.path.join(
            _here, "..", "..", "migrations", "sqlite", "analytics_notifications"
        )
        try:
            self.conn = sqlite3.connect(self.db_path)
            if self.db_path == ":memory:":
                _sql_file = _os.path.join(_migrations_dir, "001_initial.sql")
                with open(_sql_file, encoding="utf-8") as _f:
                    self.conn.executescript(_f.read())
            else:
                from app.core.sqlite_migrator import run_sqlite_migrations
                run_sqlite_migrations(self.db_path, _migrations_dir)
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    
    def record_notification(self, notification: NotificationRecord):
        """Record a new notification"""
        self.notifications[notification.notification_id] = notification
        
        # Store in database
        if self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO notifications 
                    (notification_id, alert_id, title, severity, channel, recipients, 
                     sent_at, status, delivery_time_ms, read_time_ms, 
                     acknowledgment_time_ms, total_response_time_ms, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    notification.notification_id,
                    notification.alert_id,
                    notification.title,
                    notification.severity,
                    notification.channel.value,
                    json.dumps(notification.recipients),
                    notification.sent_at.isoformat(),
                    notification.status.value,
                    notification.delivery_time_ms,
                    notification.read_time_ms,
                    notification.acknowledgment_time_ms,
                    notification.total_response_time_ms,
                    json.dumps(notification.metadata)
                ))
                self.conn.commit()
            except Exception as e:
                logger.error(f"Failed to store notification {notification.notification_id}: {e}")
        
        logger.info(f"Recorded notification {notification.notification_id} via {notification.channel.value}")
    
    def record_event(self, event: NotificationEvent):
        """Record a notification event"""
        self.events.append(event)
        
        # Update notification record
        if event.notification_id in self.notifications:
            notification = self.notifications[event.notification_id]
            notification.events.append(event)
            
            # Update notification status and timing
            if event.event_type == AnalyticsEvent.NOTIFICATION_DELIVERED:
                notification.status = NotificationStatus.DELIVERED
                if event.response_time_ms:
                    notification.delivery_time_ms = event.response_time_ms
            elif event.event_type == AnalyticsEvent.NOTIFICATION_READ:
                notification.status = NotificationStatus.READ
                if event.response_time_ms:
                    notification.read_time_ms = event.response_time_ms
            elif event.event_type == AnalyticsEvent.NOTIFICATION_ACKNOWLEDGED:
                notification.status = NotificationStatus.ACKNOWLEDGED
                if event.response_time_ms:
                    notification.acknowledgment_time_ms = event.response_time_ms
                    notification.total_response_time_ms = event.response_time_ms
            elif event.event_type == AnalyticsEvent.NOTIFICATION_FAILED:
                notification.status = NotificationStatus.FAILED
        
        # Store in database
        if self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO events 
                    (event_id, notification_id, event_type, channel, timestamp, 
                     user_id, response_time_ms, success, error_message, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event.event_id,
                    event.notification_id,
                    event.event_type.value,
                    event.channel.value,
                    event.timestamp.isoformat(),
                    event.user_id,
                    event.response_time_ms,
                    event.success,
                    event.error_message,
                    json.dumps(event.metadata)
                ))
                self.conn.commit()
            except Exception as e:
                logger.error(f"Failed to store event {event.event_id}: {e}")
        
        logger.debug(f"Recorded event {event.event_type.value} for notification {event.notification_id}")
    
    def calculate_channel_metrics(self, channel: ChannelType, hours: int = 24) -> ChannelMetrics:
        """Calculate metrics for a specific channel"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Filter notifications for this channel within time window
        channel_notifications = [
            n for n in self.notifications.values()
            if n.channel == channel and n.sent_at > cutoff_time
        ]
        
        if not channel_notifications:
            return ChannelMetrics(channel=channel)
        
        metrics = ChannelMetrics(channel=channel)
        metrics.total_sent = len(channel_notifications)
        
        # Count status distribution
        status_counts = Counter(n.status for n in channel_notifications)
        metrics.total_delivered = status_counts.get(NotificationStatus.DELIVERED, 0) + \
                                 status_counts.get(NotificationStatus.READ, 0) + \
                                 status_counts.get(NotificationStatus.ACKNOWLEDGED, 0)
        metrics.total_read = status_counts.get(NotificationStatus.READ, 0) + \
                           status_counts.get(NotificationStatus.ACKNOWLEDGED, 0)
        metrics.total_acknowledged = status_counts.get(NotificationStatus.ACKNOWLEDGED, 0)
        metrics.total_failed = status_counts.get(NotificationStatus.FAILED, 0)
        
        # Calculate rates
        if metrics.total_sent > 0:
            metrics.delivery_rate = (metrics.total_delivered / metrics.total_sent) * 100
            metrics.read_rate = (metrics.total_read / metrics.total_sent) * 100
            metrics.acknowledgment_rate = (metrics.total_acknowledged / metrics.total_sent) * 100
            metrics.failure_rate = (metrics.total_failed / metrics.total_sent) * 100
        
        # Calculate timing metrics
        delivery_times = [n.delivery_time_ms for n in channel_notifications if n.delivery_time_ms]
        read_times = [n.read_time_ms for n in channel_notifications if n.read_time_ms]
        ack_times = [n.acknowledgment_time_ms for n in channel_notifications if n.acknowledgment_time_ms]
        
        if delivery_times:
            metrics.avg_delivery_time = statistics.mean(delivery_times)
        if read_times:
            metrics.avg_read_time = statistics.mean(read_times)
        if ack_times:
            metrics.avg_acknowledgment_time = statistics.mean(ack_times)
        
        # Calculate peak hour
        hour_counts = Counter(n.sent_at.hour for n in channel_notifications)
        if hour_counts:
            metrics.peak_hour = hour_counts.most_common(1)[0][0]
        
        # Calculate user engagement score
        total_possible_engagements = metrics.total_sent * 3  # delivery + read + ack
        actual_engagements = metrics.total_delivered + metrics.total_read + metrics.total_acknowledged
        if total_possible_engagements > 0:
            metrics.user_engagement_score = (actual_engagements / total_possible_engagements) * 100
        
        self.channel_metrics[channel] = metrics
        return metrics
    
    def calculate_user_metrics(self, user_id: str, hours: int = 24) -> UserMetrics:
        """Calculate metrics for a specific user"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Filter events for this user within time window
        user_events = [
            e for e in self.events
            if e.user_id == user_id and e.timestamp > cutoff_time
        ]
        
        metrics = UserMetrics(user_id=user_id)
        
        if not user_events:
            return metrics
        
        # Get user notifications
        user_notification_ids = {e.notification_id for e in user_events}
        user_notifications = [
            n for n in self.notifications.values()
            if n.notification_id in user_notification_ids and user_id in n.recipients
        ]
        
        metrics.total_notifications = len(user_notifications)
        
        # Count engagement types
        read_events = [e for e in user_events if e.event_type == AnalyticsEvent.NOTIFICATION_READ]
        ack_events = [e for e in user_events if e.event_type == AnalyticsEvent.NOTIFICATION_ACKNOWLEDGED]
        
        metrics.read_notifications = len(read_events)
        metrics.acknowledged_notifications = len(ack_events)
        
        # Calculate average response time
        response_times = [e.response_time_ms for e in user_events if e.response_time_ms]
        if response_times:
            metrics.avg_response_time_ms = statistics.mean(response_times)
        
        # Find preferred channel
        channel_counts = Counter(e.channel for e in user_events)
        if channel_counts:
            metrics.preferred_channel = channel_counts.most_common(1)[0][0]
        
        # Calculate engagement score
        if metrics.total_notifications > 0:
            read_rate = metrics.read_notifications / metrics.total_notifications
            ack_rate = metrics.acknowledged_notifications / metrics.total_notifications
            metrics.engagement_score = ((read_rate * 0.6) + (ack_rate * 0.4)) * 100
        
        # Calculate alert fatigue score (simple heuristic)
        recent_notifications = len([n for n in user_notifications if n.sent_at > datetime.now() - timedelta(hours=1)])
        if recent_notifications > 10:
            metrics.alert_fatigue_score = min(100, (recent_notifications - 10) * 10)
        
        # Last activity
        if user_events:
            metrics.last_activity = max(e.timestamp for e in user_events)
        
        self.user_metrics[user_id] = metrics
        return metrics
    
    def calculate_global_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Calculate global analytics metrics"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Filter recent notifications
        recent_notifications = [
            n for n in self.notifications.values()
            if n.sent_at > cutoff_time
        ]
        
        recent_events = [
            e for e in self.events
            if e.timestamp > cutoff_time
        ]
        
        if not recent_notifications:
            return {
                'total_notifications': 0,
                'total_events': 0,
                'timeframe_hours': hours
            }
        
        # Basic counts
        total_notifications = len(recent_notifications)
        total_events = len(recent_events)
        
        # Status distribution
        status_distribution = dict(Counter(n.status for n in recent_notifications))
        
        # Channel distribution
        channel_distribution = dict(Counter(n.channel for n in recent_notifications))
        
        # Severity distribution
        severity_distribution = dict(Counter(n.severity for n in recent_notifications))
        
        # Response time analysis
        response_times = [n.total_response_time_ms for n in recent_notifications if n.total_response_time_ms]
        response_time_stats = {}
        if response_times:
            response_time_stats = {
                'min': min(response_times),
                'max': max(response_times),
                'avg': statistics.mean(response_times),
                'median': statistics.median(response_times),
                'count': len(response_times)
            }
        
        # Hourly distribution
        hourly_distribution = dict(Counter(n.sent_at.hour for n in recent_notifications))
        
        # Calculate overall rates
        total_delivered = sum(1 for n in recent_notifications if n.status in [
            NotificationStatus.DELIVERED, NotificationStatus.READ, NotificationStatus.ACKNOWLEDGED
        ])
        total_read = sum(1 for n in recent_notifications if n.status in [
            NotificationStatus.READ, NotificationStatus.ACKNOWLEDGED
        ])
        total_acknowledged = sum(1 for n in recent_notifications if n.status == NotificationStatus.ACKNOWLEDGED)
        total_failed = sum(1 for n in recent_notifications if n.status == NotificationStatus.FAILED)
        
        overall_rates = {
            'delivery_rate': (total_delivered / total_notifications) * 100 if total_notifications > 0 else 0,
            'read_rate': (total_read / total_notifications) * 100 if total_notifications > 0 else 0,
            'acknowledgment_rate': (total_acknowledged / total_notifications) * 100 if total_notifications > 0 else 0,
            'failure_rate': (total_failed / total_notifications) * 100 if total_notifications > 0 else 0
        }
        
        # Performance metrics
        avg_events_per_notification = total_events / total_notifications if total_notifications > 0 else 0
        
        # Top users by activity
        user_activity = Counter(e.user_id for e in recent_events if e.user_id)
        top_users = dict(user_activity.most_common(5))
        
        metrics = {
            'timeframe_hours': hours,
            'summary': {
                'total_notifications': total_notifications,
                'total_events': total_events,
                'unique_users': len(set(e.user_id for e in recent_events if e.user_id)),
                'avg_events_per_notification': round(avg_events_per_notification, 2)
            },
            'distributions': {
                'status': status_distribution,
                'channel': {k.value: v for k, v in channel_distribution.items()},
                'severity': severity_distribution,
                'hourly': hourly_distribution
            },
            'performance': {
                'overall_rates': overall_rates,
                'response_time_stats': response_time_stats
            },
            'engagement': {
                'top_users': top_users,
                'total_unique_users': len(set(e.user_id for e in recent_events if e.user_id))
            }
        }
        
        self.global_metrics = metrics
        return metrics
    
    def get_optimization_insights(self) -> List[Dict[str, Any]]:
        """Generate optimization insights based on analytics"""
        insights = []
        
        # Analyze channel performance
        channel_metrics = {
            channel: self.calculate_channel_metrics(channel)
            for channel in ChannelType
        }
        
        # Find best performing channel
        best_channel = max(
            channel_metrics.items(),
            key=lambda x: x[1].acknowledgment_rate if x[1].total_sent > 0 else 0
        )
        
        if best_channel[1].total_sent > 0:
            insights.append({
                'type': 'channel_optimization',
                'priority': 'high',
                'title': 'Optimize Channel Usage',
                'description': f'{best_channel[0].value} has the highest acknowledgment rate ({best_channel[1].acknowledgment_rate:.1f}%)',
                'recommendation': f'Consider routing more critical alerts through {best_channel[0].value}',
                'metrics': {
                    'channel': best_channel[0].value,
                    'acknowledgment_rate': best_channel[1].acknowledgment_rate,
                    'total_sent': best_channel[1].total_sent
                }
            })
        
        # Identify slow channels
        slow_channels = [
            (channel, metrics) for channel, metrics in channel_metrics.items()
            if metrics.avg_delivery_time > 5000 and metrics.total_sent > 0  # 5 seconds
        ]
        
        for channel, metrics in slow_channels:
            insights.append({
                'type': 'performance_issue',
                'priority': 'medium',
                'title': 'Slow Channel Performance',
                'description': f'{channel.value} has slow delivery times (avg: {metrics.avg_delivery_time:.0f}ms)',
                'recommendation': f'Investigate {channel.value} configuration and performance',
                'metrics': {
                    'channel': channel.value,
                    'avg_delivery_time': metrics.avg_delivery_time,
                    'delivery_rate': metrics.delivery_rate
                }
            })
        
        # Identify users with alert fatigue
        fatigued_users = []
        for user_id in set(e.user_id for e in self.events if e.user_id):
            user_metrics = self.calculate_user_metrics(user_id)
            if user_metrics.alert_fatigue_score > 50:
                fatigued_users.append((user_id, user_metrics))
        
        if fatigued_users:
            insights.append({
                'type': 'alert_fatigue',
                'priority': 'high',
                'title': 'Alert Fatigue Detected',
                'description': f'{len(fatigued_users)} users showing signs of alert fatigue',
                'recommendation': 'Implement alert filtering or reduce notification frequency for affected users',
                'metrics': {
                    'affected_users': len(fatigued_users),
                    'avg_fatigue_score': statistics.mean(u[1].alert_fatigue_score for u in fatigued_users)
                }
            })
        
        # Check for failed notifications
        global_metrics = self.calculate_global_metrics()
        failure_rate = global_metrics.get('performance', {}).get('overall_rates', {}).get('failure_rate', 0)
        
        if failure_rate > 5:  # More than 5% failure rate
            insights.append({
                'type': 'reliability_issue',
                'priority': 'critical',
                'title': 'High Failure Rate',
                'description': f'Notification failure rate is {failure_rate:.1f}%',
                'recommendation': 'Investigate notification delivery issues and implement retry mechanisms',
                'metrics': {
                    'failure_rate': failure_rate,
                    'total_notifications': global_metrics['summary']['total_notifications']
                }
            })
        
        return insights
    
    def generate_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generate comprehensive analytics report"""
        
        # Calculate all metrics
        global_metrics = self.calculate_global_metrics(hours)
        
        channel_metrics = {}
        for channel in ChannelType:
            metrics = self.calculate_channel_metrics(channel, hours)
            if metrics.total_sent > 0:  # Only include channels with activity
                channel_metrics[channel.value] = {
                    'total_sent': metrics.total_sent,
                    'delivery_rate': metrics.delivery_rate,
                    'read_rate': metrics.read_rate,
                    'acknowledgment_rate': metrics.acknowledgment_rate,
                    'failure_rate': metrics.failure_rate,
                    'avg_delivery_time': metrics.avg_delivery_time,
                    'avg_read_time': metrics.avg_read_time,
                    'avg_acknowledgment_time': metrics.avg_acknowledgment_time,
                    'peak_hour': metrics.peak_hour,
                    'user_engagement_score': metrics.user_engagement_score
                }
        
        # Get optimization insights
        insights = self.get_optimization_insights()
        
        # Generate summary
        summary_text = f"""
        Notification Analytics Report ({hours}h)
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        📊 Summary:
        - Total Notifications: {global_metrics['summary']['total_notifications']}
        - Total Events: {global_metrics['summary']['total_events']}
        - Unique Users: {global_metrics['summary']['unique_users']}
        - Active Channels: {len(channel_metrics)}
        
        🎯 Performance:
        - Delivery Rate: {global_metrics['performance']['overall_rates']['delivery_rate']:.1f}%
        - Read Rate: {global_metrics['performance']['overall_rates']['read_rate']:.1f}%
        - Acknowledgment Rate: {global_metrics['performance']['overall_rates']['acknowledgment_rate']:.1f}%
        - Failure Rate: {global_metrics['performance']['overall_rates']['failure_rate']:.1f}%
        
        💡 Insights: {len(insights)} optimization opportunities identified
        """
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'timeframe_hours': hours,
            'summary': summary_text.strip(),
            'global_metrics': global_metrics,
            'channel_metrics': channel_metrics,
            'optimization_insights': insights,
            'recommendations': [insight['recommendation'] for insight in insights if insight['priority'] in ['high', 'critical']]
        }
        
        return report
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

async def demonstrate_notification_analytics():
    """Demonstrate the notification analytics system"""
    print("AIOps Notification Analytics Dashboard Demo")
    print("=" * 60)
    
    # Initialize analytics
    analytics = NotificationAnalytics()
    
    # Simulate notification data
    print("📊 Generating sample notification data...\n")
    
    base_time = datetime.now() - timedelta(hours=2)
    
    # Sample notifications across different channels
    notifications = [
        # Discord notifications
        NotificationRecord("NOTIF-001", "ALERT-001", "High CPU Usage", "high", ChannelType.DISCORD, 
                         ["user1", "user2"], base_time, NotificationStatus.ACKNOWLEDGED),
        NotificationRecord("NOTIF-002", "ALERT-002", "Memory Warning", "medium", ChannelType.DISCORD, 
                         ["user1"], base_time + timedelta(minutes=5), NotificationStatus.READ),
        NotificationRecord("NOTIF-003", "ALERT-003", "Disk Space", "low", ChannelType.DISCORD, 
                         ["user3"], base_time + timedelta(minutes=10), NotificationStatus.DELIVERED),
        
        # Slack notifications
        NotificationRecord("NOTIF-004", "ALERT-004", "Service Down", "critical", ChannelType.SLACK, 
                         ["user2", "user4"], base_time + timedelta(minutes=15), NotificationStatus.ACKNOWLEDGED),
        NotificationRecord("NOTIF-005", "ALERT-005", "Database Error", "high", ChannelType.SLACK, 
                         ["user1", "user2"], base_time + timedelta(minutes=20), NotificationStatus.READ),
        
        # Email notifications
        NotificationRecord("NOTIF-006", "ALERT-006", "Backup Failed", "medium", ChannelType.EMAIL, 
                         ["user4"], base_time + timedelta(minutes=25), NotificationStatus.SENT),
        NotificationRecord("NOTIF-007", "ALERT-007", "Security Alert", "critical", ChannelType.EMAIL, 
                         ["user1", "user2", "user3"], base_time + timedelta(minutes=30), NotificationStatus.FAILED),
        
        # SMS notifications
        NotificationRecord("NOTIF-008", "ALERT-008", "Critical System", "critical", ChannelType.SMS, 
                         ["user2"], base_time + timedelta(minutes=35), NotificationStatus.ACKNOWLEDGED),
    ]
    
    # Record notifications
    for notification in notifications:
        analytics.record_notification(notification)
    
    # Simulate events for notifications
    events = [
        # Discord events
        NotificationEvent("EVT-001", "NOTIF-001", AnalyticsEvent.NOTIFICATION_DELIVERED, 
                         ChannelType.DISCORD, base_time + timedelta(seconds=30), "user1", {"channel_id": "alerts"}, 500),
        NotificationEvent("EVT-002", "NOTIF-001", AnalyticsEvent.NOTIFICATION_READ, 
                         ChannelType.DISCORD, base_time + timedelta(minutes=2), "user1", {}, 120000),
        NotificationEvent("EVT-003", "NOTIF-001", AnalyticsEvent.NOTIFICATION_ACKNOWLEDGED, 
                         ChannelType.DISCORD, base_time + timedelta(minutes=5), "user1", {}, 300000),
        
        NotificationEvent("EVT-004", "NOTIF-002", AnalyticsEvent.NOTIFICATION_DELIVERED, 
                         ChannelType.DISCORD, base_time + timedelta(minutes=5, seconds=15), "user1", {}, 750),
        NotificationEvent("EVT-005", "NOTIF-002", AnalyticsEvent.NOTIFICATION_READ, 
                         ChannelType.DISCORD, base_time + timedelta(minutes=7), "user1", {}, 105000),
        
        # Slack events
        NotificationEvent("EVT-006", "NOTIF-004", AnalyticsEvent.NOTIFICATION_DELIVERED, 
                         ChannelType.SLACK, base_time + timedelta(minutes=15, seconds=20), "user2", {}, 1200),
        NotificationEvent("EVT-007", "NOTIF-004", AnalyticsEvent.NOTIFICATION_READ, 
                         ChannelType.SLACK, base_time + timedelta(minutes=16), "user2", {}, 40000),
        NotificationEvent("EVT-008", "NOTIF-004", AnalyticsEvent.NOTIFICATION_ACKNOWLEDGED, 
                         ChannelType.SLACK, base_time + timedelta(minutes=18), "user2", {}, 180000),
        
        # Failed event
        NotificationEvent("EVT-009", "NOTIF-007", AnalyticsEvent.NOTIFICATION_FAILED, 
                         ChannelType.EMAIL, base_time + timedelta(minutes=30, seconds=30), None, 
                         {"error": "SMTP timeout"}, None, False, "SMTP connection timeout"),
        
        # SMS events
        NotificationEvent("EVT-010", "NOTIF-008", AnalyticsEvent.NOTIFICATION_DELIVERED, 
                         ChannelType.SMS, base_time + timedelta(minutes=35, seconds=10), "user2", {}, 2000),
        NotificationEvent("EVT-011", "NOTIF-008", AnalyticsEvent.NOTIFICATION_ACKNOWLEDGED, 
                         ChannelType.SMS, base_time + timedelta(minutes=37), "user2", {}, 130000),
    ]
    
    # Record events
    for event in events:
        analytics.record_event(event)
    
    print(f"✅ Recorded {len(notifications)} notifications and {len(events)} events\n")
    
    # Display global metrics
    print("🌍 Global Metrics (Last 24 hours):")
    global_metrics = analytics.calculate_global_metrics()
    print(f"  Total Notifications: {global_metrics['summary']['total_notifications']}")
    print(f"  Total Events: {global_metrics['summary']['total_events']}")
    print(f"  Unique Users: {global_metrics['summary']['unique_users']}")
    print(f"  Events per Notification: {global_metrics['summary']['avg_events_per_notification']}")
    
    print(f"\n  📈 Overall Performance:")
    rates = global_metrics['performance']['overall_rates']
    print(f"    Delivery Rate: {rates['delivery_rate']:.1f}%")
    print(f"    Read Rate: {rates['read_rate']:.1f}%")
    print(f"    Acknowledgment Rate: {rates['acknowledgment_rate']:.1f}%")
    print(f"    Failure Rate: {rates['failure_rate']:.1f}%")
    
    # Display channel metrics
    print(f"\n📱 Channel Performance Analysis:")
    for channel in ChannelType:
        metrics = analytics.calculate_channel_metrics(channel)
        if metrics.total_sent > 0:
            print(f"\n  {channel.value.title()} Channel:")
            print(f"    Sent: {metrics.total_sent}")
            print(f"    Delivery Rate: {metrics.delivery_rate:.1f}%")
            print(f"    Read Rate: {metrics.read_rate:.1f}%")
            print(f"    Acknowledgment Rate: {metrics.acknowledgment_rate:.1f}%")
            print(f"    Avg Delivery Time: {metrics.avg_delivery_time:.0f}ms")
            print(f"    Engagement Score: {metrics.user_engagement_score:.1f}%")
            print(f"    Peak Hour: {metrics.peak_hour}:00")
    
    # Display user metrics
    print(f"\n👥 User Engagement Analysis:")
    all_users = set()
    for event in events:
        if event.user_id:
            all_users.add(event.user_id)
    
    for user_id in sorted(all_users):
        metrics = analytics.calculate_user_metrics(user_id)
        print(f"\n  User {user_id}:")
        print(f"    Total Notifications: {metrics.total_notifications}")
        print(f"    Read: {metrics.read_notifications} ({(metrics.read_notifications/metrics.total_notifications*100):.1f}%)")
        print(f"    Acknowledged: {metrics.acknowledged_notifications} ({(metrics.acknowledged_notifications/metrics.total_notifications*100):.1f}%)")
        print(f"    Avg Response Time: {metrics.avg_response_time_ms:.0f}ms")
        print(f"    Preferred Channel: {metrics.preferred_channel.value if metrics.preferred_channel else 'None'}")
        print(f"    Engagement Score: {metrics.engagement_score:.1f}%")
        print(f"    Alert Fatigue Score: {metrics.alert_fatigue_score:.1f}/100")
    
    # Show optimization insights
    print(f"\n💡 Optimization Insights:")
    insights = analytics.get_optimization_insights()
    for i, insight in enumerate(insights, 1):
        priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(insight['priority'], "ℹ️")
        print(f"  {i}. {priority_icon} {insight['title']} ({insight['priority']} priority)")
        print(f"     {insight['description']}")
        print(f"     💡 {insight['recommendation']}")
    
    if not insights:
        print("  ✅ No optimization opportunities identified - system performing well!")
    
    # Generate comprehensive report
    print(f"\n📊 Comprehensive Report:")
    report = analytics.generate_report()
    print(report['summary'])
    
    if report['recommendations']:
        print(f"\n🎯 Top Recommendations:")
        for i, rec in enumerate(report['recommendations'][:3], 1):
            print(f"  {i}. {rec}")
    
    # Display distributions
    print(f"\n📋 Distribution Analysis:")
    distributions = global_metrics['distributions']
    
    print(f"  Status Distribution:")
    for status, count in distributions['status'].items():
        percentage = (count / global_metrics['summary']['total_notifications']) * 100
        print(f"    {status.value}: {count} ({percentage:.1f}%)")
    
    print(f"\n  Channel Distribution:")
    for channel, count in distributions['channel'].items():
        percentage = (count / global_metrics['summary']['total_notifications']) * 100
        print(f"    {channel}: {count} ({percentage:.1f}%)")
    
    print(f"\n  Severity Distribution:")
    for severity, count in distributions['severity'].items():
        percentage = (count / global_metrics['summary']['total_notifications']) * 100
        print(f"    {severity}: {count} ({percentage:.1f}%)")
    
    # Response time analysis
    if global_metrics['performance']['response_time_stats']:
        print(f"\n⏱️ Response Time Analysis:")
        rt_stats = global_metrics['performance']['response_time_stats']
        print(f"  Average: {rt_stats['avg']:.0f}ms")
        print(f"  Median: {rt_stats['median']:.0f}ms")
        print(f"  Min: {rt_stats['min']:.0f}ms")
        print(f"  Max: {rt_stats['max']:.0f}ms")
        print(f"  Sample Size: {rt_stats['count']} notifications")
    
    # Cleanup
    analytics.close()
    
    print(f"\n✅ Notification analytics demonstration completed!")
    print(f"🎯 Key Capabilities:")
    print(f"  • Real-time notification tracking and analytics")
    print(f"  • Channel performance comparison and optimization")
    print(f"  • User engagement and alert fatigue detection")
    print(f"  • Response time analysis and SLA monitoring")
    print(f"  • Automated insights and recommendations")
    print(f"  • Comprehensive reporting and historical analysis")

if __name__ == "__main__":
    asyncio.run(demonstrate_notification_analytics())