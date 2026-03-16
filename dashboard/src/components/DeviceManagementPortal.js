/*
Device Management Portal
Admin portal for adding, monitoring, and managing company devices
*/

import React, { useState, useEffect } from 'react';
import { apiService, USE_MOCKS } from '../services/api';
import {
  Box,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  IconButton,
  Avatar,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tabs,
  Tab,
  Alert,
  Badge,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Tooltip,
  LinearProgress,
  Switch,
  FormControlLabel
} from '@mui/material';
import {
  Computer as ComputerIcon,
  Laptop as LaptopIcon,
  PhoneAndroid as PhoneIcon,
  Tablet as TabletIcon,
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Visibility as ViewIcon,
  Settings as SettingsIcon,
  Warning as WarningIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  CloudDownload as InstallIcon,
  Security as SecurityIcon,
  Analytics as AnalyticsIcon,
  Group as GroupIcon,
  Business as BusinessIcon,
  LocationOn as LocationIcon,
  NetworkCheck as NetworkIcon,
  Storage as StorageIcon,
  Memory as MemoryIcon,
  Speed as SpeedIcon
} from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';

// Device types and status enums
const DEVICE_TYPES = {
  LAPTOP: 'laptop',
  DESKTOP: 'desktop',
  MOBILE: 'mobile',
  TABLET: 'tablet',
  SERVER: 'server'
};

const DEVICE_STATUS = {
  ONLINE: 'online',
  OFFLINE: 'offline',
  WARNING: 'warning',
  CRITICAL: 'critical',
  MAINTENANCE: 'maintenance'
};

const OS_TYPES = {
  WINDOWS: 'Windows',
  MACOS: 'macOS',
  LINUX: 'Linux',
  ANDROID: 'Android',
  IOS: 'iOS'
};

// Mock device data (fallback when USE_MOCKS is true)
const mockDevices = [
  {
    id: 'DEV001',
    name: 'John-MacBook-Pro',
    type: DEVICE_TYPES.LAPTOP,
    os: OS_TYPES.MACOS,
    version: 'macOS Ventura 13.5',
    employee: 'John Smith',
    department: 'Engineering',
    status: DEVICE_STATUS.ONLINE,
    lastSeen: '2024-01-15T10:30:00Z',
    ipAddress: '192.168.1.101',
    macAddress: '00:1B:44:11:3A:B7',
    location: 'San Francisco, CA',
    specs: {
      cpu: 'Apple M2 Pro',
      memory: '16 GB',
      storage: '512 GB SSD',
      screen: '14-inch Retina'
    },
    performance: {
      cpu: 35,
      memory: 62,
      disk: 78,
      temperature: 45
    },
    security: {
      antivirus: true,
      firewall: true,
      encrypted: true,
      lastUpdate: '2024-01-14T09:00:00Z'
    },
    installed: true
  },
  {
    id: 'DEV002',
    name: 'Sarah-Windows-Desktop',
    type: DEVICE_TYPES.DESKTOP,
    os: OS_TYPES.WINDOWS,
    version: 'Windows 11 Pro',
    employee: 'Sarah Johnson',
    department: 'Design',
    status: DEVICE_STATUS.WARNING,
    lastSeen: '2024-01-15T10:25:00Z',
    ipAddress: '192.168.1.102',
    macAddress: '00:1B:44:11:3A:B8',
    location: 'New York, NY',
    specs: {
      cpu: 'Intel i7-12700K',
      memory: '32 GB DDR4',
      storage: '1 TB NVMe SSD',
      gpu: 'NVIDIA RTX 3070'
    },
    performance: {
      cpu: 78,
      memory: 89,
      disk: 45,
      temperature: 72
    },
    security: {
      antivirus: true,
      firewall: true,
      encrypted: false,
      lastUpdate: '2024-01-10T14:30:00Z'
    },
    installed: true
  },
  {
    id: 'DEV003',
    name: 'Mike-iPhone-14',
    type: DEVICE_TYPES.MOBILE,
    os: OS_TYPES.IOS,
    version: 'iOS 17.2',
    employee: 'Mike Davis',
    department: 'Sales',
    status: DEVICE_STATUS.ONLINE,
    lastSeen: '2024-01-15T10:28:00Z',
    ipAddress: '192.168.1.103',
    location: 'Chicago, IL',
    specs: {
      model: 'iPhone 14 Pro',
      storage: '256 GB',
      screen: '6.1-inch Super Retina XDR'
    },
    performance: {
      battery: 87,
      storage: 65,
      signal: 95
    },
    security: {
      passcode: true,
      biometric: true,
      encrypted: true,
      lastUpdate: '2024-01-14T20:15:00Z'
    },
    installed: false
  }
];

const mockCompanyStats = {
  totalDevices: 47,
  onlineDevices: 42,
  offlineDevices: 3,
  warningDevices: 2,
  criticalDevices: 0,
  departments: {
    'Engineering': 18,
    'Design': 12,
    'Sales': 10,
    'Marketing': 7
  },
  deviceTypes: {
    'laptop': 25,
    'desktop': 15,
    'mobile': 35,
    'tablet': 8,
    'server': 4
  }
};

// Utility functions
const getDeviceIcon = (type) => {
  switch (type) {
    case DEVICE_TYPES.LAPTOP: return <LaptopIcon />;
    case DEVICE_TYPES.DESKTOP: return <ComputerIcon />;
    case DEVICE_TYPES.MOBILE: return <PhoneIcon />;
    case DEVICE_TYPES.TABLET: return <TabletIcon />;
    case DEVICE_TYPES.SERVER: return <StorageIcon />;
    default: return <ComputerIcon />;
  }
};

const getStatusColor = (status) => {
  switch (status) {
    case DEVICE_STATUS.ONLINE: return '#4caf50';
    case DEVICE_STATUS.WARNING: return '#ff9800';
    case DEVICE_STATUS.CRITICAL: return '#f44336';
    case DEVICE_STATUS.OFFLINE: return '#9e9e9e';
    case DEVICE_STATUS.MAINTENANCE: return '#2196f3';
    default: return '#9e9e9e';
  }
};

const getStatusIcon = (status) => {
  switch (status) {
    case DEVICE_STATUS.ONLINE: return <SuccessIcon />;
    case DEVICE_STATUS.WARNING: return <WarningIcon />;
    case DEVICE_STATUS.CRITICAL: return <ErrorIcon />;
    default: return <ErrorIcon />;
  }
};

// Main Device Management Portal Component
const DeviceManagementPortal = () => {
  const [devices, setDevices] = useState(USE_MOCKS ? mockDevices : []);
  const [selectedTab, setSelectedTab] = useState(0);
  const [companyStats, setCompanyStats] = useState(USE_MOCKS ? mockCompanyStats : null);
  
  const computeStats = (list = []) => {
    const total = list.length;
    const online = list.filter(d => d.status === 'online').length;
    const warning = list.filter(d => d.status === 'warning').length;
    const critical = list.filter(d => d.status === 'critical').length;
    const offline = Math.max(0, total - online - warning - critical);
    return { totalDevices: total, onlineDevices: online, warningDevices: warning, criticalDevices: critical, offlineDevices: offline };
  };
  // Load from backend when mocks disabled
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (USE_MOCKS) return; // keep mocks in dev when flag is on
      try {
        const list = await apiService.getDevices();
        if (!cancelled && Array.isArray(list)) {
          setDevices(list.length ? list : []);
        }
      } catch (e) {
        console.warn('getDevices failed; staying with current state');
      }
      try {
        const stats = await apiService.getCompanyStats();
        if (!cancelled) {
          if (stats && stats.totalDevices !== undefined) setCompanyStats(stats);
          else setCompanyStats(computeStats(devices));
        }
      } catch (e) {
        if (!cancelled) setCompanyStats(computeStats(devices));
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);
  const [addDeviceOpen, setAddDeviceOpen] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [deviceDetailsOpen, setDeviceDetailsOpen] = useState(false);
  const [installAgentOpen, setInstallAgentOpen] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterDepartment, setFilterDepartment] = useState('all');

  // Device Overview Component
  const DeviceOverview = () => {
    // Filter devices based on selected filters
    const filteredDevices = devices.filter(device => {
      const statusMatch = filterStatus === 'all' || device.status === filterStatus;
      const departmentMatch = filterDepartment === 'all' || device.department === filterDepartment;
      return statusMatch && departmentMatch;
    });

    return (
    <Grid container spacing={3}>
      {/* Quick Stats Cards */}
      <Grid item xs={12} md={2.4}>
        <Card sx={{ bgcolor: '#4caf50', color: 'white' }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <Typography variant="h3">{(companyStats?.totalDevices ?? computeStats(devices).totalDevices)}</Typography>
            <Typography variant="subtitle1">Total Devices</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={2.4}>
        <Card sx={{ bgcolor: '#4caf50', color: 'white' }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <Typography variant="h3">{(companyStats?.onlineDevices ?? computeStats(devices).onlineDevices)}</Typography>
            <Typography variant="subtitle1">Online</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={2.4}>
        <Card sx={{ bgcolor: '#ff9800', color: 'white' }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <Typography variant="h3">{(companyStats?.warningDevices ?? computeStats(devices).warningDevices)}</Typography>
            <Typography variant="subtitle1">Warning</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={2.4}>
        <Card sx={{ bgcolor: '#9e9e9e', color: 'white' }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <Typography variant="h3">{(companyStats?.offlineDevices ?? computeStats(devices).offlineDevices)}</Typography>
            <Typography variant="subtitle1">Offline</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={2.4}>
        <Card sx={{ bgcolor: '#f44336', color: 'white' }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <Typography variant="h3">{(companyStats?.criticalDevices ?? computeStats(devices).criticalDevices)}</Typography>
            <Typography variant="subtitle1">Critical</Typography>
          </CardContent>
        </Card>
      </Grid>

      {/* Filters */}
      <Grid item xs={12}>
        <Paper sx={{ p: 2 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Filter by Status</InputLabel>
                <Select
                  value={filterStatus}
                  label="Filter by Status"
                  onChange={(e) => setFilterStatus(e.target.value)}
                >
                  <MenuItem value="all">All Status</MenuItem>
                  <MenuItem value="online">Online</MenuItem>
                  <MenuItem value="warning">Warning</MenuItem>
                  <MenuItem value="offline">Offline</MenuItem>
                  <MenuItem value="critical">Critical</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Filter by Department</InputLabel>
                <Select
                  value={filterDepartment}
                  label="Filter by Department"
                  onChange={(e) => setFilterDepartment(e.target.value)}
                >
                  <MenuItem value="all">All Departments</MenuItem>
                  <MenuItem value="Engineering">Engineering</MenuItem>
                  <MenuItem value="Design">Design</MenuItem>
                  <MenuItem value="Sales">Sales</MenuItem>
                  <MenuItem value="Marketing">Marketing</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={2}>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setAddDeviceOpen(true)}
                fullWidth
              >
                Add Device
              </Button>
            </Grid>
            <Grid item xs={12} md={2}>
              <Button
                variant="outlined"
                startIcon={<InstallIcon />}
                onClick={() => setInstallAgentOpen(true)}
                fullWidth
              >
                Install Agent
              </Button>
            </Grid>
            <Grid item xs={12} md={2}>
              <Chip 
                label={`Showing ${filteredDevices.length} of ${devices.length} devices`} 
                color="primary" 
                variant="outlined"
              />
            </Grid>
          </Grid>
        </Paper>
      </Grid>

      {/* Device Table */}
      <Grid item xs={12}>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ mb: 3 }}>
            Device Inventory 
            {(filterStatus !== 'all' || filterDepartment !== 'all') && (
              <Chip 
                label={`Filtered: ${filterStatus !== 'all' ? filterStatus : ''} ${filterDepartment !== 'all' ? filterDepartment : ''}`}
                size="small" 
                sx={{ ml: 2 }}
                onDelete={() => {
                  setFilterStatus('all');
                  setFilterDepartment('all');
                }}
              />
            )}
          </Typography>
          
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Device</TableCell>
                  <TableCell>Employee</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Performance</TableCell>
                  <TableCell>Security</TableCell>
                  <TableCell>Last Seen</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredDevices.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} align="center">
                      <Alert severity="info">
                        No devices match the selected filters. Try adjusting your filter criteria.
                      </Alert>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredDevices.map((device) => (
                  <TableRow key={device.id} hover>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        {getDeviceIcon(device.type)}
                        <Box>
                          <Typography variant="subtitle2">{device.name}</Typography>
                          <Typography variant="caption" color="textSecondary">
                            {device.os} • {device.type}
                          </Typography>
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box>
                        <Typography variant="body2">{device.employee}</Typography>
                        <Typography variant="caption" color="textSecondary">
                          {device.department}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Chip
                          icon={getStatusIcon(device.status)}
                          label={device.status}
                          size="small"
                          sx={{ bgcolor: getStatusColor(device.status), color: 'white' }}
                        />
                        {!device.installed && (
                          <Chip label="Agent Not Installed" size="small" color="warning" />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ width: 120 }}>
                        {device.performance.cpu !== undefined && (
                          <>
                            <Typography variant="caption">CPU: {device.performance.cpu}%</Typography>
                            <LinearProgress
                              variant="determinate"
                              value={device.performance.cpu}
                              size="small"
                              sx={{ mb: 0.5 }}
                            />
                          </>
                        )}
                        {device.performance.memory !== undefined && (
                          <>
                            <Typography variant="caption">MEM: {device.performance.memory}%</Typography>
                            <LinearProgress
                              variant="determinate"
                              value={device.performance.memory}
                              size="small"
                            />
                          </>
                        )}
                        {device.performance.battery !== undefined && (
                          <>
                            <Typography variant="caption">BAT: {device.performance.battery}%</Typography>
                            <LinearProgress
                              variant="determinate"
                              value={device.performance.battery}
                              size="small"
                            />
                          </>
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        {device.security.antivirus && (
                          <Tooltip title="Antivirus Active">
                            <SecurityIcon color="success" fontSize="small" />
                          </Tooltip>
                        )}
                        {device.security.firewall && (
                          <Tooltip title="Firewall Enabled">
                            <NetworkIcon color="success" fontSize="small" />
                          </Tooltip>
                        )}
                        {device.security.encrypted && (
                          <Tooltip title="Disk Encrypted">
                            <StorageIcon color="success" fontSize="small" />
                          </Tooltip>
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {new Date(device.lastSeen).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <Tooltip title="View Details">
                          <IconButton
                            size="small"
                            onClick={() => {
                              setSelectedDevice(device);
                              setDeviceDetailsOpen(true);
                            }}
                          >
                            <ViewIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Edit Device">
                          <IconButton size="small">
                            <EditIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Device Settings">
                          <IconButton size="small">
                            <SettingsIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Remove Device">
                          <IconButton size="small" color="error">
                            <DeleteIcon />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Grid>
    </Grid>
    );
  };

  // Analytics Component
  const Analytics = () => (
    <Grid container spacing={3}>
      {/* Department Breakdown */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <GroupIcon /> Department Distribution
            </Typography>
            <List dense>
              {Object.entries(mockCompanyStats.departments).map(([dept, count]) => (
                <ListItem key={dept}>
                  <ListItemIcon>
                    <BusinessIcon />
                  </ListItemIcon>
                  <ListItemText
                    primary={dept}
                    secondary={`${count} devices`}
                  />
                  <Typography variant="body2">
                    {Math.round((count / mockCompanyStats.totalDevices) * 100)}%
                  </Typography>
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      </Grid>

      {/* Device Types */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <ComputerIcon /> Device Types
            </Typography>
            <List dense>
              {Object.entries(mockCompanyStats.deviceTypes).map(([type, count]) => (
                <ListItem key={type}>
                  <ListItemIcon>
                    {getDeviceIcon(type)}
                  </ListItemIcon>
                  <ListItemText
                    primary={type.charAt(0).toUpperCase() + type.slice(1)}
                    secondary={`${count} devices`}
                  />
                  <Typography variant="body2">
                    {Math.round((count / mockCompanyStats.totalDevices) * 100)}%
                  </Typography>
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      </Grid>

      {/* Security Overview */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <SecurityIcon /> Security Status
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h4" color="success.main">
                    {devices.filter(d => d.security.antivirus).length}
                  </Typography>
                  <Typography variant="subtitle2">Antivirus Protected</Typography>
                </Box>
              </Grid>
              <Grid item xs={12} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h4" color="success.main">
                    {devices.filter(d => d.security.firewall).length}
                  </Typography>
                  <Typography variant="subtitle2">Firewall Enabled</Typography>
                </Box>
              </Grid>
              <Grid item xs={12} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h4" color="success.main">
                    {devices.filter(d => d.security.encrypted).length}
                  </Typography>
                  <Typography variant="subtitle2">Disk Encrypted</Typography>
                </Box>
              </Grid>
              <Grid item xs={12} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h4" color="warning.main">
                    {devices.filter(d => !d.installed).length}
                  </Typography>
                  <Typography variant="subtitle2">Agent Missing</Typography>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
        <ComputerIcon color="primary" />
        Device Management Portal
      </Typography>

      <Tabs value={selectedTab} onChange={(e, newValue) => setSelectedTab(newValue)} sx={{ mb: 3 }}>
        <Tab label="Device Overview" />
        <Tab label="Analytics" />
        <Tab label="Agent Deployment" />
      </Tabs>

      <AnimatePresence mode="wait">
        <motion.div
          key={selectedTab}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
        >
          {selectedTab === 0 && <DeviceOverview />}
          {selectedTab === 1 && <Analytics />}
          {selectedTab === 2 && (
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>Agent Deployment</Typography>
              <Alert severity="info" sx={{ mb: 2 }}>
                Deploy the AIOps monitoring agent to devices for real-time monitoring and management.
              </Alert>
              <Button variant="contained" startIcon={<InstallIcon />}>
                Generate Installation Package
              </Button>
            </Paper>
          )}
        </motion.div>
      </AnimatePresence>

      {/* Add Device Dialog */}
      <Dialog open={addDeviceOpen} onClose={() => setAddDeviceOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Add New Device</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Device Name" />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Device Type</InputLabel>
                <Select label="Device Type">
                  <MenuItem value="laptop">Laptop</MenuItem>
                  <MenuItem value="desktop">Desktop</MenuItem>
                  <MenuItem value="mobile">Mobile</MenuItem>
                  <MenuItem value="tablet">Tablet</MenuItem>
                  <MenuItem value="server">Server</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Employee Name" />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Department" />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="IP Address" />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="MAC Address" />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={<Switch />}
                label="Install monitoring agent automatically"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDeviceOpen(false)}>Cancel</Button>
          <Button variant="contained">Add Device</Button>
        </DialogActions>
      </Dialog>

      {/* Device Details Dialog */}
      <Dialog 
        open={deviceDetailsOpen} 
        onClose={() => setDeviceDetailsOpen(false)} 
        maxWidth="lg" 
        fullWidth
      >
        {selectedDevice && (
          <>
            <DialogTitle>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {getDeviceIcon(selectedDevice.type)}
                {selectedDevice.name}
                <Chip
                  icon={getStatusIcon(selectedDevice.status)}
                  label={selectedDevice.status}
                  size="small"
                  sx={{ bgcolor: getStatusColor(selectedDevice.status), color: 'white' }}
                />
              </Box>
            </DialogTitle>
            <DialogContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>Device Information</Typography>
                  <Typography><strong>Employee:</strong> {selectedDevice.employee}</Typography>
                  <Typography><strong>Department:</strong> {selectedDevice.department}</Typography>
                  <Typography><strong>OS:</strong> {selectedDevice.version}</Typography>
                  <Typography><strong>IP Address:</strong> {selectedDevice.ipAddress}</Typography>
                  <Typography><strong>Location:</strong> {selectedDevice.location}</Typography>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>Specifications</Typography>
                  {Object.entries(selectedDevice.specs).map(([key, value]) => (
                    <Typography key={key}>
                      <strong>{key.toUpperCase()}:</strong> {value}
                    </Typography>
                  ))}
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="h6" gutterBottom>Security Status</Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={3}>
                      <Chip
                        label={`Antivirus: ${selectedDevice.security.antivirus ? 'Active' : 'Inactive'}`}
                        color={selectedDevice.security.antivirus ? 'success' : 'error'}
                      />
                    </Grid>
                    <Grid item xs={3}>
                      <Chip
                        label={`Firewall: ${selectedDevice.security.firewall ? 'Enabled' : 'Disabled'}`}
                        color={selectedDevice.security.firewall ? 'success' : 'error'}
                      />
                    </Grid>
                    <Grid item xs={3}>
                      <Chip
                        label={`Encryption: ${selectedDevice.security.encrypted ? 'Active' : 'Inactive'}`}
                        color={selectedDevice.security.encrypted ? 'success' : 'error'}
                      />
                    </Grid>
                    <Grid item xs={3}>
                      <Chip
                        label={`Agent: ${selectedDevice.installed ? 'Installed' : 'Missing'}`}
                        color={selectedDevice.installed ? 'success' : 'warning'}
                      />
                    </Grid>
                  </Grid>
                </Grid>
              </Grid>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setDeviceDetailsOpen(false)}>Close</Button>
              <Button variant="contained">Edit Device</Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      {/* Install Agent Dialog */}
      <Dialog open={installAgentOpen} onClose={() => setInstallAgentOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Install Monitoring Agent</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Select devices to install the AIOps monitoring agent for real-time system monitoring.
          </Alert>
          <List>
            {devices.filter(d => !d.installed).map((device) => (
              <ListItem key={device.id}>
                <ListItemIcon>
                  {getDeviceIcon(device.type)}
                </ListItemIcon>
                <ListItemText
                  primary={device.name}
                  secondary={`${device.employee} - ${device.department}`}
                />
                <Switch />
              </ListItem>
            ))}
          </List>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInstallAgentOpen(false)}>Cancel</Button>
          <Button variant="contained">Install Selected</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DeviceManagementPortal;