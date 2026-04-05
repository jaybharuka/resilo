import '@testing-library/jest-dom';
jest.mock('axios');

jest.mock('../services/api', () => ({
  apiService: {
    getRemediationRules: jest.fn(async () => []),
    getRemediationStats: jest.fn(async () => ({ total_attempts: 0, successful_attempts: 0, active_rules: 0, average_execution_time: 0, success_rate: 0 })),
    getSystemData: jest.fn(async () => ({ cpu: 0, memory: 0, disk: 0 })),
    getRemediationIssues: jest.fn(async () => ({ issues: [], metrics: {} })),
    getRemediationHistory: jest.fn(async () => []),
    getAutonomousMode: jest.fn(async () => ({ autonomous_mode: false })),
    getRemediationJobs: jest.fn(async () => []),
    getRemediationJob: jest.fn(async () => ({ job: null, logs: [] })),
    getRemediationJobLogs: jest.fn(async () => []),
    triggerRemediation: jest.fn(async () => ({ success: true, results: [] })),
    setAutonomousMode: jest.fn(async () => ({ autonomous_mode: false })),
    toggleRemediationRule: jest.fn(async () => ({ enabled: true })),
  },
}));

jest.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    login: jest.fn(),
    loading: false,
    authError: null,
    role: 'admin',
  }),
}));

jest.mock('../components/Dashboard', () => () => <div>Dashboard</div>);
jest.mock('../components/RealtimeChat', () => () => <div>Chat</div>);

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Login from '../components/Login';
import Dashboard from '../components/Dashboard';
import RealtimeChat from '../components/RealtimeChat';
import RemediationJobsPanel from '../components/RemediationJobsPanel';

test('renders login screen', () => {
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  );
  expect(screen.getByRole('textbox')).toBeInTheDocument();
});

test('renders dashboard metrics', () => {
  render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>
  );
  expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
});

test('chat input is present', () => {
  render(
    <MemoryRouter>
      <RealtimeChat />
    </MemoryRouter>
  );
  expect(screen.getByText(/chat/i)).toBeInTheDocument();
});

test('remediation jobs panel renders job visibility section', async () => {
  render(
    <MemoryRouter>
      <RemediationJobsPanel />
    </MemoryRouter>
  );

  expect(await screen.findByText(/no remediation jobs queued/i)).toBeInTheDocument();
});
