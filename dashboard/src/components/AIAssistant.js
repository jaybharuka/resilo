import React, { useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { apiService } from '../services/api';
import chatStream from '../services/chatStream';
import realtime from '../services/realtime';
import { Activity, TrendingUp, Zap, Wrench, Lightbulb, Target, Bot, MessageSquare, Send, Square } from 'lucide-react';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const UI      = { fontFamily: "'Outfit', sans-serif" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };

const quickActions = [
  { label: 'Health Check',          icon: <Activity size={15} />,   action: 'health-check' },
  { label: 'Performance Analysis',  icon: <TrendingUp size={15} />, action: 'performance'  },
  { label: 'Resource Optimization', icon: <Zap size={15} />,        action: 'optimization' },
  { label: 'Troubleshoot Issues',   icon: <Wrench size={15} />,     action: 'troubleshoot' },
];

function isSmallTalk(message) {
  if (!message) return false;
  const msg = String(message).trim().toLowerCase();
  if (!msg) return false;
  const greetings = [
    'hi', 'hey', 'hello', 'hola', 'yo', 'sup', 'good morning', 'good evening', 'good afternoon',
    'how are you', 'how r u', 'how are u', "what's up", 'whats up', 'how is it going', 'how are things',
  ];
  const systemKeywords = ['cpu', 'memory', 'disk', 'performance', 'network', 'error', 'status', 'health'];
  if (systemKeywords.some(k => msg.includes(k))) return false;
  return greetings.some(g => msg === g || msg.includes(g)) && msg.length <= 60;
}

const PANEL = {
  background: 'rgb(22, 20, 16)',
  border: '1px solid rgba(42,40,32,0.9)',
  borderRadius: '12px',
};

/**
 * Convert markdown or mixed markdown/HTML AI responses into clean HTML.
 * Handles: **bold**, *italic*, `code`, # headings, - / * bullet lists,
 * numbered lists, and bare newlines. Leaves existing HTML tags untouched.
 */
function mdToHtml(text) {
  if (!text) return '';
  const t = String(text);

  // If the response is already rich HTML (has block tags), only patch inline markdown
  const hasBlockHtml = /<(ul|ol|li|br|p|h[1-6]|strong|em|div|table)\b/i.test(t);

  if (hasBlockHtml) {
    // Just convert inline markdown that may have leaked through
    return t
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  // Full markdown → HTML conversion
  const lines = t.split('\n');
  const out = [];
  let inList = false;
  let listType = '';

  const flushList = () => {
    if (inList) { out.push(`</${listType}>`); inList = false; listType = ''; }
  };

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Headings
    const h = line.match(/^(#{1,4})\s+(.+)/);
    if (h) {
      flushList();
      const level = Math.min(h[1].length, 4);
      const sizes = ['1.05em','1em','0.95em','0.9em'];
      out.push(`<strong style="font-size:${sizes[level-1]};display:block;margin:0.6em 0 0.2em">${h[2]}</strong>`);
      continue;
    }

    // Unordered bullet
    const ul = line.match(/^[\s]*[-*•]\s+(.+)/);
    if (ul) {
      if (!inList || listType !== 'ul') { flushList(); out.push('<ul>'); inList = true; listType = 'ul'; }
      out.push(`<li>${ul[1]}</li>`);
      continue;
    }

    // Ordered list
    const ol = line.match(/^[\s]*\d+[.)]\s+(.+)/);
    if (ol) {
      if (!inList || listType !== 'ol') { flushList(); out.push('<ol>'); inList = true; listType = 'ol'; }
      out.push(`<li>${ol[1]}</li>`);
      continue;
    }

    flushList();

    // Blank line → spacing
    if (!line.trim()) { out.push('<br>'); continue; }

    // Inline styles
    line = line
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g,     '<em>$1</em>')
      .replace(/`([^`]+)`/g,     '<code>$1</code>');

    out.push(line + '<br>');
  }

  flushList();

  // Collapse 3+ consecutive <br> into two
  return out.join('').replace(/(<br>\s*){3,}/g, '<br><br>');
}

const AIAssistant = () => {
  const [messages, setMessages] = useState([{
    type: 'ai',
    content: "Hello! I'm your Resilo AI Assistant. I can help you analyze system performance, troubleshoot issues, and provide insights. What can I help you with today?",
    timestamp: new Date().toLocaleTimeString(),
  }]);
  const [inputValue, setInputValue]   = useState('');
  const [isTyping, setIsTyping]       = useState(false);
  const [streaming, setStreaming]     = useState(false);
  const partialRef  = useRef('');
  const cancelRef   = useRef(null);
  const bottomRef   = useRef(null);

  const scrollToBottom = () =>
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);

  const handleSendMessage = async (message = inputValue) => {
    if (!message.trim()) return;

    const userMessage = { type: 'user', content: message, timestamp: new Date().toLocaleTimeString() };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    scrollToBottom();

    const sock = (() => { try { return realtime.getSocket(); } catch { return null; } })();
    const smallTalk = isSmallTalk(message);

    if (sock && !sock.disconnected && !smallTalk) {
      setStreaming(true);
      setIsTyping(false);
      partialRef.current = '';
      // Push a placeholder immediately so there's no blank gap
      setMessages(prev => [...prev, { type: 'ai', content: '', streaming: true, timestamp: new Date().toLocaleTimeString() }]);
      try {
        const handle = chatStream.send(message, {
          onToken: (t) => {
            partialRef.current += t;
            setMessages(prev => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last?.streaming) {
                copy[copy.length - 1] = { ...last, content: partialRef.current };
              }
              return copy;
            });
            scrollToBottom();
          },
          onDone: () => {
            setStreaming(false);
            cancelRef.current = null;
            setMessages(prev => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last?.streaming) {
                copy[copy.length - 1] = { type: 'ai', content: partialRef.current, timestamp: new Date().toLocaleTimeString() };
              }
              return copy;
            });
          },
          onError: (err) => {
            setStreaming(false);
            cancelRef.current = null;
            setMessages(prev => {
              const copy = [...prev];
              // Replace placeholder with error
              if (copy[copy.length - 1]?.streaming) copy.pop();
              return [...copy, { type: 'ai', content: `Error: ${err}`, timestamp: new Date().toLocaleTimeString() }];
            });
          },
        });
        cancelRef.current = handle;
        return;
      } catch { setStreaming(false); }
    }

    setIsTyping(true);
    try {
      const res = await apiService.sendChatMessage(message, smallTalk ? { expect_small_talk: true } : {});
      const botText       = res?.response || 'No response received.';
      const smallTalkFlag = !!res?.small_talk || smallTalk;
      const metrics       = res?.small_talk_metrics || null;
      setMessages(prev => [...prev, {
        type: 'ai', content: botText,
        timestamp: new Date().toLocaleTimeString(),
        smallTalk: smallTalkFlag, metrics,
      }]);
      scrollToBottom();
    } catch {
      setMessages(prev => [...prev, {
        type: 'ai', content: 'Chat service unavailable.',
        timestamp: new Date().toLocaleTimeString(),
      }]);
    } finally { setIsTyping(false); }
  };

  const handleQuickAction = (action) => {
    const msgs = {
      'health-check': 'Please run a comprehensive system health check',
      'performance':  'Analyze my system performance and identify bottlenecks',
      'optimization': 'Help me optimize my system resources',
      'troubleshoot': "I'm experiencing system issues, help me troubleshoot",
    };
    handleSendMessage(msgs[action]);
  };

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* Page header */}
      <div>
        <h1 style={{ ...DISPLAY, fontSize: '2.2rem', letterSpacing: '0.06em', color: '#F5F0E8', margin: 0, lineHeight: 1 }}>
          AI Assistant
        </h1>
        <p style={{ ...MONO, fontSize: '11px', letterSpacing: '0.1em', color: '#4A443D', marginTop: '6px' }}>
          INTELLIGENT SYSTEM MONITORING & OPTIMIZATION
        </p>
      </div>

      {/* Quick action cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {quickActions.map((action, i) => (
          <button
            key={i}
            onClick={() => handleQuickAction(action.action)}
            style={{
              ...PANEL,
              padding: '16px',
              textAlign: 'left',
              cursor: 'pointer',
              border: '1px solid rgba(42,40,32,0.9)',
              transition: 'border-color 0.15s, background 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'rgba(245,158,11,0.35)';
              e.currentTarget.style.background = 'rgba(245,158,11,0.04)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'rgba(42,40,32,0.9)';
              e.currentTarget.style.background = 'rgb(22,20,16)';
            }}
          >
            <div style={{ color: '#4A443D', marginBottom: '10px', transition: 'color 0.15s' }}
              ref={el => {
                if (el) {
                  el.parentElement.addEventListener('mouseenter', () => { el.style.color = '#F59E0B'; });
                  el.parentElement.addEventListener('mouseleave', () => { el.style.color = '#4A443D'; });
                }
              }}
            >
              {action.icon}
            </div>
            <div style={{ ...UI, fontSize: '13px', color: '#6B6357', fontWeight: 500 }}>{action.label}</div>
          </button>
        ))}
      </div>

      {/* Chat window */}
      <div style={{ ...PANEL, display: 'flex', flexDirection: 'column', height: '32rem', boxShadow: '0 4px 24px rgba(0,0,0,0.3)' }}>

        {/* Messages area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {messages.map((message, index) => {
            if (message.type === 'user') {
              return (
                <div key={index} style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <div
                    style={{
                      maxWidth: '70%',
                      padding: '10px 16px',
                      borderRadius: '16px',
                      borderBottomRightRadius: '4px',
                      background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                      boxShadow: '0 2px 12px rgba(245,158,11,0.25)',
                    }}
                  >
                    <p style={{ ...UI, fontSize: '13px', color: '#0C0B09', margin: 0, lineHeight: 1.5 }}>{message.content}</p>
                    <p style={{ ...MONO, fontSize: '10px', color: 'rgba(12,11,9,0.5)', marginTop: '5px', textAlign: 'right' }}>
                      {message.timestamp}
                    </p>
                  </div>
                </div>
              );
            }

            const isSmallTalkMsg = !!message.smallTalk;
            const isStreaming    = !!message.streaming;
            const bubbleBorder   = isSmallTalkMsg
              ? '1px solid rgba(45,212,191,0.2)'
              : '1px solid rgba(42,40,32,0.9)';
            const bubbleBorderLeft = isSmallTalkMsg ? '3px solid #2DD4BF' : '3px solid rgba(42,40,32,0.9)';
            const avatarBg = isSmallTalkMsg ? 'rgba(45,212,191,0.1)' : 'rgba(245,158,11,0.1)';
            const avatarColor = isSmallTalkMsg ? '#2DD4BF' : '#F59E0B';

            return (
              <div key={index} style={{ display: 'flex', justifyContent: 'flex-start', gap: '10px', alignItems: 'flex-start' }}>
                {/* Avatar */}
                <div style={{
                  width: '26px', height: '26px', borderRadius: '50%',
                  background: avatarBg, border: `1px solid ${avatarColor}30`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, marginTop: '2px',
                }}>
                  {isSmallTalkMsg
                    ? <MessageSquare size={11} color={avatarColor} />
                    : <Bot size={11} color={avatarColor} />
                  }
                </div>

                {/* Bubble */}
                <div style={{
                  maxWidth: '75%',
                  padding: '10px 14px',
                  borderRadius: '14px',
                  borderBottomLeftRadius: '4px',
                  background: 'rgb(31,29,24)',
                  border: bubbleBorder,
                  borderLeft: bubbleBorderLeft,
                }}>
                  {isSmallTalkMsg && (
                    <div style={{ ...MONO, fontSize: '9px', letterSpacing: '0.12em', color: '#2DD4BF', marginBottom: '6px' }}>
                      CONVERSATIONAL
                    </div>
                  )}
                  {message.metrics && (
                    <div style={{ display: 'flex', gap: '12px', marginBottom: '6px', flexWrap: 'wrap' }}>
                      {typeof message.metrics.cpu    === 'number' && <MetricPill label="CPU"  value={`${message.metrics.cpu.toFixed(1)}%`} />}
                      {typeof message.metrics.memory === 'number' && <MetricPill label="MEM"  value={`${message.metrics.memory.toFixed(1)}%`} />}
                      {typeof message.metrics.disk   === 'number' && <MetricPill label="DISK" value={`${message.metrics.disk.toFixed(1)}%`} />}
                    </div>
                  )}
                  <div
                    className="prose"
                    style={{ ...UI, fontSize: '13px', color: '#A89F8C', lineHeight: 1.6 }}
                    dangerouslySetInnerHTML={{
                      __html: DOMPurify.sanitize(
                        mdToHtml(
                          isSmallTalkMsg
                            ? String(message.content || '').replace(/Current snapshot:[^<]*<br>?/i, '').trim()
                            : String(message.content || '')
                        )
                      ),
                    }}
                  />
                  {isStreaming && (
                    <span style={{ display: 'inline-block', width: '2px', height: '13px', background: '#F59E0B', marginLeft: '2px', verticalAlign: 'middle', animation: 'pulse 0.8s infinite' }} />
                  )}
                  <p style={{ ...MONO, fontSize: '10px', color: '#3A342D', marginTop: '5px' }}>
                    {message.timestamp}
                    {isStreaming && <span style={{ color: '#F59E0B', marginLeft: '6px' }}>streaming…</span>}
                  </p>
                </div>
              </div>
            );
          })}

          {/* Typing indicator (HTTP fallback) */}
          {isTyping && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              <div style={{
                width: '26px', height: '26px', borderRadius: '50%',
                background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
              }}>
                <Bot size={11} color="#F59E0B" />
              </div>
              <div style={{
                padding: '12px 16px',
                borderRadius: '14px', borderBottomLeftRadius: '4px',
                background: 'rgb(31,29,24)',
                border: '1px solid rgba(42,40,32,0.9)',
                borderLeft: '3px solid rgba(42,40,32,0.9)',
                display: 'flex', gap: '5px', alignItems: 'center',
              }}>
                {[0, 0.18, 0.36].map((delay, i) => (
                  <span key={i} style={{
                    width: '5px', height: '5px', borderRadius: '50%',
                    background: '#F59E0B', display: 'inline-block',
                    animation: 'bounce 1.2s infinite',
                    animationDelay: `${delay}s`,
                    opacity: 0.7,
                  }} />
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input row */}
        <div style={{
          borderTop: '1px solid rgba(42,40,32,0.9)',
          padding: '12px 14px',
          display: 'flex',
          gap: '10px',
          alignItems: 'center',
        }}>
          <input
            type="text"
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
            placeholder="Ask anything about your system…"
            style={{
              flex: 1,
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(42,40,32,0.9)',
              borderRadius: '8px',
              padding: '9px 14px',
              ...UI,
              fontSize: '13px',
              color: '#F5F0E8',
              outline: 'none',
              transition: 'border-color 0.15s, box-shadow 0.15s',
            }}
            onFocus={e => {
              e.target.style.borderColor = 'rgba(245,158,11,0.4)';
              e.target.style.boxShadow   = '0 0 0 3px rgba(245,158,11,0.07)';
            }}
            onBlur={e => {
              e.target.style.borderColor = 'rgba(42,40,32,0.9)';
              e.target.style.boxShadow   = 'none';
            }}
          />

          {streaming ? (
            <button
              onClick={() => {
                try { cancelRef.current?.cancel?.(); } finally { setStreaming(false); }
              }}
              title="Stop streaming"
              style={{
                width: '36px', height: '36px', borderRadius: '8px', flexShrink: 0,
                background: 'rgba(248,113,113,0.12)',
                border: '1px solid rgba(248,113,113,0.3)',
                color: '#F87171', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(248,113,113,0.2)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'rgba(248,113,113,0.12)'; }}
            >
              <Square size={13} />
            </button>
          ) : (
            <button
              onClick={() => handleSendMessage()}
              disabled={!inputValue.trim() || isTyping}
              title="Send"
              style={{
                width: '36px', height: '36px', borderRadius: '8px', flexShrink: 0,
                background: (!inputValue.trim() || isTyping)
                  ? 'rgba(42,40,32,0.6)'
                  : 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
                border: 'none',
                color: (!inputValue.trim() || isTyping) ? '#4A443D' : '#0C0B09',
                cursor: (!inputValue.trim() || isTyping) ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.15s',
                boxShadow: (!inputValue.trim() || isTyping) ? 'none' : '0 2px 10px rgba(245,158,11,0.3)',
              }}
            >
              <Send size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Tips & Commands */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Tips */}
        <div style={PANEL}>
          <div style={{ padding: '18px 20px', borderBottom: '1px solid rgba(42,40,32,0.9)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Lightbulb size={13} color="#F59E0B" />
            <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>TIPS & SUGGESTIONS</span>
          </div>
          <ul style={{ margin: 0, padding: '16px 20px', listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {[
              'Ask about specific system metrics or performance issues',
              'Request optimization recommendations',
              'Get help with troubleshooting steps',
              'Learn about system health patterns',
            ].map((tip, i) => (
              <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                <span style={{ color: '#3A342D', flexShrink: 0, marginTop: '1px', ...MONO, fontSize: '11px' }}>›</span>
                <span style={{ ...UI, fontSize: '13px', color: '#6B6357', lineHeight: 1.5 }}>{tip}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Quick Commands */}
        <div style={PANEL}>
          <div style={{ padding: '18px 20px', borderBottom: '1px solid rgba(42,40,32,0.9)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Target size={13} color="#F59E0B" />
            <span style={{ ...MONO, fontSize: '11px', letterSpacing: '0.12em', color: '#A89F8C' }}>QUICK COMMANDS</span>
          </div>
          <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {[
              '"Check system health"',
              '"Why is my CPU usage high?"',
              '"Optimize memory usage"',
              '"Show performance trends"',
            ].map(cmd => (
              <button
                key={cmd}
                onClick={() => handleSendMessage(cmd.replace(/"/g, ''))}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(42,40,32,0.9)',
                  ...MONO,
                  fontSize: '11px',
                  color: '#4A443D',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                  letterSpacing: '0.02em',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.borderColor = 'rgba(245,158,11,0.3)';
                  e.currentTarget.style.color = '#F59E0B';
                  e.currentTarget.style.background = 'rgba(245,158,11,0.04)';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = 'rgba(42,40,32,0.9)';
                  e.currentTarget.style.color = '#4A443D';
                  e.currentTarget.style.background = 'rgba(255,255,255,0.02)';
                }}
              >
                {cmd}
              </button>
            ))}
          </div>
        </div>
      </div>

    </div>
  );
};

function MetricPill({ label, value }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '2px 7px', borderRadius: '4px',
      background: 'rgba(245,158,11,0.08)',
      border: '1px solid rgba(245,158,11,0.18)',
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: '10px', letterSpacing: '0.06em',
    }}>
      <span style={{ color: '#4A443D' }}>{label}</span>
      <span style={{ color: '#F59E0B' }}>{value}</span>
    </span>
  );
}

export default AIAssistant;
