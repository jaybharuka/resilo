import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import {
  Paper,
  Box,
  Typography,
  Grid,
  useTheme
} from '@mui/material';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';
import { motion } from 'framer-motion';
import { BarChart2, Network, Thermometer } from 'lucide-react';

const PerformanceChart = () => {
  const theme = useTheme();
  const [performanceData, setPerformanceData] = useState([]);
  const [networkData, setNetworkData] = useState([]);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        const series = await apiService.getPerformanceData();
        if (!mounted || !Array.isArray(series)) return;
        const mapped = series.map((pt) => ({
          time: new Date((pt.timestamp || Date.now()) * 1000).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' }),
          cpu: pt.cpu,
          memory: pt.memory,
          disk: pt.disk,
          temperature: pt.temperature ?? null,
          download: (pt.network_in || 0) / 1024,
          upload: (pt.network_out || 0) / 1024,
        }));
        setPerformanceData(mapped);
        setNetworkData(mapped);
      } catch (e) {
        // Leave empty if fetch fails; component remains stable
      }
    };
    fetchData();
    return () => { mounted = false; };
  }, []);

  const chartVariants = {
    hidden: { opacity: 0, scale: 0.95 },
    visible: {
      opacity: 1,
      scale: 1,
      transition: {
        duration: 0.5,
        ease: "easeOut"
      }
    }
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <Paper sx={{ 
          p: 2, 
          backgroundColor: theme.palette.mode === 'dark' ? 'rgba(30, 30, 30, 0.95)' : 'rgba(255, 255, 255, 0.95)',
          backdropFilter: 'blur(10px)',
          border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)'}`
        }}>
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
            {label}
          </Typography>
          {payload.map((entry, index) => (
            <Typography
              key={index}
              variant="body2"
              sx={{ color: entry.color }}
            >
              {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}
              {entry.name === 'Temperature' ? '°C' : 
               entry.name.includes('CPU') || entry.name.includes('Memory') || entry.name.includes('Disk') ? '%' :
               entry.name.includes('Download') || entry.name.includes('Upload') ? ' MB/s' : ''}
            </Typography>
          ))}
        </Paper>
      );
    }
    return null;
  };

  return (
    <Box>
      <Grid container spacing={3}>
        {/* System Performance Chart */}
        <Grid item xs={12} lg={6}>
          <motion.div
            variants={chartVariants}
            initial="hidden"
            animate="visible"
          >
            <Paper sx={{ 
              p: 3,
              background: theme.palette.mode === 'dark' 
                ? 'linear-gradient(135deg, rgba(26, 31, 58, 0.8) 0%, rgba(45, 53, 97, 0.8) 100%)'
                : 'linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(248, 250, 252, 0.9) 100%)',
              backdropFilter: 'blur(20px)',
              border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)'}`,
              borderRadius: 3,
              height: 400
            }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <BarChart2 size={20} /> System Performance
              </Typography>
              <ResponsiveContainer width="100%" height="85%">
                <LineChart data={performanceData}>
                  <CartesianGrid 
                    strokeDasharray="3 3" 
                    stroke={theme.palette.mode === 'dark' ? '#333' : '#e0e0e0'} 
                  />
                  <XAxis 
                    dataKey="time" 
                    stroke={theme.palette.text.secondary}
                    fontSize={12}
                  />
                  <YAxis 
                    stroke={theme.palette.text.secondary}
                    fontSize={12}
                    domain={[0, 100]}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Line 
                    type="monotone" 
                    dataKey="cpu" 
                    stroke="#ff6b6b" 
                    name="CPU Usage"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="memory" 
                    stroke="#4fc3f7" 
                    name="Memory Usage"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="disk" 
                    stroke="#00d4aa" 
                    name="Disk Usage"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Paper>
          </motion.div>
        </Grid>

        {/* Network Performance Chart */}
        <Grid item xs={12} lg={6}>
          <motion.div
            variants={chartVariants}
            initial="hidden"
            animate="visible"
            transition={{ delay: 0.2 }}
          >
            <Paper sx={{ 
              p: 3,
              background: theme.palette.mode === 'dark' 
                ? 'linear-gradient(135deg, rgba(26, 31, 58, 0.8) 0%, rgba(45, 53, 97, 0.8) 100%)'
                : 'linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(248, 250, 252, 0.9) 100%)',
              backdropFilter: 'blur(20px)',
              border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)'}`,
              borderRadius: 3,
              height: 400
            }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Network size={20} /> Network Performance
              </Typography>
              <ResponsiveContainer width="100%" height="85%">
                <AreaChart data={networkData}>
                  <CartesianGrid 
                    strokeDasharray="3 3" 
                    stroke={theme.palette.mode === 'dark' ? '#333' : '#e0e0e0'} 
                  />
                  <XAxis 
                    dataKey="time" 
                    stroke={theme.palette.text.secondary}
                    fontSize={12}
                  />
                  <YAxis 
                    stroke={theme.palette.text.secondary}
                    fontSize={12}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="download"
                    stackId="1"
                    stroke="#8884d8"
                    fill="#8884d8"
                    fillOpacity={0.6}
                    name="Download Speed"
                  />
                  <Area
                    type="monotone"
                    dataKey="upload"
                    stackId="2"
                    stroke="#82ca9d"
                    fill="#82ca9d"
                    fillOpacity={0.6}
                    name="Upload Speed"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Paper>
          </motion.div>
        </Grid>

        {/* Temperature Chart */}
        <Grid item xs={12}>
          <motion.div
            variants={chartVariants}
            initial="hidden"
            animate="visible"
            transition={{ delay: 0.4 }}
          >
            <Paper sx={{ 
              p: 3,
              background: theme.palette.mode === 'dark' 
                ? 'linear-gradient(135deg, rgba(26, 31, 58, 0.8) 0%, rgba(45, 53, 97, 0.8) 100%)'
                : 'linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(248, 250, 252, 0.9) 100%)',
              backdropFilter: 'blur(20px)',
              border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)'}`,
              borderRadius: 3,
              height: 300
            }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Thermometer size={20} /> System Temperature
              </Typography>
              <ResponsiveContainer width="100%" height="85%">
                <AreaChart data={performanceData}>
                  <CartesianGrid 
                    strokeDasharray="3 3" 
                    stroke={theme.palette.mode === 'dark' ? '#333' : '#e0e0e0'} 
                  />
                  <XAxis 
                    dataKey="time" 
                    stroke={theme.palette.text.secondary}
                    fontSize={12}
                  />
                  <YAxis 
                    stroke={theme.palette.text.secondary}
                    fontSize={12}
                    domain={[35, 75]}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="temperature"
                    stroke="#ff9500"
                    fill="url(#temperatureGradient)"
                    strokeWidth={3}
                    name="Temperature"
                  />
                  <defs>
                    <linearGradient id="temperatureGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ff9500" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="#ff9500" stopOpacity={0.1}/>
                    </linearGradient>
                  </defs>
                </AreaChart>
              </ResponsiveContainer>
            </Paper>
          </motion.div>
        </Grid>
      </Grid>
    </Box>
  );
};

export default PerformanceChart;