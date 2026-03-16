/*
Multi-Role Dashboard System
Admin and Employee portals with role-based access and device management
*/

import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  Chip,
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
  Avatar,
  IconButton,
  Badge,
  Tabs,
  Tab,
  Switch,
  FormControlLabel,
  Alert,
  Tooltip,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider
} from '@mui/material';
import {
  AdminPanelSettings as AdminIcon,
  Person as EmployeeIcon,
  Computer as DeviceIcon,
  Security as SecurityIcon,
  Dashboard as DashboardIcon,
  Analytics as AnalyticsIcon,
  Settings as SettingsIcon,
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Visibility as ViewIcon,
  Warning as WarningIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  BusinessCenter as CompanyIcon,
  Group as GroupIcon,
  Notifications as NotificationsIcon,
  Schedule as ScheduleIcon
} from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';
import { Lightbulb } from 'lucide-react';

// Role-based access control
const USER_ROLES = {
  ADMIN: 'admin',
  EMPLOYEE: 'employee',
  MANAGER: 'manager'
};

const PERMISSIONS = {
  VIEW_ALL_DEVICES: 'view_all_devices',
  MANAGE_DEVICES: 'manage_devices',
  VIEW_ANALYTICS: 'view_analytics',
  MANAGE_USERS: 'manage_users',
  SYSTEM_SETTINGS: 'system_settings',
  VIEW_OWN_DEVICE: 'view_own_device'
};

const ROLE_PERMISSIONS = {
  [USER_ROLES.ADMIN]: [
    PERMISSIONS.VIEW_ALL_DEVICES,
    PERMISSIONS.MANAGE_DEVICES,
    PERMISSIONS.VIEW_ANALYTICS,
    PERMISSIONS.MANAGE_USERS,
    PERMISSIONS.SYSTEM_SETTINGS,
    PERMISSIONS.VIEW_OWN_DEVICE
  ],
  [USER_ROLES.MANAGER]: [
    PERMISSIONS.VIEW_ALL_DEVICES,
    PERMISSIONS.VIEW_ANALYTICS,
    PERMISSIONS.VIEW_OWN_DEVICE
  ],
  [USER_ROLES.EMPLOYEE]: [
    PERMISSIONS.VIEW_OWN_DEVICE
  ]
};

// Mock data for demonstration
const mockDevices = [
  {
    id: 'DEV001',
    name: 'John-Laptop-Work',
    type: 'laptop',
    employee: 'John Smith',
    department: 'Engineering',
    status: 'healthy',
    cpu: 45,
    memory: 67,
    disk: 23,
    lastSeen: '2024-01-15T10:30:00Z',
    ip: '192.168.1.101',
    os: 'Windows 11 Pro'
  },
  {
    id: 'DEV002',
    name: 'Sarah-Desktop-Design',
    type: 'desktop',
    employee: 'Sarah Johnson',
    department: 'Design',
    status: 'warning',
    cpu: 78,
    memory: 89,
    disk: 91,
    lastSeen: '2024-01-15T10:25:00Z',
    ip: '192.168.1.102',
    os: 'macOS Ventura'
  },
  {
    id: 'DEV003',
    name: 'Mike-Laptop-Sales',
    type: 'laptop',
    employee: 'Mike Davis',
    department: 'Sales',
    status: 'critical',
    cpu: 95,
    memory: 94,
    disk: 8,
    lastSeen: '2024-01-15T09:45:00Z',
    ip: '192.168.1.103',
    os: 'Windows 10 Pro'
  }
];

const mockUsers = [
  {
    id: 'USER001',
    name: 'John Smith',
    email: 'john.smith@company.com',
    role: USER_ROLES.EMPLOYEE,
    department: 'Engineering',
    devices: ['DEV001'],
    lastLogin: '2024-01-15T08:30:00Z',
    active: true
  },
  {
    id: 'USER002',
    name: 'Sarah Johnson',
    email: 'sarah.johnson@company.com',
    role: USER_ROLES.MANAGER,
    department: 'Design',
    devices: ['DEV002'],
    lastLogin: '2024-01-15T09:15:00Z',
    active: true
  },
  {
    id: 'USER003',
    name: 'Mike Davis',
    email: 'mike.davis@company.com',
    role: USER_ROLES.EMPLOYEE,
    department: 'Sales',
    devices: ['DEV003'],
    lastLogin: '2024-01-15T07:20:00Z',
    active: false
  }
];

// Utility functions
const hasPermission = (userRole, permission) => {
  return ROLE_PERMISSIONS[userRole]?.includes(permission) || false;
};

const getStatusColor = (status) => {
  switch (status) {
    case 'healthy': return '#4caf50';
    case 'warning': return '#ff9800';
    case 'critical': return '#f44336';
    default: return '#9e9e9e';
  }
};

const getStatusIcon = (status) => {
  switch (status) {
    case 'healthy': return <SuccessIcon />;
    case 'warning': return <WarningIcon />;
    case 'critical': return <ErrorIcon />;
    default: return <DeviceIcon />;
  }
};

// Admin Dashboard Component
const AdminDashboard = ({ currentUser }) => {
  const [devices, setDevices] = useState(mockDevices);
  const [users, setUsers] = useState(mockUsers);
  const [selectedTab, setSelectedTab] = useState(0);
  const [addDeviceOpen, setAddDeviceOpen] = useState(false);
  const [addUserOpen, setAddUserOpen] = useState(false);

  const totalDevices = devices.length;
  const healthyDevices = devices.filter(d => d.status === 'healthy').length;
  const warningDevices = devices.filter(d => d.status === 'warning').length;
  const criticalDevices = devices.filter(d => d.status === 'critical').length;

  const DeviceOverview = () => (
    <Grid container spacing={3}>
      {/* Quick Stats */}
      <Grid item xs={12} md={3}>
        <Card sx={{ bgcolor: '#4caf50', color: 'white' }}>
          <CardContent>
            <Typography variant="h4">{totalDevices}</Typography>
            <Typography variant="subtitle1">Total Devices</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={3}>
        <Card sx={{ bgcolor: '#4caf50', color: 'white' }}>
          <CardContent>
            <Typography variant="h4">{healthyDevices}</Typography>
            <Typography variant="subtitle1">Healthy</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={3}>
        <Card sx={{ bgcolor: '#ff9800', color: 'white' }}>
          <CardContent>
            <Typography variant="h4">{warningDevices}</Typography>
            <Typography variant="subtitle1">Warning</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={3}>
        <Card sx={{ bgcolor: '#f44336', color: 'white' }}>
          <CardContent>
            <Typography variant="h4">{criticalDevices}</Typography>
            <Typography variant="subtitle1">Critical</Typography>
          </CardContent>
        </Card>
      </Grid>

      {/* Device Management Table */}
      <Grid item xs={12}>
        <Paper sx={{ p: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h6">Device Management</Typography>
            {hasPermission(currentUser.role, PERMISSIONS.MANAGE_DEVICES) && (
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setAddDeviceOpen(true)}
              >
                Add Device
              </Button>
            )}
          </Box>
          
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Device</TableCell>
                  <TableCell>Employee</TableCell>
                  <TableCell>Department</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Performance</TableCell>
                  <TableCell>Last Seen</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {devices.map((device) => (
                  <TableRow key={device.id}>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <DeviceIcon />
                        <Box>
                          <Typography variant="subtitle2">{device.name}</Typography>
                          <Typography variant="caption" color="textSecondary">
                            {device.type} • {device.os}
                          </Typography>
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell>{device.employee}</TableCell>
                    <TableCell>{device.department}</TableCell>
                    <TableCell>
                      <Chip
                        icon={getStatusIcon(device.status)}
                        label={device.status}
                        size="small"
                        sx={{ bgcolor: getStatusColor(device.status), color: 'white' }}
                      />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ width: 100 }}>
                        <Typography variant="caption">CPU: {device.cpu}%</Typography>
                        <Typography variant="caption" display="block">MEM: {device.memory}%</Typography>
                        <Typography variant="caption" display="block">DISK: {device.disk}%</Typography>
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
                          <IconButton size="small">
                            <ViewIcon />
                          </IconButton>
                        </Tooltip>
                        {hasPermission(currentUser.role, PERMISSIONS.MANAGE_DEVICES) && (
                          <>
                            <Tooltip title="Edit">
                              <IconButton size="small">
                                <EditIcon />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Remove">
                              <IconButton size="small" color="error">
                                <DeleteIcon />
                              </IconButton>
                            </Tooltip>
                          </>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Grid>
    </Grid>
  );

  const UserManagement = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Paper sx={{ p: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h6">User Management</Typography>
            {hasPermission(currentUser.role, PERMISSIONS.MANAGE_USERS) && (
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setAddUserOpen(true)}
              >
                Add User
              </Button>
            )}
          </Box>

          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>User</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>Department</TableCell>
                  <TableCell>Devices</TableCell>
                  <TableCell>Last Login</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Avatar>{user.name.charAt(0)}</Avatar>
                        <Box>
                          <Typography variant="subtitle2">{user.name}</Typography>
                          <Typography variant="caption" color="textSecondary">
                            {user.email}
                          </Typography>
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={user.role}
                        size="small"
                        color={user.role === USER_ROLES.ADMIN ? 'error' : 
                               user.role === USER_ROLES.MANAGER ? 'warning' : 'default'}
                      />
                    </TableCell>
                    <TableCell>{user.department}</TableCell>
                    <TableCell>
                      <Badge badgeContent={user.devices.length} color="primary">
                        <DeviceIcon />
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {new Date(user.lastLogin).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={user.active ? 'Active' : 'Inactive'}
                        size="small"
                        color={user.active ? 'success' : 'default'}
                      />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <Tooltip title="View Profile">
                          <IconButton size="small">
                            <ViewIcon />
                          </IconButton>
                        </Tooltip>
                        {hasPermission(currentUser.role, PERMISSIONS.MANAGE_USERS) && (
                          <>
                            <Tooltip title="Edit User">
                              <IconButton size="small">
                                <EditIcon />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Deactivate">
                              <IconButton size="small" color="error">
                                <DeleteIcon />
                              </IconButton>
                            </Tooltip>
                          </>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Grid>
    </Grid>
  );

  const Analytics = () => (
    <Grid container spacing={3}>
      <Grid item xs={12} md={4}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Department Overview</Typography>
            <List dense>
              <ListItem>
                <ListItemText primary="Engineering" secondary="5 devices, 2 warnings" />
              </ListItem>
              <ListItem>
                <ListItemText primary="Design" secondary="3 devices, 1 critical" />
              </ListItem>
              <ListItem>
                <ListItemText primary="Sales" secondary="4 devices, all healthy" />
              </ListItem>
            </List>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={4}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Performance Trends</Typography>
            <Typography variant="body2" color="textSecondary">
              • Average CPU: 62%<br/>
              • Average Memory: 74%<br/>
              • Average Disk: 45%<br/>
              • Uptime: 99.2%
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={4}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Recent Alerts</Typography>
            <List dense>
              <ListItem>
                <ListItemIcon>
                  <ErrorIcon color="error" />
                </ListItemIcon>
                <ListItemText 
                  primary="High Memory Usage" 
                  secondary="Sarah-Desktop-Design"
                />
              </ListItem>
              <ListItem>
                <ListItemIcon>
                  <WarningIcon color="warning" />
                </ListItemIcon>
                <ListItemText 
                  primary="Low Disk Space" 
                  secondary="Mike-Laptop-Sales"
                />
              </ListItem>
            </List>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
        <AdminIcon color="error" />
        Admin Dashboard
      </Typography>

      <Tabs value={selectedTab} onChange={(e, newValue) => setSelectedTab(newValue)} sx={{ mb: 3 }}>
        <Tab label="Device Overview" />
        {hasPermission(currentUser.role, PERMISSIONS.MANAGE_USERS) && (
          <Tab label="User Management" />
        )}
        {hasPermission(currentUser.role, PERMISSIONS.VIEW_ANALYTICS) && (
          <Tab label="Analytics" />
        )}
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
          {selectedTab === 1 && hasPermission(currentUser.role, PERMISSIONS.MANAGE_USERS) && <UserManagement />}
          {selectedTab === 2 && hasPermission(currentUser.role, PERMISSIONS.VIEW_ANALYTICS) && <Analytics />}
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
              <TextField fullWidth label="Device Type" />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Employee" />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Department" />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="IP Address" />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDeviceOpen(false)}>Cancel</Button>
          <Button variant="contained">Add Device</Button>
        </DialogActions>
      </Dialog>

      {/* Add User Dialog */}
      <Dialog open={addUserOpen} onClose={() => setAddUserOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Add New User</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Full Name" />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Email" type="email" />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Role" select />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField fullWidth label="Department" />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddUserOpen(false)}>Cancel</Button>
          <Button variant="contained">Add User</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

// Employee Dashboard Component
const EmployeeDashboard = ({ currentUser }) => {
  const userDevices = mockDevices.filter(device => 
    mockUsers.find(user => user.id === currentUser.id)?.devices.includes(device.id)
  );

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
        <EmployeeIcon color="primary" />
        My Dashboard
      </Typography>

      <Grid container spacing={3}>
        {/* Welcome Card */}
        <Grid item xs={12}>
          <Card sx={{ bgcolor: 'primary.main', color: 'primary.contrastText' }}>
            <CardContent>
              <Typography variant="h5" gutterBottom>
                Welcome back, {currentUser.name}!
              </Typography>
              <Typography variant="body1">
                Monitor your device performance and receive real-time insights.
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* My Devices */}
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ mb: 3 }}>My Devices</Typography>
            
            {userDevices.length > 0 ? (
              <Grid container spacing={2}>
                {userDevices.map((device) => (
                  <Grid item xs={12} md={6} lg={4} key={device.id}>
                    <Card>
                      <CardContent>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                          <Typography variant="h6">{device.name}</Typography>
                          <Chip
                            icon={getStatusIcon(device.status)}
                            label={device.status}
                            size="small"
                            sx={{ bgcolor: getStatusColor(device.status), color: 'white' }}
                          />
                        </Box>
                        
                        <Typography variant="body2" color="textSecondary" gutterBottom>
                          {device.type} • {device.os}
                        </Typography>
                        
                        <Box sx={{ mt: 2 }}>
                          <Typography variant="body2">CPU: {device.cpu}%</Typography>
                          <Typography variant="body2">Memory: {device.memory}%</Typography>
                          <Typography variant="body2">Disk: {device.disk}%</Typography>
                        </Box>
                        
                        <Typography variant="caption" color="textSecondary" display="block" sx={{ mt: 2 }}>
                          Last updated: {new Date(device.lastSeen).toLocaleString()}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            ) : (
              <Alert severity="info">
                No devices assigned to your account. Contact your administrator for device setup.
              </Alert>
            )}
          </Paper>
        </Grid>

        {/* Performance Summary */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Performance Summary</Typography>
              {userDevices.length > 0 ? (
                <Box>
                  <Typography variant="body2">
                    Average CPU: {Math.round(userDevices.reduce((acc, d) => acc + d.cpu, 0) / userDevices.length)}%
                  </Typography>
                  <Typography variant="body2">
                    Average Memory: {Math.round(userDevices.reduce((acc, d) => acc + d.memory, 0) / userDevices.length)}%
                  </Typography>
                  <Typography variant="body2">
                    Average Disk: {Math.round(userDevices.reduce((acc, d) => acc + d.disk, 0) / userDevices.length)}%
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="textSecondary">
                  No performance data available
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Quick Actions */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Quick Actions</Typography>
              <List dense>
                <ListItem button>
                  <ListItemIcon>
                    <NotificationsIcon />
                  </ListItemIcon>
                  <ListItemText primary="View Alerts" />
                </ListItem>
                <ListItem button>
                  <ListItemIcon>
                    <ScheduleIcon />
                  </ListItemIcon>
                  <ListItemText primary="Schedule Maintenance" />
                </ListItem>
                <ListItem button>
                  <ListItemIcon>
                    <SettingsIcon />
                  </ListItemIcon>
                  <ListItemText primary="Device Settings" />
                </ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

// Main Multi-Role Dashboard Component
const MultiRoleDashboard = () => {
  const [currentUser, setCurrentUser] = useState({
    id: 'USER001',
    name: 'John Smith',
    email: 'john.smith@company.com',
    role: USER_ROLES.ADMIN, // Change this to test different roles
    department: 'Engineering'
  });

  const [roleSelectionOpen, setRoleSelectionOpen] = useState(false);

  const handleRoleChange = (newRole) => {
    setCurrentUser({ ...currentUser, role: newRole });
    setRoleSelectionOpen(false);
  };

  const getRoleDashboard = () => {
    switch (currentUser.role) {
      case USER_ROLES.ADMIN:
      case USER_ROLES.MANAGER:
        return <AdminDashboard currentUser={currentUser} />;
      case USER_ROLES.EMPLOYEE:
        return <EmployeeDashboard currentUser={currentUser} />;
      default:
        return <EmployeeDashboard currentUser={currentUser} />;
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Multi-Role Portal Explanation */}
      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <SecurityIcon /> Multi-Role Portal Overview
        </Typography>
        <Typography variant="body2" sx={{ mb: 2 }}>
          The Multi-Role Portal provides <strong>role-based access control</strong> for different user types within your organization. 
          Each role has specific permissions and sees customized dashboards tailored to their responsibilities.
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <AdminIcon color="error" />
              <Typography variant="subtitle2" color="error.main">Admin Role</Typography>
            </Box>
            <Typography variant="caption">
              • Full system access and device management<br/>
              • User management and security controls<br/>
              • Analytics and system settings<br/>
              • Company-wide device oversight
            </Typography>
          </Grid>
          <Grid item xs={12} md={4}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <GroupIcon color="primary" />
              <Typography variant="subtitle2" color="primary.main">Manager Role</Typography>
            </Box>
            <Typography variant="caption">
              • Department device visibility<br/>
              • Team analytics and reports<br/>
              • Employee device status<br/>
              • Limited administrative access
            </Typography>
          </Grid>
          <Grid item xs={12} md={4}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <EmployeeIcon color="success" />
              <Typography variant="subtitle2" color="success.main">Employee Role</Typography>
            </Box>
            <Typography variant="caption">
              • Personal device management<br/>
              • Self-service IT requests<br/>
              • Own device performance monitoring<br/>
              • Basic system notifications
            </Typography>
          </Grid>
        </Grid>
        <Typography variant="caption" sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 0.5, fontStyle: 'italic' }}>
          <Lightbulb size={14} /> Use the "Change Role" button below to switch between different user perspectives and explore role-based features.
        </Typography>
      </Alert>

      {/* Role Indicator */}
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        mb: 3,
        p: 2,
        bgcolor: 'background.paper',
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Avatar sx={{ bgcolor: currentUser.role === USER_ROLES.ADMIN ? 'error.main' : 'primary.main' }}>
            {currentUser.role === USER_ROLES.ADMIN ? <AdminIcon /> : <EmployeeIcon />}
          </Avatar>
          <Box>
            <Typography variant="h6">{currentUser.name}</Typography>
            <Typography variant="body2" color="textSecondary">
              {currentUser.role.toUpperCase()} • {currentUser.department}
            </Typography>
          </Box>
        </Box>
        
        <Button
          variant="outlined"
          onClick={() => setRoleSelectionOpen(true)}
          startIcon={<SecurityIcon />}
        >
          Change Role (Demo)
        </Button>
      </Box>

      {/* Role-based Dashboard */}
      {getRoleDashboard()}

      {/* Role Selection Dialog */}
      <Dialog open={roleSelectionOpen} onClose={() => setRoleSelectionOpen(false)}>
        <DialogTitle>Select Role (Demo Purpose)</DialogTitle>
        <DialogContent>
          <List>
            <ListItem button onClick={() => handleRoleChange(USER_ROLES.ADMIN)}>
              <ListItemIcon>
                <AdminIcon color="error" />
              </ListItemIcon>
              <ListItemText 
                primary="Administrator" 
                secondary="Full access to all features and device management" 
              />
            </ListItem>
            <Divider />
            <ListItem button onClick={() => handleRoleChange(USER_ROLES.MANAGER)}>
              <ListItemIcon>
                <GroupIcon color="warning" />
              </ListItemIcon>
              <ListItemText 
                primary="Manager" 
                secondary="View all devices and analytics, limited management" 
              />
            </ListItem>
            <Divider />
            <ListItem button onClick={() => handleRoleChange(USER_ROLES.EMPLOYEE)}>
              <ListItemIcon>
                <EmployeeIcon color="primary" />
              </ListItemIcon>
              <ListItemText 
                primary="Employee" 
                secondary="View only personal devices and performance" 
              />
            </ListItem>
          </List>
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default MultiRoleDashboard;