import React from 'react';
import { useTheme } from '../context/ThemeContext';

export default function ThemeToggle({ className = '' }) {
  const { theme, cycleTheme } = useTheme();
  const label = theme === 'light' ? 'Light' : theme === 'dark' ? 'Ops Dark' : 'High Contrast';
  return (
    <button
      onClick={cycleTheme}
      title={`Switch theme (current: ${label})`}
      className={`inline-flex items-center gap-2 px-3 py-2 rounded-md border transition-colors duration-150 ${
        theme === 'light'
          ? 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
          : theme === 'dark'
          ? 'bg-gray-800 border-gray-600 text-gray-100 hover:bg-gray-700'
          : 'bg-black text-amber-300 border-amber-400 hover:bg-gray-900'
      } ${className}`}
    >
      <span>Theme:</span>
      <span className="font-medium">{label}</span>
    </button>
  );
}
