import React, { memo } from 'react';
import {
  Paper,
  Box,
  Typography,
  Grid,
  LinearProgress,
  useTheme,
  Chip,
  Card,
  CardContent,
  Tooltip
} from '@mui/material';
import {
  Memory as MemoryIcon,
  Storage as StorageIcon,
  Speed as CpuIcon,
  NetworkCheck as NetworkIcon,
  DeviceThermostat as TempIcon,
  Computer as ProcessIcon
} from '@mui/icons-material';
import { motion } from 'framer-motion';
import { BarChart2, Clock, RefreshCw } from 'lucide-react';

const SimpleSystemMetrics = memo(({ systemData }) => {
  const theme = useTheme();

  // If no data provided, show enhanced loading state
  if (!systemData) {
    return (
      <Paper sx={{ 
        p: 3,
        background: theme.palette.background.paper,
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 3,
        boxShadow: theme.palette.mode === 'dark' 
          ? '0 8px 32px rgba(0, 0, 0, 0.3)'
          : '0 8px 32px rgba(0, 0, 0, 0.1)'
      }}>
        <Typography variant="h6" sx={{ mb: 3, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
          <BarChart2 size={20} /> System Metrics
          <Chip label="Loading..." size="small" color="info" />
        </Typography>
        <Box sx={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center',
          height: 200,
          flexDirection: 'column',
          gap: 2
        }}>
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
          >
            <CpuIcon sx={{ fontSize: 48, color: theme.palette.primary.main }} />
          </motion.div>
          <Typography variant="body2" color="textSecondary">
            Loading system data...
          </Typography>
        </Box>
      </Paper>
    );
  }

  const metrics = [
    {
      label: 'CPU Usage',
      value: systemData.cpu || 0,
      icon: <CpuIcon />,
      color: systemData.cpu > 80 ? '#ff6b6b' : systemData.cpu > 60 ? '#ffa726' : '#00d4aa',
      unit: '%',
      max: 100,
      description: 'Processor utilization'
    },
    {
      label: 'Memory',
      value: systemData.memory || 0,
      icon: <MemoryIcon />,
      color: systemData.memory > 85 ? '#ff6b6b' : systemData.memory > 70 ? '#ffa726' : '#00d4aa',
      unit: '%',
      max: 100,
      description: 'RAM usage'
    },
    {
      label: 'Disk Space',
      value: systemData.disk || 0,
      icon: <StorageIcon />,
      color: systemData.disk > 90 ? '#ff6b6b' : systemData.disk > 75 ? '#ffa726' : '#00d4aa',
      unit: '%',
      max: 100,
      description: 'Storage utilization'
    },
    {
      label: 'Network In',
      value: systemData.network_in || 0,
      icon: <NetworkIcon />,
      color: '#4fc3f7',
      unit: 'Mbps',
      max: Math.max(500, (systemData.network_in || 0) * 1.2),
      description: 'Incoming network traffic'
    },
    {
      label: 'Temperature',
      value: systemData.temperature || 0,
      icon: <TempIcon />,
      color: systemData.temperature > 70 ? '#ff6b6b' : systemData.temperature > 60 ? '#ffa726' : '#00d4aa',
      unit: '°C',
      max: 100,
      description: 'System temperature'
    },
    {
      label: 'Processes',
      value: systemData.active_processes || 0,
      icon: <ProcessIcon />,
      color: '#9c27b0',
      unit: '',
      max: Math.max(200, (systemData.active_processes || 0) * 1.2),
      description: 'Active processes count'
    }
  ];

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy': return '#00d4aa';
      case 'warning': return '#ffa726';
      case 'critical': return '#ff6b6b';
      default: return '#757575';
    }
  };

  const getStatusLabel = (status) => {
    switch (status) {
      case 'healthy': return 'HEALTHY';
      case 'warning': return 'WARNING';
      case 'critical': return 'CRITICAL';
      case 'disconnected': return 'OFFLINE';
      default: return 'UNKNOWN';
    }
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2
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
    <Paper sx={{ 
      p: 3,
      background: theme.palette.mode === 'dark' 
        ? 'linear-gradient(135deg, rgba(26, 31, 58, 0.8) 0%, rgba(45, 53, 97, 0.8) 100%)'
        : 'linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(248, 250, 252, 0.9) 100%)',
      backdropFilter: 'blur(20px)',
      border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)'}`,
      borderRadius: 3,
      boxShadow: theme.palette.mode === 'dark' 
        ? '0 8px 32px rgba(0, 0, 0, 0.3)'
        : '0 8px 32px rgba(0, 0, 0, 0.1)'
    }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
          <BarChart2 size={20} /> System Metrics
          <motion.div
            animate={{ scale: [1, 1.05, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <Chip 
              label="LIVE"
              size="small"
              sx={{
                bgcolor: '#00d4aa',
                color: 'white',
                fontWeight: 600,
                fontSize: '0.7rem'
              }}
            />
          </motion.div>
        </Typography>
        
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Tooltip title={`System Status: ${systemData.status || 'Unknown'}`}>
            <Chip 
              label={getStatusLabel(systemData.status)}
              size="small"
              sx={{
                bgcolor: getStatusColor(systemData.status),
                color: 'white',
                fontWeight: 600,
                minWidth: 80
              }}
            />
          </Tooltip>
        </Box>
      </Box>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <Grid container spacing={2}>
          {metrics.map((metric, index) => (
            <Grid item xs={12} sm={6} md={4} lg={2} key={index}>
              <motion.div variants={itemVariants}>
                <Card
                  sx={{
                    background: theme.palette.mode === 'dark' 
                      ? 'rgba(255, 255, 255, 0.03)'
                      : 'rgba(0, 0, 0, 0.02)',
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 2,
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      transform: 'translateY(-4px)',
                      boxShadow: `0 8px 25px ${metric.color}20`,
                      borderColor: metric.color
                    }
                  }}
                >
                  <CardContent sx={{ p: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      <Box sx={{ 
                        color: metric.color, 
                        mr: 1,
                        display: 'flex',
                        alignItems: 'center',
                        p: 0.5,
                        borderRadius: 1,
                        bgcolor: `${metric.color}20`
                      }}>
                        {metric.icon}
                      </Box>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.8rem' }}>
                          {metric.label}
                        </Typography>
                      </Box>
                    </Box>
                    
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 1, color: metric.color }}>
                      {typeof metric.value === 'number' ? metric.value.toFixed(1) : metric.value}{metric.unit}
                    </Typography>
                    
                    {metric.max && (
                      <Box sx={{ mb: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={(metric.value / metric.max) * 100}
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
                    )}
                    
                    <Typography variant="caption" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                      {metric.description}
                    </Typography>
                  </CardContent>
                </Card>
              </motion.div>
            </Grid>
          ))}
        </Grid>
      </motion.div>

      <Box sx={{ 
        mt: 3, 
        pt: 2,
        borderTop: `1px solid ${theme.palette.divider}`,
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center' 
      }}>
        <Typography variant="caption" color="textSecondary" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Clock size={12} /> Uptime: <strong>{systemData.uptime || 'N/A'}</strong>
        </Typography>
        <Typography variant="caption" color="textSecondary" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <RefreshCw size={12} /> Updated: <strong>{systemData.last_updated ? new Date(systemData.last_updated).toLocaleTimeString() : 'Never'}</strong>
        </Typography>
      </Box>
    </Paper>
  );
});

export default SimpleSystemMetrics;