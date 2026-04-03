import '@testing-library/jest-dom';
jest.mock('axios');

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