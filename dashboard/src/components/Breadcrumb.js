import React from 'react';
import {
  Breadcrumbs,
  Link,
  Typography,
  Box,
  Chip,
  useTheme
} from '@mui/material';
import {
  Home as HomeIcon,
  Dashboard as DashboardIcon,
  Computer as ComputerIcon,
  Psychology as AiIcon,
  Security as SecurityIcon,
  DevicesOther as DevicesIcon,
  Settings as SettingsIcon,
  NavigateNext as NavigateNextIcon
} from '@mui/icons-material';

const Breadcrumb = ({ activeTab, onTabChange }) => {
  const theme = useTheme();

  const getTabConfig = (tabId) => {
    const configs = {
      dashboard: {
        label: 'Dashboard',
        icon: <DashboardIcon fontSize="small" />,
        description: 'System overview and real-time monitoring'
      },
      systems: {
        label: 'Systems',
        icon: <ComputerIcon fontSize="small" />,
        description: 'Detailed system specifications and performance'
      },
      ai: {
        label: 'AI Insights',
        icon: <AiIcon fontSize="small" />,
        description: 'AI-powered analysis and recommendations'
      },
      roles: {
        label: 'Multi-Role Portal',
        icon: <SecurityIcon fontSize="small" />,
        description: 'Role-based access and management'
      },
      devices: {
        label: 'Device Management',
        icon: <DevicesIcon fontSize="small" />,
        description: 'Manage and monitor connected devices'
      },
      settings: {
        label: 'Settings',
        icon: <SettingsIcon fontSize="small" />,
        description: 'Configuration and preferences'
      }
    };
    return configs[tabId] || { label: tabId, icon: null, description: '' };
  };

  const currentConfig = getTabConfig(activeTab);

  return (
    <Box sx={{
      mb: 3,
      p: 2,
      background: theme.palette.mode === 'dark' 
        ? 'rgba(255, 255, 255, 0.02)'
        : 'rgba(0, 0, 0, 0.02)',
      border: `1px solid ${theme.palette.divider}`,
      borderRadius: 2,
      transition: 'all 0.3s ease'
    }}>
      <Breadcrumbs
        separator={<NavigateNextIcon fontSize="small" />}
        aria-label="breadcrumb"
        sx={{ mb: 1 }}
      >
        <Link
          component="button"
          variant="body2"
          onClick={() => onTabChange('dashboard')}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            color: activeTab === 'dashboard' ? theme.palette.primary.main : theme.palette.text.secondary,
            textDecoration: 'none',
            '&:hover': {
              color: theme.palette.primary.main,
              textDecoration: 'underline'
            }
          }}
        >
          <HomeIcon fontSize="small" />
          AIOps Bot
        </Link>
        
        {activeTab !== 'dashboard' && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            {currentConfig.icon}
            <Typography 
              variant="body2" 
              color="textPrimary"
              sx={{ fontWeight: 500 }}
            >
              {currentConfig.label}
            </Typography>
          </Box>
        )}
      </Breadcrumbs>
      
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="caption" color="textSecondary">
          {currentConfig.description}
        </Typography>
        
        <Chip 
          label={`${activeTab.charAt(0).toUpperCase()}${activeTab.slice(1)} View`}
          size="small"
          variant="outlined"
          sx={{
            fontWeight: 500,
            textTransform: 'capitalize'
          }}
        />
      </Box>
    </Box>
  );
};

export default Breadcrumb;