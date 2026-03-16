import React, { useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { apiService } from '../services/api';
import chatStream from '../services/chatStream';
import realtime from '../services/realtime';
import { Activity, TrendingUp, Zap, Wrench, Lightbulb, Target, Bot, MessageSquare } from 'lucide-react';

const quickActions = [
  { label: 'Health Check', icon: <Activity size={20} />, action: 'health-check' },
  { label: 'Performance Analysis', icon: <TrendingUp size={20} />, action: 'performance' },
  { label: 'Resource Optimization', icon: <Zap size={20} />, action: 'optimization' },
  { label: 'Troubleshoot Issues', icon: <Wrench size={20} />, action: 'troubleshoot' }
];

// Frontend small-talk heuristic mirroring backend logic so we can
// 1) Skip streaming path (no metadata there yet) and
// 2) Apply compact UI styling.
function isSmallTalk(message) {
  if (!message) return false;
  const msg = String(message).trim().toLowerCase();
  if (!msg) return false;
  const greetings = [
    'hi', 'hey', 'hello', 'hola', 'yo', 'sup', 'good morning', 'good evening', 'good afternoon',
    'how are you', 'how r u', 'how are u', "what's up", 'whats up', 'how is it going', 'how are things'
  ];
  const systemKeywords = ['cpu', 'memory', 'disk', 'performance', 'network', 'error', 'status', 'health'];
  if (systemKeywords.some(k => msg.includes(k))) return false;
  const isGreeting = greetings.some(g => msg === g || msg.includes(g));
  return isGreeting && msg.length <= 60; // keep same length guard
}

const AIAssistant = () => {
  const [messages, setMessages] = useState([
    {
      type: 'ai',
      content:
        "Hello! I'm your AIOps AI Assistant. I can help you analyze system performance, troubleshoot issues, and provide insights. What can I help you with today?",
      timestamp: new Date().toLocaleTimeString()
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const partialRef = useRef('');
  const cancelRef = useRef(null);

  const handleSendMessage = async (message = inputValue) => {
    if (!message.trim()) return;

    const userMessage = {
      type: 'user',
      content: message,
      timestamp: new Date().toLocaleTimeString()
    };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    // Prefer streaming via sockets if available
  const sock = (() => { try { return realtime.getSocket(); } catch { return null; } })();
  const smallTalk = isSmallTalk(message);
  // Skip streaming for small talk so we can leverage REST metadata (small_talk flag)
  if (sock && !sock.disconnected && !smallTalk) {
      setStreaming(true);
      setIsTyping(false);
      partialRef.current = '';
      try {
        const handle = chatStream.send(message, {
          onToken: (t) => {
            partialRef.current += t;
            setMessages((prev) => {
              const copy = [...prev];
              if (copy.length && copy[copy.length - 1]?.streaming) {
                copy[copy.length - 1] = { ...copy[copy.length - 1], content: partialRef.current };
              } else {
                copy.push({ type: 'ai', content: partialRef.current, streaming: true, timestamp: new Date().toLocaleTimeString() });
              }
              return copy;
            });
          },
          onDone: () => {
            setStreaming(false);
            cancelRef.current = null;
            setMessages((prev) => {
              const copy = [...prev];
              if (copy.length && copy[copy.length - 1]?.streaming) {
                copy[copy.length - 1] = { type: 'ai', content: partialRef.current, timestamp: new Date().toLocaleTimeString() };
              }
              return copy;
            });
          },
          onError: (err) => {
            setStreaming(false);
            cancelRef.current = null;
            setMessages((prev) => [...prev, { type: 'ai', content: `Error: ${err}`, timestamp: new Date().toLocaleTimeString() }]);
          }
        });
        cancelRef.current = handle;
        return; // streaming path
      } catch (e) {
        // Fall back to REST
      }
    }

    setIsTyping(true);
    try {
      const res = await apiService.sendChatMessage(message, smallTalk ? { expect_small_talk: true } : {});
      const botText = res?.response || 'No response received.';
      const smallTalkFlag = !!res?.small_talk || smallTalk; // backend authoritative
      const metrics = res?.small_talk_metrics || null;
      setMessages(prev => [
        ...prev,
        { type: 'ai', content: botText, timestamp: new Date().toLocaleTimeString(), smallTalk: smallTalkFlag, metrics }
      ]);
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { type: 'ai', content: 'Chat service unavailable.', timestamp: new Date().toLocaleTimeString() }
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleQuickAction = (action) => {
    const actionMessages = {
      'health-check': 'Please run a comprehensive system health check',
      'performance': 'Analyze my system performance and identify bottlenecks',
      'optimization': 'Help me optimize my system resources',
      'troubleshoot': "I'm experiencing system issues, help me troubleshoot"
    };

    handleSendMessage(actionMessages[action]);
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">AI Assistant</h2>
        <p className="text-gray-600">Get intelligent help with system monitoring and optimization</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-6">
        {quickActions.map((action, index) => (
          <button
            key={index}
            onClick={() => handleQuickAction(action.action)}
            className="bg-white border border-gray-200 rounded-xl p-4 transition-shadow duration-200 hover:shadow-md"
          >
            <div className="mb-2 flex justify-center text-blue-600">{action.icon}</div>
            <div className="text-gray-900 font-medium text-sm">{action.label}</div>
          </button>
        ))}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="h-96 overflow-y-auto mb-4 space-y-4">
          {messages.map((message, index) => {
            const baseAi = message.smallTalk
              ? 'bg-emerald-50 text-gray-900 border border-emerald-200'
              : 'bg-gray-50 text-gray-900 border border-gray-200';
            return (
              <div key={index} className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-xs lg:max-w-md px-4 py-3 rounded-lg ${
                  message.type === 'user'
                    ? 'bg-blue-600 text-white'
                    : baseAi
                }`}>
                  <div className="flex items-start space-x-2">
                    {message.type === 'ai' && (message.smallTalk ? <MessageSquare size={18} className="text-emerald-600 mt-0.5 shrink-0" /> : <Bot size={18} className="text-blue-600 mt-0.5 shrink-0" />)}
                    <div className="flex-1">
                      {message.type === 'ai' ? (
                        <>
                          {message.smallTalk ? (
                            <div className="text-sm leading-snug text-gray-800">
                              <p className="text-[10px] uppercase tracking-wide font-semibold text-emerald-600 mb-1">Small Talk</p>
                              {message.metrics && (
                                <div className="text-xs text-emerald-700 font-medium flex flex-wrap gap-x-2 gap-y-1 mb-1">
                                  {typeof message.metrics.cpu === 'number' && <span>CPU {message.metrics.cpu.toFixed(1)}%</span>}
                                  {typeof message.metrics.memory === 'number' && <span>Mem {message.metrics.memory.toFixed(1)}%</span>}
                                  {typeof message.metrics.disk === 'number' && <span>Disk {message.metrics.disk.toFixed(1)}%</span>}
                                </div>
                              )}
                              <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(String(message.content || '').replace(/Current snapshot:[^<]*<br>?/i,'').trim()) }} />
                            </div>
                          ) : (
                            <div className="text-sm prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(String(message.content || '')) }} />
                          )}
                        </>
                      ) : (
                        <p className="text-sm">{message.content}</p>
                      )}
                      <p className="text-xs opacity-70 mt-1">{message.timestamp}</p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}

          {(isTyping || streaming) && (
            <div className="flex justify-start">
              <div className="bg-gray-50 border border-gray-200 px-4 py-3 rounded-lg max-w-xs">
                <div className="flex items-center space-x-2">
                  <Bot size={18} className="text-blue-600 shrink-0" />
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                    <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex space-x-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
            placeholder="Ask me anything about your system..."
            className="flex-1 bg-white border border-gray-300 rounded-lg px-4 py-3 text-gray-900 placeholder-gray-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          <button
            onClick={() => handleSendMessage()}
            disabled={!inputValue.trim() || isTyping || streaming}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white px-6 py-3 rounded-lg transition-colors duration-200 disabled:cursor-not-allowed"
          >
            {streaming ? 'Streaming...' : isTyping ? 'Sending...' : 'Send'}
          </button>
          {streaming && (
            <button
              onClick={() => {
                try { cancelRef.current?.cancel?.(); } finally { setStreaming(false); }
              }}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-3 rounded-lg transition-colors duration-200"
            >
              Stop
            </button>
          )}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <Lightbulb size={18} className="mr-2 text-yellow-500" />
            Tips & Suggestions
          </h3>
          <div className="space-y-3">
            <div className="text-gray-700 text-sm">• Ask about specific system metrics or performance issues</div>
            <div className="text-gray-700 text-sm">• Request optimization recommendations</div>
            <div className="text-gray-700 text-sm">• Get help with troubleshooting steps</div>
            <div className="text-gray-700 text-sm">• Learn about system health patterns</div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <Target size={18} className="mr-2 text-blue-500" />
            Quick Commands
          </h3>
          <div className="space-y-2">
            <code className="block bg-gray-50 text-green-700 border border-gray-200 text-xs p-2 rounded">"Check system health"</code>
            <code className="block bg-gray-50 text-green-700 border border-gray-200 text-xs p-2 rounded">"Why is my CPU usage high?"</code>
            <code className="block bg-gray-50 text-green-700 border border-gray-200 text-xs p-2 rounded">"Optimize memory usage"</code>
            <code className="block bg-gray-50 text-green-700 border border-gray-200 text-xs p-2 rounded">"Show performance trends"</code>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIAssistant;