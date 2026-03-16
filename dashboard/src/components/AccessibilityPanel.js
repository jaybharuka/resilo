import React, { useState, useEffect } from 'react';
import {
  Fab,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
  Typography,
  Box,
  Divider,
  useTheme,
  Tooltip,
  Switch,
  FormControlLabel
} from '@mui/material';
import {
  Accessibility as AccessibilityIcon,
  TextFields as FontSizeIcon,
  Contrast as ContrastIcon,
  ZoomIn as ZoomInIcon,
  ZoomOut as ZoomOutIcon,
  VolumeUp as VolumeIcon,
  Keyboard as KeyboardIcon,
  Visibility as VisibilityIcon
} from '@mui/icons-material';

const AccessibilityPanel = ({ onThemeToggle, darkMode }) => {
  const theme = useTheme();
  const [anchorEl, setAnchorEl] = useState(null);
  const [settings, setSettings] = useState({
    fontSize: 'normal',
    highContrast: false,
    soundEnabled: true,
    keyboardNavigation: true,
    reducedMotion: false
  });

  const open = Boolean(anchorEl);

  const handleClick = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleFontSizeChange = (size) => {
    setSettings(prev => ({ ...prev, fontSize: size }));
    
    // Apply font size changes to root element
    const root = document.documentElement;
    switch (size) {
      case 'small':
        root.style.fontSize = '14px';
        break;
      case 'large':
        root.style.fontSize = '18px';
        break;
      case 'extra-large':
        root.style.fontSize = '22px';
        break;
      default:
        root.style.fontSize = '16px';
    }
  };

  const handleHighContrastToggle = () => {
    const newValue = !settings.highContrast;
    setSettings(prev => ({ ...prev, highContrast: newValue }));
    
    // Apply high contrast mode
    document.body.classList.toggle('high-contrast', newValue);
  };

  const handleReducedMotionToggle = () => {
    const newValue = !settings.reducedMotion;
    setSettings(prev => ({ ...prev, reducedMotion: newValue }));
    
    // Apply reduced motion preference
    document.body.classList.toggle('reduced-motion', newValue);
  };

  // Add keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (event) => {
      if (event.altKey) {
        switch (event.key) {
          case 'a':
            event.preventDefault();
            handleClick(event);
            break;
          case 't':
            event.preventDefault();
            onThemeToggle();
            break;
          case '+':
            event.preventDefault();
            handleFontSizeChange('large');
            break;
          case '-':
            event.preventDefault();
            handleFontSizeChange('small');
            break;
          default:
            break;
        }
      }
    };

    if (settings.keyboardNavigation) {
      document.addEventListener('keydown', handleKeyPress);
      return () => document.removeEventListener('keydown', handleKeyPress);
    }
  }, [settings.keyboardNavigation, onThemeToggle]);

  return (
    <>
      <Tooltip title="Accessibility Options (Alt+A)">
        <Fab
          size="small"
          color="secondary"
          onClick={handleClick}
          sx={{
            position: 'fixed',
            bottom: 24,
            left: 24,
            background: 'linear-gradient(45deg, #2196F3, #21CBF3)',
            '&:hover': {
              transform: 'scale(1.1)',
              transition: 'transform 0.2s ease-in-out'
            }
          }}
        >
          <AccessibilityIcon />
        </Fab>
      </Tooltip>

      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        transformOrigin={{ horizontal: 'left', vertical: 'bottom' }}
        anchorOrigin={{ horizontal: 'left', vertical: 'top' }}
        PaperProps={{
          sx: {
            minWidth: 280,
            maxWidth: 400,
            background: theme.palette.mode === 'dark' 
              ? 'rgba(30, 30, 30, 0.95)'
              : 'rgba(255, 255, 255, 0.95)',
            backdropFilter: 'blur(20px)',
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 2
          }
        }}
      >
        <Box sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
            Accessibility Options
          </Typography>
          <Typography variant="caption" color="textSecondary">
            Customize your experience for better accessibility
          </Typography>
        </Box>
        
        <Divider />
        
        {/* Font Size */}
        <MenuItem>
          <ListItemIcon>
            <FontSizeIcon />
          </ListItemIcon>
          <ListItemText>
            <Typography variant="subtitle2">Font Size</Typography>
            <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
              {['small', 'normal', 'large', 'extra-large'].map((size) => (
                <Tooltip key={size} title={`${size.charAt(0).toUpperCase()}${size.slice(1)} font`}>
                  <Box
                    component="button"
                    onClick={() => handleFontSizeChange(size)}
                    sx={{
                      border: 'none',
                      background: settings.fontSize === size ? theme.palette.primary.main : 'transparent',
                      color: settings.fontSize === size ? 'white' : 'inherit',
                      borderRadius: 1,
                      p: 0.5,
                      minWidth: 24,
                      cursor: 'pointer',
                      fontSize: size === 'small' ? '12px' : size === 'large' ? '18px' : size === 'extra-large' ? '20px' : '14px'
                    }}
                  >
                    Aa
                  </Box>
                </Tooltip>
              ))}
            </Box>
          </ListItemText>
        </MenuItem>

        {/* High Contrast */}
        <MenuItem onClick={handleHighContrastToggle}>
          <ListItemIcon>
            <ContrastIcon />
          </ListItemIcon>
          <ListItemText>
            <FormControlLabel
              control={
                <Switch 
                  checked={settings.highContrast}
                  size="small"
                />
              }
              label="High Contrast Mode"
              sx={{ m: 0 }}
            />
          </ListItemText>
        </MenuItem>

        {/* Dark Mode Toggle */}
        <MenuItem onClick={onThemeToggle}>
          <ListItemIcon>
            <VisibilityIcon />
          </ListItemIcon>
          <ListItemText>
            <FormControlLabel
              control={
                <Switch 
                  checked={darkMode}
                  size="small"
                />
              }
              label="Dark Mode (Alt+T)"
              sx={{ m: 0 }}
            />
          </ListItemText>
        </MenuItem>

        {/* Reduced Motion */}
        <MenuItem onClick={handleReducedMotionToggle}>
          <ListItemIcon>
            <ZoomInIcon />
          </ListItemIcon>
          <ListItemText>
            <FormControlLabel
              control={
                <Switch 
                  checked={settings.reducedMotion}
                  size="small"
                />
              }
              label="Reduce Motion"
              sx={{ m: 0 }}
            />
          </ListItemText>
        </MenuItem>

        {/* Sound */}
        <MenuItem onClick={() => setSettings(prev => ({ ...prev, soundEnabled: !prev.soundEnabled }))}>
          <ListItemIcon>
            <VolumeIcon />
          </ListItemIcon>
          <ListItemText>
            <FormControlLabel
              control={
                <Switch 
                  checked={settings.soundEnabled}
                  size="small"
                />
              }
              label="Sound Feedback"
              sx={{ m: 0 }}
            />
          </ListItemText>
        </MenuItem>

        {/* Keyboard Navigation */}
        <MenuItem onClick={() => setSettings(prev => ({ ...prev, keyboardNavigation: !prev.keyboardNavigation }))}>
          <ListItemIcon>
            <KeyboardIcon />
          </ListItemIcon>
          <ListItemText>
            <FormControlLabel
              control={
                <Switch 
                  checked={settings.keyboardNavigation}
                  size="small"
                />
              }
              label="Keyboard Shortcuts"
              sx={{ m: 0 }}
            />
          </ListItemText>
        </MenuItem>

        <Divider />
        
        <Box sx={{ p: 2 }}>
          <Typography variant="caption" color="textSecondary">
            <strong>Keyboard Shortcuts:</strong><br/>
            Alt+A: Accessibility panel<br/>
            Alt+T: Toggle theme<br/>
            Alt++: Increase font size<br/>
            Alt+-: Decrease font size
          </Typography>
        </Box>
      </Menu>
    </>
  );
};

export default AccessibilityPanel;