import { create } from 'zustand';
import { metricsApi, alertsApi, remediationApi, getOrgId } from '../services/resiloApi';

export const useResiloStore = create((set, get) => ({
  metrics: [],         // latest MetricSnapshot per agent
  metricsHistory: [],  // time-series snapshots
  alerts: [],
  remediations: [],
  isLoading: true,
  error: null,
  darkMode: false,

  toggleDarkMode: () => set((state) => ({ darkMode: !state.darkMode })),

  fetchDashboardData: async () => {
    const orgId = getOrgId();
    if (!orgId) {
      // Not logged in yet — keep loading state, don't throw
      return;
    }
    try {
      const [latest, history, alerts, remeds] = await Promise.allSettled([
        metricsApi.getLatest(orgId),
        metricsApi.getHistory(orgId, { limit: 60 }),
        alertsApi.list(orgId),
        remediationApi.list(orgId),
      ]);

      set({
        metrics:        latest.status === 'fulfilled'  ? (latest.value  || []) : [],
        metricsHistory: history.status === 'fulfilled' ? (history.value || []) : [],
        alerts:         alerts.status === 'fulfilled'  ? (alerts.value  || []) : [],
        remediations:   remeds.status === 'fulfilled'  ? (remeds.value  || []) : [],
        isLoading: false,
        error: null,
      });
    } catch (error) {
      set({ error: error.message, isLoading: false });
    }
  },

  // Start a polling loop every 15 seconds for real-time updates
  startPolling: () => {
    get().fetchDashboardData(); // Initial fetch
    const interval = setInterval(() => {
      get().fetchDashboardData();
    }, 15000);
    return () => clearInterval(interval);
  },
}));
