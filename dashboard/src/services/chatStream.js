// Streaming chat client using Socket.IO
import realtime from './realtime';
import { v4 as uuidv4 } from 'uuid';

function getStoredToken() {
  try { return localStorage.getItem('aiops:token') || null; } catch { return null; }
}

class ChatStreamClient {
  constructor() {
    this.listeners = new Map(); // streamId -> { onToken, onDone, onError }
    this.bound = false;
  }

  bindSocket() {
    if (this.bound) return;
    const socket = realtime.getSocket();
    if (!socket) return;
    this.bound = true;
    socket.on('chat:chunk', ({ streamId, token }) => {
      const l = this.listeners.get(streamId);
      if (l?.onToken) l.onToken(token);
    });
    socket.on('chat:done', ({ streamId }) => {
      const l = this.listeners.get(streamId);
      if (l?.onDone) l.onDone();
      this.listeners.delete(streamId);
    });
    socket.on('chat:error', ({ streamId, error }) => {
      const l = this.listeners.get(streamId);
      if (l?.onError) l.onError(error);
      this.listeners.delete(streamId);
    });
  }

  send(message, { onToken, onDone, onError } = {}) {
    const socket = realtime.getSocket();
    if (!socket || socket.disconnected) {
      throw new Error('Streaming unavailable: socket not connected');
    }
    this.bindSocket();
    const streamId = uuidv4();
    this.listeners.set(streamId, { onToken, onDone, onError });
    socket.emit('chat:send', { message, streamId, token: getStoredToken() });
    return {
      streamId,
      cancel: () => {
        try {
          socket.emit('chat:cancel', { streamId });
        } finally {
          this.listeners.delete(streamId);
        }
      },
    };
  }
}

const chatStream = new ChatStreamClient();
export default chatStream;
