import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

const ThemeContext = createContext({
  theme: 'light',
  setTheme: () => {},
  cycleTheme: () => {},
});

const THEMES = ['light', 'dark', 'high-contrast'];

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState('light');

  useEffect(() => {
    try {
      const saved = localStorage.getItem('aiops.theme');
      if (saved && THEMES.includes(saved)) {
        setThemeState(saved);
      }
    } catch {}
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('theme-light', 'theme-dark', 'theme-hc');
    const cls = theme === 'dark' ? 'theme-dark' : theme === 'high-contrast' ? 'theme-hc' : 'theme-light';
    root.classList.add(cls);
    try { localStorage.setItem('aiops.theme', theme); } catch {}
  }, [theme]);

  const setTheme = (t) => {
    if (THEMES.includes(t)) setThemeState(t);
  };

  const cycleTheme = () => {
    setThemeState((prev) => {
      const idx = THEMES.indexOf(prev);
      return THEMES[(idx + 1) % THEMES.length];
    });
  };

  const value = useMemo(() => ({ theme, setTheme, cycleTheme }), [theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

export default ThemeContext;
