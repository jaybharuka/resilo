import React, { useState, useEffect, useRef } from 'react';
import {
  Drawer,
  Box,
  Typography,
  TextField,
  IconButton,
  List,
  ListItem,
  Paper,
  Chip,
  useTheme,
  InputAdornment,
  CircularProgress
} from '@mui/material';
import {
  Close as CloseIcon,
  Send as SendIcon,
  SmartToy as BotIcon,
  Person as PersonIcon
} from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';
import { apiService } from '../services/api';

const RealtimeChat = ({ open, onClose }) => {
  const theme = useTheme();
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (open && messages.length === 0) {
      // Initial greeting
      setTimeout(() => {
        setMessages([{
          id: 1,
          text: "Hi! I'm your Resilo assistant. I can help you with system monitoring, performance analysis, and troubleshooting. What would you like to know?",
          sender: 'bot',
          timestamp: new Date(),
          sentiment: 'friendly'
        }]);
      }, 500);
    }
  }, [open, messages.length]);

  const simulateBotResponse = (userMessage) => {
    setIsTyping(true);
    
    setTimeout(() => {
      let botResponse = "";
      let sentiment = "helpful";
      
      const userLower = userMessage.toLowerCase();
      
      if (userLower.includes('cpu') || userLower.includes('performance')) {
        botResponse = "I can see your CPU usage is currently at 28%. This is within normal range. Would you like me to analyze any specific performance issues?";
        sentiment = "analytical";
      } else if (userLower.includes('memory') || userLower.includes('ram')) {
        botResponse = "Your memory usage is at 75%. I recommend closing some unnecessary applications. Should I show you which processes are using the most memory?";
        sentiment = "concerned";
      } else if (userLower.includes('error') || userLower.includes('problem')) {
        botResponse = "I understand you're experiencing issues. Let me analyze your system logs. Can you describe what error you're seeing?";
        sentiment = "empathetic";
      } else if (userLower.includes('thank') || userLower.includes('good')) {
        botResponse = "You're welcome! I'm here to help keep your systems running smoothly. Is there anything else you'd like me to monitor?";
        sentiment = "satisfied";
      } else {
        botResponse = "I'm analyzing your request using my AI models. Could you provide more details about what you need help with?";
        sentiment = "curious";
      }
      
      setMessages(prev => [...prev, {
        id: prev.length + 1,
        text: botResponse,
        sender: 'bot',
        timestamp: new Date(),
        sentiment: sentiment
      }]);
      
      setIsTyping(false);
    }, Math.random() * 2000 + 1000); // 1-3 seconds delay
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;

    const newMessage = {
      id: messages.length + 1,
      text: inputValue,
      sender: 'user',
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, newMessage]);
    setIsTyping(true);

    try {
      // Send message to the real API via centralized apiService
      const data = await apiService.sendChatMessage(inputValue);
      const botMessage = {
        id: messages.length + 2,
        text: data?.response || "I'm currently offline, but I'll be back soon! In the meantime, check your system metrics above.",
        sender: 'bot',
        timestamp: new Date(),
        sentiment: 'helpful',
        systemContext: data?.system_context
      };

      setTimeout(() => {
        setMessages(prev => [...prev, botMessage]);
        setIsTyping(false);
      }, 500);
    } catch (error) {
      console.error('Chat error:', error);
      // Fallback response
      const fallbackMessage = {
        id: messages.length + 2,
        text: "Sorry, I'm having trouble connecting to the AI service right now. Please check if the API server is running and try again.",
        sender: 'bot',
        timestamp: new Date(),
        sentiment: 'error'
      };

      setTimeout(() => {
        setMessages(prev => [...prev, fallbackMessage]);
        setIsTyping(false);
      }, 500);
    }
    
    setInputValue('');
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const getSentimentColor = (sentiment) => {
    switch (sentiment) {
      case 'friendly': return '#00d4aa';
      case 'concerned': return '#ffd93d';
      case 'empathetic': return '#ff6b6b';
      case 'satisfied': return '#00d4aa';
      case 'analytical': return '#4fc3f7';
      default: return theme.palette.primary.main;
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 400 },
          background: theme.palette.mode === 'dark' 
            ? 'linear-gradient(135deg, rgba(26, 31, 58, 0.95) 0%, rgba(45, 53, 97, 0.95) 100%)'
            : 'linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 250, 252, 0.95) 100%)',
          backdropFilter: 'blur(20px)'
        }
      }}
    >
      <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <Box sx={{ 
          p: 2, 
          borderBottom: `1px solid ${theme.palette.divider}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <BotIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                Resilo Assistant
              </Typography>
              <Typography variant="caption" color="textSecondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Box component="span" sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: '#4caf50', display: 'inline-block' }} />
                Online • AI-Powered
              </Typography>
            </Box>
          </Box>
          <IconButton onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </Box>

        {/* Messages */}
        <Box sx={{ 
          flexGrow: 1, 
          overflow: 'auto', 
          p: 2,
          display: 'flex',
          flexDirection: 'column'
        }}>
          <List sx={{ flexGrow: 1 }}>
            <AnimatePresence>
              {messages.map((message) => (
                <motion.div
                  key={message.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3 }}
                >
                  <ListItem sx={{ 
                    display: 'flex', 
                    justifyContent: message.sender === 'user' ? 'flex-end' : 'flex-start',
                    mb: 2
                  }}>
                    <Paper sx={{
                      p: 2,
                      maxWidth: '80%',
                      background: message.sender === 'user'
                        ? 'linear-gradient(45deg, #00d4aa, #4fffdd)'
                        : theme.palette.mode === 'dark' 
                          ? 'rgba(255, 255, 255, 0.05)'
                          : 'rgba(0, 0, 0, 0.03)',
                      color: message.sender === 'user' ? 'white' : 'inherit',
                      borderRadius: message.sender === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px'
                    }}>
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 1 }}>
                        {message.sender === 'bot' && (
                          <BotIcon sx={{ 
                            fontSize: 16, 
                            mr: 1, 
                            color: getSentimentColor(message.sentiment) 
                          }} />
                        )}
                        {message.sender === 'user' && (
                          <PersonIcon sx={{ fontSize: 16, mr: 1, color: 'rgba(255,255,255,0.8)' }} />
                        )}
                        <Typography variant="body2">
                          {message.text}
                        </Typography>
                      </Box>
                      
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="caption" sx={{ 
                          opacity: 0.7,
                          color: message.sender === 'user' ? 'rgba(255,255,255,0.7)' : 'text.secondary'
                        }}>
                          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </Typography>
                        
                        {message.sender === 'bot' && message.sentiment && (
                          <Chip 
                            label={message.sentiment}
                            size="small"
                            sx={{
                              height: 16,
                              fontSize: '0.6rem',
                              background: `${getSentimentColor(message.sentiment)}20`,
                              color: getSentimentColor(message.sentiment)
                            }}
                          />
                        )}
                      </Box>
                    </Paper>
                  </ListItem>
                </motion.div>
              ))}
            </AnimatePresence>
            
            {isTyping && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
              >
                <ListItem sx={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <Paper sx={{
                    p: 2,
                    background: theme.palette.mode === 'dark' 
                      ? 'rgba(255, 255, 255, 0.05)'
                      : 'rgba(0, 0, 0, 0.03)',
                    borderRadius: '16px 16px 16px 4px'
                  }}>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <BotIcon sx={{ fontSize: 16, mr: 1, color: theme.palette.primary.main }} />
                      <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
                        AI is thinking...
                      </Typography>
                    </Box>
                  </Paper>
                </ListItem>
              </motion.div>
            )}
          </List>
          <div ref={messagesEndRef} />
        </Box>

        {/* Input */}
        <Box sx={{ p: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
          <TextField
            fullWidth
            multiline
            maxRows={3}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about system performance, errors, or any IT issues..."
            variant="outlined"
            sx={{
              '& .MuiOutlinedInput-root': {
                borderRadius: 3
              }
            }}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton 
                    onClick={handleSendMessage}
                    disabled={!inputValue.trim()}
                    sx={{
                      background: inputValue.trim() ? 'linear-gradient(45deg, #00d4aa, #4fffdd)' : 'transparent',
                      color: inputValue.trim() ? 'white' : 'inherit',
                      '&:hover': {
                        background: inputValue.trim() ? 'linear-gradient(45deg, #00a279, #00d4aa)' : 'transparent'
                      }
                    }}
                  >
                    <SendIcon />
                  </IconButton>
                </InputAdornment>
              )
            }}
          />
        </Box>
      </Box>
    </Drawer>
  );
};

export default RealtimeChat;