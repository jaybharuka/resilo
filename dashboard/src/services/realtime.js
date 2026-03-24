import { io } from 'socket.io-client';
import { API_BASE_URL } from './api';

// Socket base: use REACT_APP_SOCKET_URL, then window.location.origin (same host/port as page),
// then infer from API_BASE_URL host with port 3011 (Express/Socket.IO server)
const inferSocketUrl = () => {
  const env = process.env.REACT_APP_SOCKET_URL;
  if (env) return env;
  try {
    if (typeof window !== 'undefined' && window.location) {
      return window.location.origin; // same host+port as the served page
    }
  } catch {}
  try {
    const u = new URL(API_BASE_URL);
    return `${u.protocol}//${u.hostname}:3011`;
  } catch {
    return 'http://localhost:3011';
  }
};

class RealtimeClient {
  constructor() {
    this.socket = null;
    this.listeners = new Map();
    this.connected = false;
  }

  connect() {
    if (this.socket) return this.socket;
    const url = inferSocketUrl();
    this.socket = io(url, { transports: ['websocket'], autoConnect: true });

    this.socket.on('connect', () => {
      this.connected = true;
    });

    this.socket.on('disconnect', () => {
      this.connected = false;
    });

    return this.socket;
  }

  getSocket() {
    if (!this.socket) {
      return this.connect();
    }
    return this.socket;
  }

  isConnected() {
    const s = this.socket;
    return !!(s && s.connected && !s.disconnected);
  }

  subscribe(event, cb) {
    const s = this.connect();
    s.on(event, cb);

    if (!this.listeners.has(event)) this.listeners.set(event, new Set());
    this.listeners.get(event).add(cb);

    return () => this.unsubscribe(event, cb);
  }

  unsubscribe(event, cb) {
    if (!this.socket) return;
    this.socket.off(event, cb);
    const set = this.listeners.get(event);
    if (set) {
      set.delete(cb);
      if (set.size === 0) this.listeners.delete(event);
    }
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.connected = false;
      this.listeners.clear();
    }
  }
}

export const realtime = new RealtimeClient();
export default realtime;
