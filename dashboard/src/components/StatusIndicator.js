import React from 'react';
import { Chip, Box, useTheme } from '@mui/material';
import { motion } from 'framer-motion';

const StatusIndicator = ({ 
  status = 'healthy', 
  label = 'System Status',
  size = 'medium',
  showPulse = true 
}) => {
  const theme = useTheme();

  const getStatusConfig = (status) => {
    switch (status.toLowerCase()) {
      case 'healthy':
      case 'online':
      case 'active':
      case 'running':
        return {
          color: '#00d4aa',
          bgColor: 'rgba(0, 212, 170, 0.1)',
          icon: '●',
          text: status
        };
      case 'warning':
      case 'degraded':
      case 'unstable':
        return {
          color: '#ffd93d',
          bgColor: 'rgba(255, 217, 61, 0.1)',
          icon: '⚠',
          text: status
        };
      case 'critical':
      case 'error':
      case 'offline':
      case 'down':
        return {
          color: '#ff6b6b',
          bgColor: 'rgba(255, 107, 107, 0.1)',
          icon: '●',
          text: status
        };
      case 'maintenance':
      case 'updating':
        return {
          color: '#4fc3f7',
          bgColor: 'rgba(79, 195, 247, 0.1)',
          icon: '⊙',
          text: status
        };
      case 'unknown':
      case 'pending':
        return {
          color: '#9e9e9e',
          bgColor: 'rgba(158, 158, 158, 0.1)',
          icon: '?',
          text: status
        };
      default:
        return {
          color: '#4fc3f7',
          bgColor: 'rgba(79, 195, 247, 0.1)',
          icon: '●',
          text: status
        };
    }
  };

  const config = getStatusConfig(status);
  
  const pulseVariants = {
    pulse: {
      scale: [1, 1.2, 1],
      opacity: [1, 0.7, 1],
      transition: {
        duration: 2,
        repeat: Infinity,
        ease: "easeInOut"
      }
    }
  };

  const chipVariants = {
    initial: { scale: 0.8, opacity: 0 },
    animate: { 
      scale: 1, 
      opacity: 1,
      transition: {
        type: "spring",
        stiffness: 500,
        damping: 30
      }
    },
    hover: {
      scale: 1.05,
      transition: {
        type: "spring",
        stiffness: 400,
        damping: 25
      }
    }
  };

  return (
    <motion.div
      variants={chipVariants}
      initial="initial"
      animate="animate"
      whileHover="hover"
    >
      <Chip
        icon={
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {showPulse && (status === 'healthy' || status === 'online' || status === 'active' || status === 'running') ? (
              <motion.span
                variants={pulseVariants}
                animate="pulse"
                style={{ 
                  color: config.color,
                  fontSize: size === 'small' ? '8px' : size === 'large' ? '12px' : '10px',
                  marginRight: '4px'
                }}
              >
                {config.icon}
              </motion.span>
            ) : (
              <span style={{ 
                color: config.color,
                fontSize: size === 'small' ? '8px' : size === 'large' ? '12px' : '10px',
                marginRight: '4px'
              }}>
                {config.icon}
              </span>
            )}
          </Box>
        }
        label={
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <span style={{ 
              fontWeight: 600,
              textTransform: 'capitalize',
              fontSize: size === 'small' ? '0.75rem' : size === 'large' ? '0.875rem' : '0.8rem'
            }}>
              {label}: {config.text}
            </span>
          </Box>
        }
        size={size}
        sx={{
          backgroundColor: config.bgColor,
          color: config.color,
          border: `1px solid ${config.color}30`,
          fontWeight: 600,
          backdropFilter: 'blur(10px)',
          '& .MuiChip-icon': {
            color: config.color
          },
          '&:hover': {
            backgroundColor: `${config.color}20`,
            boxShadow: `0 0 20px ${config.color}40`
          },
          transition: 'all 0.3s ease'
        }}
      />
    </motion.div>
  );
};

// Predefined status indicators for common use cases
export const SystemStatus = ({ status }) => (
  <StatusIndicator status={status} label="System" />
);

export const ServiceStatus = ({ status, serviceName }) => (
  <StatusIndicator status={status} label={serviceName || "Service"} />
);

export const DatabaseStatus = ({ status }) => (
  <StatusIndicator status={status} label="Database" />
);

export const APIStatus = ({ status }) => (
  <StatusIndicator status={status} label="API" />
);

export const NetworkStatus = ({ status }) => (
  <StatusIndicator status={status} label="Network" />
);

export const AIServiceStatus = ({ status }) => (
  <StatusIndicator status={status} label="AI Service" />
);

export default StatusIndicator;