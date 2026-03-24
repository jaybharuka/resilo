/**
 * Threshold utilities — shared between Settings, Dashboard, Security, and Remediation.
 * Values are persisted in localStorage so the user can configure them in Settings.
 */

export const THRESHOLD_KEY = 'aiops:thresholds';

export const THRESHOLD_DEFAULTS = {
  cpu_warn:  75,
  cpu_crit:  90,
  mem_warn:  80,
  mem_crit:  90,
  disk_warn: 80,
  disk_crit: 90,
};

/** Read thresholds from localStorage, falling back to defaults. */
export function getThresholds() {
  try {
    const stored = JSON.parse(localStorage.getItem(THRESHOLD_KEY) || 'null');
    if (stored && typeof stored === 'object') {
      return { ...THRESHOLD_DEFAULTS, ...stored };
    }
  } catch {}
  return { ...THRESHOLD_DEFAULTS };
}

/** Persist thresholds to localStorage. Returns true on success. */
export function saveThresholds(t) {
  try {
    localStorage.setItem(THRESHOLD_KEY, JSON.stringify({ ...THRESHOLD_DEFAULTS, ...t }));
    return true;
  } catch {
    return false;
  }
}

/**
 * Compute the status string for a metric value given current thresholds.
 * @param {'cpu'|'mem'|'disk'} metric
 * @param {number} value  0-100
 * @returns {'critical'|'warning'|'healthy'}
 */
export function metricStatus(metric, value) {
  const t = getThresholds();
  const crit = t[`${metric}_crit`];
  const warn = t[`${metric}_warn`];
  if (value >= crit) return 'critical';
  if (value >= warn) return 'warning';
  return 'healthy';
}
