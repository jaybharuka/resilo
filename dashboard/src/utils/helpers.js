import React from 'react';
import { useTheme, useMediaQuery } from '@mui/material';

// Responsive breakpoint hook
export const useResponsive = () => {
  const theme = useTheme();
  
  return {
    isMobile: useMediaQuery(theme.breakpoints.down('sm')),
    isTablet: useMediaQuery(theme.breakpoints.between('sm', 'md')),
    isDesktop: useMediaQuery(theme.breakpoints.up('md')),
    isLargeScreen: useMediaQuery(theme.breakpoints.up('lg')),
    isExtraLarge: useMediaQuery(theme.breakpoints.up('xl'))
  };
};

// Touch device detection
export const isTouchDevice = () => {
  return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
};

// Performance monitoring hook
export const usePerformanceMonitor = () => {
  const monitor = {
    measureRender: (componentName) => {
      const start = performance.now();
      return () => {
        const end = performance.now();
        console.log(`${componentName} render time: ${end - start}ms`);
      };
    },
    
    measureAsync: async (operationName, asyncOperation) => {
      const start = performance.now();
      try {
        const result = await asyncOperation();
        const end = performance.now();
        console.log(`${operationName} completed in: ${end - start}ms`);
        return result;
      } catch (error) {
        const end = performance.now();
        console.error(`${operationName} failed after: ${end - start}ms`, error);
        throw error;
      }
    }
  };

  return monitor;
};

// Local storage helpers with error handling
export const storage = {
  get: (key, defaultValue = null) => {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : defaultValue;
    } catch (error) {
      console.warn(`Error reading from localStorage for key "${key}":`, error);
      return defaultValue;
    }
  },
  
  set: (key, value) => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (error) {
      console.warn(`Error writing to localStorage for key "${key}":`, error);
      return false;
    }
  },
  
  remove: (key) => {
    try {
      localStorage.removeItem(key);
      return true;
    } catch (error) {
      console.warn(`Error removing from localStorage for key "${key}":`, error);
      return false;
    }
  }
};

// Debounce utility for performance optimization
export const useDebounce = (value, delay) => {
  const [debouncedValue, setDebouncedValue] = React.useState(value);

  React.useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
};

// Keyboard navigation helpers
export const keyboardNavigation = {
  handleArrowKeys: (event, items, currentIndex, onSelect) => {
    switch (event.key) {
      case 'ArrowUp':
        event.preventDefault();
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
        onSelect(prevIndex);
        break;
      case 'ArrowDown':
        event.preventDefault();
        const nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
        onSelect(nextIndex);
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        if (items[currentIndex] && items[currentIndex].onClick) {
          items[currentIndex].onClick();
        }
        break;
      case 'Escape':
        event.preventDefault();
        // Handle escape key
        break;
      default:
        break;
    }
  },
  
  trapFocus: (containerRef) => {
    const focusableElements = containerRef.current?.querySelectorAll(
      'a[href], button, textarea, input[type="text"], input[type="radio"], input[type="checkbox"], select'
    );
    
    if (!focusableElements || focusableElements.length === 0) return;
    
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    
    const handleTabKey = (event) => {
      if (event.key !== 'Tab') return;
      
      if (event.shiftKey) {
        if (document.activeElement === firstElement) {
          lastElement.focus();
          event.preventDefault();
        }
      } else {
        if (document.activeElement === lastElement) {
          firstElement.focus();
          event.preventDefault();
        }
      }
    };
    
    containerRef.current?.addEventListener('keydown', handleTabKey);
    
    return () => {
      containerRef.current?.removeEventListener('keydown', handleTabKey);
    };
  }
};

// Error boundary helper
export const withErrorBoundary = (Component, fallback) => {
  return class extends React.Component {
    constructor(props) {
      super(props);
      this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
      return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
      console.error('Error caught by boundary:', error, errorInfo);
    }

    render() {
      if (this.state.hasError) {
        return fallback || <div>Something went wrong.</div>;
      }

      return <Component {...this.props} />;
    }
  };
};

export default {
  useResponsive,
  isTouchDevice,
  usePerformanceMonitor,
  storage,
  useDebounce,
  keyboardNavigation,
  withErrorBoundary
};