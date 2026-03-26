/**
 * browserMetrics.js — Collect system metrics from the user's machine.
 *
 * Strategy (in priority order):
 *   1. Local psutil agent at http://localhost:9090/metrics  (real values)
 *   2. Browser Performance / Navigator APIs                 (estimates)
 *
 * All values are normalised to the same shape as MetricSnapshot so the
 * backend and dashboard can treat them identically.
 */

const LOCAL_AGENT_URL = 'http://localhost:9090/metrics';
const LOCAL_AGENT_TIMEOUT_MS = 1500;

// ── Local agent probe ─────────────────────────────────────────────────────────

let _localAgentAvailable = null;   // null = untested, true/false after first check

async function _tryLocalAgent() {
  try {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), LOCAL_AGENT_TIMEOUT_MS);
    const res = await fetch(LOCAL_AGENT_URL, {
      signal: ctrl.signal,
      cache: 'no-store',
      mode: 'cors',
    });
    clearTimeout(tid);
    if (!res.ok) return null;
    const data = await res.json();
    _localAgentAvailable = true;
    return data;
  } catch {
    _localAgentAvailable = false;
    return null;
  }
}

export function isLocalAgentAvailable() {
  return _localAgentAvailable === true;
}

// ── Browser API estimates ─────────────────────────────────────────────────────

async function _cpuEstimate() {
  // Measure how long a fixed 500k-iteration loop takes.
  // On an idle modern machine this is ~2 ms.
  // Under load it grows; we map the ratio → 0-100%.
  const ITERS = 500_000;
  const BASELINE_MS = 2;

  const t0 = performance.now();
  let x = 0;
  for (let i = 0; i < ITERS; i++) x ^= i;
  void x; // prevent optimisation
  const elapsed = performance.now() - t0;

  const ratio = elapsed / BASELINE_MS;
  // ratio 1 → 0%,  ratio 5 → ~80%,  ratio 10+ → ~100%
  return Math.min(100, Math.max(0, Math.round((ratio - 1) * 12.5)));
}

function _memoryEstimate() {
  // Chrome only: performance.memory (values in bytes)
  const pm = performance.memory;
  if (!pm) return null;
  return Math.round((pm.usedJSHeapSize / pm.jsHeapSizeLimit) * 100);
}

async function _batteryInfo() {
  try {
    const b = await navigator.getBattery?.();
    if (!b) return null;
    return { level: Math.round(b.level * 100), charging: b.charging };
  } catch {
    return null;
  }
}

function _networkInfo() {
  const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (!c) return { network_in: null, network_out: null };
  // downlink is in Mbps; convert to MB/s for consistency with psutil bytes
  const mbps = c.downlink || null;
  return {
    network_in:  mbps ? Math.round(mbps * 125) : null,  // Mbps → KB/s (approx)
    network_out: null,
    effective_type: c.effectiveType || null,
  };
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Collect metrics from the best available source.
 * Returns an object compatible with MetricSnapshot fields.
 */
export async function collectMetrics() {
  // 1. Try local psutil agent for real values
  const local = await _tryLocalAgent();
  if (local) {
    return {
      cpu:         local.cpu         ?? 0,
      memory:      local.memory      ?? 0,
      disk:        local.disk        ?? 0,
      network_in:  local.network_in  ?? 0,
      network_out: local.network_out ?? 0,
      temperature: local.temperature ?? null,
      processes:   local.processes   ?? null,
      uptime_secs: local.uptime_secs ?? null,
      cpu_cores:   local.cpu_cores   ?? navigator.hardwareConcurrency ?? null,
      device_memory_gb: local.device_memory_gb ?? (navigator.deviceMemory || null),
      platform:    local.platform    ?? navigator.platform ?? null,
      source:      'local-agent',
    };
  }

  // 2. Browser estimates
  const [cpuEst, battery, net] = await Promise.all([
    _cpuEstimate(),
    _batteryInfo(),
    Promise.resolve(_networkInfo()),
  ]);

  const memPct = _memoryEstimate();

  return {
    cpu:          cpuEst,
    memory:       memPct,
    disk:         null,
    network_in:   net.network_in,
    network_out:  net.network_out,
    temperature:  null,
    processes:    null,
    uptime_secs:  null,
    cpu_cores:    navigator.hardwareConcurrency ?? null,
    device_memory_gb: navigator.deviceMemory   ?? null,
    platform:     navigator.platform           ?? null,
    battery:      battery,
    effective_type: net.effective_type          ?? null,
    source:       'browser',
  };
}

// ── Continuous push loop ──────────────────────────────────────────────────────

let _stopLoop = null;

/**
 * Start sending metrics to the backend every `intervalMs` ms.
 * Returns a stop function.
 */
export function startMetricsPush(pushFn, intervalMs = 10_000) {
  let active = true;
  _stopLoop = () => { active = false; };

  async function loop() {
    while (active) {
      try {
        const metrics = await collectMetrics();
        // Skip pure browser-API estimates with no real signal — they store zeros
        // in the DB and pollute the dashboard. Local-agent data is always pushed.
        const hasRealData = metrics.source === 'local-agent' || metrics.cpu > 0 || metrics.memory > 0;
        if (hasRealData) await pushFn(metrics);
      } catch { /* swallow — network issues are expected */ }
      await new Promise(r => setTimeout(r, intervalMs));
    }
  }

  loop();
  return _stopLoop;
}

export function stopMetricsPush() {
  _stopLoop?.();
  _stopLoop = null;
}
