import React, { useState, useEffect, memo } from 'react';
import { apiService, realTimeService, USE_MOCKS } from '../services/api';
import {
  Paper,
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  IconButton,
  useTheme,
  Card,
  CardContent,
  Collapse,
  Grid,
  Tooltip,
  Badge,
  Fab
} from '@mui/material';
import {
  Error as ErrorIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  CheckCircle as SuccessIcon,
  Refresh as RefreshIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  NotificationsActive as AlertIcon,
  Schedule as TimeIcon,
  Source as SourceIcon
} from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';
import { Lightbulb, BellRing, LayoutList, LayoutGrid } from 'lucide-react';

const AlertsPanel = memo(() => {
  const theme = useTheme();
  const [alerts, setAlerts] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [viewMode, setViewMode] = useState('table'); // 'table' or 'cards'

  const fetchAlerts = async () => {
    try {
      const list = await apiService.getAlerts();
      // If backend returns anomalies, map to the expected rich shape minimally
      if (Array.isArray(list) && list.length && list[0]?.description && list[0]?.severity) {
        const mapped = list.map((a, idx) => ({
          id: a.id || idx + 1,
          severity: a.severity || 'info',
          message: a.description || a.message || 'Alert',
          source: a.source || 'System Monitor',
          timestamp: new Date(a.timestamp || Date.now()),
          status: a.status || 'active',
          details: a.details || a.description || '',
          category: a.category || 'General',
          affected_systems: a.affected_systems || [],
          recommendation: a.recommendation || ''
        }));
        setAlerts(mapped);
        return;
      }
    } catch (e) {
      console.warn('Alerts fetch failed, falling back to mocks if enabled');
    }
    if (USE_MOCKS) {
      // Enhanced mock alerts data with more details
      const mockAlerts = [
      {
        id: 1,
        severity: 'critical',
        message: 'High memory usage detected - System approaching critical threshold',
        source: 'System Monitor',
        timestamp: new Date(Date.now() - 2 * 60000), // 2 minutes ago
        status: 'active',
        details: 'Memory usage has reached 95% and may cause system instability. Consider closing unnecessary applications or adding more RAM.',
        category: 'Performance',
        affected_systems: ['Primary Server', 'Database'],
        recommendation: 'Restart memory-intensive processes or scale up resources'
      },
      {
        id: 2,
        severity: 'warning',
        message: 'CPU temperature exceeding safe operating range',
        source: 'Hardware Monitor',
        timestamp: new Date(Date.now() - 5 * 60000), // 5 minutes ago
        status: 'investigating',
        details: 'CPU temperature has reached 78°C, which is above the recommended 70°C threshold. This may lead to thermal throttling.',
        category: 'Hardware',
        affected_systems: ['CPU Core 1', 'CPU Core 2'],
        recommendation: 'Check cooling system and ensure proper ventilation'
      },
      {
        id: 3,
        severity: 'info',
        message: 'Automated backup completed successfully',
        source: 'Backup Service',
        timestamp: new Date(Date.now() - 15 * 60000), // 15 minutes ago
        status: 'resolved',
        details: 'Daily backup process completed without errors. All data has been successfully backed up to remote storage.',
        category: 'Maintenance',
        affected_systems: ['Backup Server'],
        recommendation: 'No action required'
      },
      {
        id: 4,
        severity: 'error',
        message: 'Database connection timeout detected',
        source: 'Database Monitor',
        timestamp: new Date(Date.now() - 30 * 60000), // 30 minutes ago
        status: 'investigating',
        details: 'Multiple connection timeouts detected on the primary database. This may indicate network issues or database overload.',
        category: 'Database',
        affected_systems: ['Primary DB', 'Application Server'],
        recommendation: 'Check database performance and network connectivity'
      },
      {
        id: 5,
        severity: 'success',
        message: 'System health check passed all diagnostics',
        source: 'Health Monitor',
        timestamp: new Date(Date.now() - 45 * 60000), // 45 minutes ago
        status: 'resolved',
        details: 'Comprehensive system health check completed successfully. All components are functioning within normal parameters.',
        category: 'Monitoring',
        affected_systems: ['All Systems'],
        recommendation: 'Continue normal operations'
      },
      {
        id: 6,
        severity: 'warning',
        message: 'Disk space on /var partition approaching limit',
        source: 'Storage Monitor',
        timestamp: new Date(Date.now() - 60 * 60000), // 1 hour ago
        status: 'active',
        details: 'Storage usage on /var partition has reached 85% capacity. Consider cleaning up log files or expanding storage.',
        category: 'Storage',
        affected_systems: ['File Server'],
        recommendation: 'Clean up log files or expand storage capacity'
      }
      ];
      setAlerts(mockAlerts);
    } else {
      setAlerts([]);
    }
  };

  useEffect(() => {
    fetchAlerts();
    // subscribe to realtime polling for alerts
    const unsubscribe = realTimeService.subscribe('alerts', (data) => {
      if (Array.isArray(data)) {
        // naive map; reuse mapping logic in fetch if needed
        setAlerts((prev) => data.map((a, idx) => ({
          id: a.id || idx + 1,
          severity: a.severity || 'info',
          message: a.description || a.message || 'Alert',
          source: a.source || 'System Monitor',
          timestamp: new Date(a.timestamp || Date.now()),
          status: a.status || 'active',
          details: a.details || a.description || '',
          category: a.category || 'General',
          affected_systems: a.affected_systems || [],
          recommendation: a.recommendation || ''
        })));
      }
    });
    const onGlobal = () => fetchAlerts();
    try { window.addEventListener('aiops:refresh', onGlobal); } catch {}
    return () => { unsubscribe(); try { window.removeEventListener('aiops:refresh', onGlobal); } catch {} };
  }, []);

  const toggleExpanded = (alertId) => {
    setExpanded(prev => ({
      ...prev,
      [alertId]: !prev[alertId]
    }));
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'critical':
      case 'error':
        return <ErrorIcon sx={{ color: '#ff6b6b' }} />;
      case 'warning':
        return <WarningIcon sx={{ color: '#ffd93d' }} />;
      case 'info':
        return <InfoIcon sx={{ color: '#4fc3f7' }} />;
      case 'success':
        return <SuccessIcon sx={{ color: '#00d4aa' }} />;
      default:
        return <InfoIcon sx={{ color: '#4fc3f7' }} />;
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return '#ff6b6b';
      case 'error': return '#ff6b6b';
      case 'warning': return '#ffd93d';
      case 'info': return '#4fc3f7';
      case 'success': return '#00d4aa';
      default: return '#4fc3f7';
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return '#ff6b6b';
      case 'investigating': return '#ffd93d';
      case 'resolved': return '#00d4aa';
      default: return '#4fc3f7';
    }
  };

  const formatTimeAgo = (timestamp) => {
    const diff = Date.now() - timestamp.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (days > 0) return `${days}d ${hours % 24}h ago`;
    if (hours > 0) return `${hours}h ${minutes % 60}m ago`;
    return `${minutes}m ago`;
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.05,
        delayChildren: 0.1
      }
    }
  };

  const itemVariants = {
    hidden: { x: -20, opacity: 0 },
    visible: {
      x: 0,
      opacity: 1,
      transition: {
        type: "spring",
        stiffness: 300,
        damping: 24
      }
    }
  };

  const criticalCount = alerts.filter(a => a.severity === 'critical').length;
  const warningCount = alerts.filter(a => a.severity === 'warning').length;
  const activeCount = alerts.filter(a => a.status === 'active').length;

  const CardView = () => (
    <Grid container spacing={2}>
      {alerts.map((alert) => (
        <Grid item xs={12} md={6} lg={4} key={alert.id}>
          <motion.div variants={itemVariants}>
            <Card sx={{
              background: theme.palette.mode === 'dark' 
                ? 'rgba(255, 255, 255, 0.03)'
                : 'rgba(0, 0, 0, 0.02)',
              border: `1px solid ${theme.palette.divider}`,
              borderLeft: `4px solid ${getSeverityColor(alert.severity)}`,
              borderRadius: 2,
              transition: 'all 0.3s ease',
              '&:hover': {
                transform: 'translateY(-4px)',
                boxShadow: `0 8px 25px ${getSeverityColor(alert.severity)}20`
              }
            }}>
              <CardContent sx={{ p: 2 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {getSeverityIcon(alert.severity)}
                    <Chip 
                      label={alert.severity.toUpperCase()}
                      size="small"
                      sx={{
                        bgcolor: getSeverityColor(alert.severity),
                        color: 'white',
                        fontWeight: 600
                      }}
                    />
                  </Box>
                  <IconButton 
                    size="small" 
                    onClick={() => toggleExpanded(alert.id)}
                  >
                    {expanded[alert.id] ? <CollapseIcon /> : <ExpandIcon />}
                  </IconButton>
                </Box>
                
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  {alert.message}
                </Typography>
                
                <Box sx={{ display: 'flex', gap: 1, mb: 1, flexWrap: 'wrap' }}>
                  <Chip 
                    label={alert.status}
                    size="small"
                    sx={{
                      bgcolor: `${getStatusColor(alert.status)}20`,
                      color: getStatusColor(alert.status),
                      fontWeight: 500,
                      textTransform: 'capitalize'
                    }}
                  />
                  <Chip 
                    label={alert.category}
                    size="small"
                    variant="outlined"
                  />
                </Box>
                
                <Typography variant="caption" color="textSecondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <TimeIcon fontSize="small" />
                  {formatTimeAgo(alert.timestamp)}
                </Typography>
                
                <Collapse in={expanded[alert.id]}>
                  <Box sx={{ mt: 2, p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      {alert.details}
                    </Typography>
                    <Typography variant="caption" color="textSecondary" display="block" sx={{ mb: 1 }}>
                      <strong>Source:</strong> {alert.source}
                    </Typography>
                    <Typography variant="caption" color="textSecondary" display="block" sx={{ mb: 1 }}>
                      <strong>Affected:</strong> {alert.affected_systems?.join(', ')}
                    </Typography>
                    <Box sx={{ mt: 1, p: 1, bgcolor: `${getSeverityColor(alert.severity)}10`, borderRadius: 1 }}>
                      <Typography variant="caption" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Lightbulb size={14} /> {alert.recommendation}
                      </Typography>
                    </Box>
                  </Box>
                </Collapse>
              </CardContent>
            </Card>
          </motion.div>
        </Grid>
      ))}
    </Grid>
  );

  const TableView = () => (
    <TableContainer>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 600 }}>Severity</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Message</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Source</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Time</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          <AnimatePresence>
            {alerts.map((alert) => (
              <motion.tr key={alert.id} variants={itemVariants}>
                <TableRow
                  sx={{
                    '&:last-child td, &:last-child th': { border: 0 },
                    transition: 'all 0.2s ease',
                    '&:hover': {
                      backgroundColor: theme.palette.mode === 'dark' 
                        ? 'rgba(255, 255, 255, 0.02)'
                        : 'rgba(0, 0, 0, 0.02)',
                      transform: 'translateX(4px)'
                    }
                  }}
                >
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {getSeverityIcon(alert.severity)}
                      <Typography variant="body2" sx={{ textTransform: 'capitalize', fontWeight: 500 }}>
                        {alert.severity}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ maxWidth: 300 }}>
                      {alert.message}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <SourceIcon fontSize="small" color="action" />
                      <Typography variant="body2" color="textSecondary">
                        {alert.source}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={alert.status}
                      size="small"
                      sx={{
                        background: `${getStatusColor(alert.status)}20`,
                        color: getStatusColor(alert.status),
                        fontWeight: 500,
                        textTransform: 'capitalize'
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="textSecondary">
                      {formatTimeAgo(alert.timestamp)}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <IconButton 
                      size="small" 
                      onClick={() => toggleExpanded(alert.id)}
                    >
                      {expanded[alert.id] ? <CollapseIcon /> : <ExpandIcon />}
                    </IconButton>
                  </TableCell>
                </TableRow>
              </motion.tr>
            ))}
          </AnimatePresence>
        </TableBody>
      </Table>
    </TableContainer>
  );

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
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
            <BellRing size={20} /> Recent Alerts
            <Badge badgeContent={activeCount} color="error">
              <AlertIcon />
            </Badge>
          </Typography>
          
          <Box sx={{ display: 'flex', gap: 1 }}>
            {criticalCount > 0 && (
              <Chip 
                label={`${criticalCount} Critical`}
                size="small"
                sx={{ bgcolor: '#ff6b6b', color: 'white', fontWeight: 600 }}
              />
            )}
            {warningCount > 0 && (
              <Chip 
                label={`${warningCount} Warning`}
                size="small"
                sx={{ bgcolor: '#ffd93d', color: 'black', fontWeight: 600 }}
              />
            )}
          </Box>
        </Box>
        
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="Toggle View">
            <IconButton size="small" onClick={() => setViewMode(viewMode === 'table' ? 'cards' : 'table')}>
              {viewMode === 'table' ? <LayoutList size={18} /> : <LayoutGrid size={18} />}
            </IconButton>
          </Tooltip>
          <Tooltip title="Refresh Alerts">
            <IconButton size="small" onClick={fetchAlerts}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {viewMode === 'cards' ? <CardView /> : <TableView />}
      </motion.div>
    </Paper>
  );
});

export default AlertsPanel;