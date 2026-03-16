import React, { useState, useEffect } from 'react';
import {
  Paper,
  Box,
  Typography,
  Grid,
  LinearProgress,
  Chip,
  useTheme,
  IconButton
} from '@mui/material';
import {
  Memory as MemoryIcon,
  Storage as StorageIcon,
  Speed as CpuIcon,
  NetworkCheck as NetworkIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import { motion } from 'framer-motion';
import { apiService, realTimeService } from '../services/api';

const SystemMetrics = () => {
  const theme = useTheme();
  const [systemData, setSystemData] = useState({
    cpu: 0,
    memory: 0,
    disk: 0,
    network_in: 0,
    network_out: 0,
    status: 'loading',
    uptime: 'N/A',
    active_processes: 0
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Initial data fetch
    const fetchData = async () => {
      setLoading(true);
      const data = await apiService.getSystemData();
      setSystemData(data);
      setLoading(false);
    };

    fetchData();

    // Subscribe to real-time updates
    const unsubscribe = realTimeService.subscribe('system', (data) => {
      setSystemData(data);
      setLoading(false);
    });

    return unsubscribe;
  }, []);

  const handleRefresh = async () => {
    setLoading(true);
    const data = await apiService.getSystemData();
    setSystemData(data);
    setLoading(false);
  };

  if (!systemData) {
    return (
      <Paper sx={{ p: 3, height: 200 }}>
        <Typography>Loading system metrics...</Typography>
      </Paper>
    );
  }

  const metrics = [
    {
      label: 'CPU Usage',
      value: systemData.cpu,
      icon: <CpuIcon />,
      color: systemData.cpu > 80 ? '#ff6b6b' : systemData.cpu > 60 ? '#ffd93d' : '#00d4aa',
      unit: '%'
    },
    {
      label: 'Memory',
      value: systemData.memory,
      icon: <MemoryIcon />,
      color: systemData.memory > 85 ? '#ff6b6b' : systemData.memory > 70 ? '#ffd93d' : '#00d4aa',
      unit: '%'
    },
    {
      label: 'Disk Usage',
      value: systemData.disk,
      icon: <StorageIcon />,
      color: systemData.disk > 90 ? '#ff6b6b' : systemData.disk > 75 ? '#ffd93d' : '#00d4aa',
      unit: '%'
    },
    {
      label: 'Network',
      value: systemData.network_in,
      icon: <NetworkIcon />,
      color: '#00d4aa',
      unit: 'MB/s'
    }
  ];

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  };

  const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: {
      y: 0,
      opacity: 1,
      transition: {
        type: "spring",
        stiffness: 300,
        damping: 24
      }
    }
  };

  return (
    <motion.div
      variants={containerVariants}
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
        borderRadius: 3
      }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            System Overview
          </Typography>
          <Chip 
            label={`Uptime: ${systemData.uptime}`}
            color="primary"
            variant="outlined"
            size="small"
          />
        </Box>

        <Grid container spacing={3}>
          {metrics.map((metric, index) => (
            <Grid item xs={12} sm={6} md={3} key={metric.label}>
              <motion.div variants={itemVariants}>
                <Box sx={{ 
                  p: 2, 
                  borderRadius: 2,
                  background: theme.palette.mode === 'dark' 
                    ? 'rgba(255, 255, 255, 0.03)'
                    : 'rgba(0, 0, 0, 0.02)',
                  border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.03)'}`,
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    transform: 'translateY(-2px)',
                    boxShadow: `0 8px 32px ${metric.color}20`
                  }
                }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Box sx={{ 
                      p: 1, 
                      borderRadius: '50%', 
                      background: `${metric.color}20`,
                      color: metric.color,
                      mr: 2
                    }}>
                      {metric.icon}
                    </Box>
                    <Typography variant="body2" color="textSecondary">
                      {metric.label}
                    </Typography>
                  </Box>

                  <Typography variant="h4" sx={{ 
                    fontWeight: 700, 
                    color: metric.color,
                    mb: 1
                  }}>
                    {metric.value}{metric.unit}
                  </Typography>

                  <LinearProgress
                    variant="determinate"
                    value={metric.value}
                    sx={{
                      height: 6,
                      borderRadius: 3,
                      backgroundColor: theme.palette.mode === 'dark' 
                        ? 'rgba(255, 255, 255, 0.1)'
                        : 'rgba(0, 0, 0, 0.1)',
                      '& .MuiLinearProgress-bar': {
                        borderRadius: 3,
                        background: `linear-gradient(90deg, ${metric.color}80, ${metric.color})`
                      }
                    }}
                  />
                </Box>
              </motion.div>
            </Grid>
          ))}
        </Grid>
      </Paper>
    </motion.div>
  );
};

export default SystemMetrics;