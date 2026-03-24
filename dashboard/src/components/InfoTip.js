/**
 * InfoTip — shared (i) tooltip component used across all pages.
 * Click to toggle · Outside-click to close · Edge-aware popover placement.
 */
import React, { useState, useEffect, useRef } from 'react';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };

/* Inject keyframe once globally */
let _styled = false;
function ensureAnim() {
  if (_styled || typeof document === 'undefined') return;
  _styled = true;
  const el = document.createElement('style');
  el.id = 'infotip-kf';
  el.textContent = `@keyframes itIn{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:translateY(0)}}`;
  document.head.appendChild(el);
}

export default function InfoTip({ info, size = 15 }) {
  const [open, setOpen] = useState(false);
  const [alignRight, setAlignRight] = useState(true);
  const wrapRef = useRef(null);
  const btnRef  = useRef(null);

  ensureAnim();

  useEffect(() => {
    if (!open) return;
    /* Detect right-edge proximity → flip popover to left-aligned */
    if (btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setAlignRight(rect.right + 210 <= window.innerWidth);
    }
    function onDown(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const btnSize = `${size}px`;

  return (
    <div ref={wrapRef} style={{ position: 'relative', display: 'inline-flex', flexShrink: 0, zIndex: 20 }}>
      {/* The (i) circle */}
      <button
        ref={btnRef}
        type="button"
        aria-label="More information"
        onClick={e => { e.stopPropagation(); setOpen(v => !v); }}
        style={{
          width: btnSize, height: btnSize,
          borderRadius: '50%',
          border: `1px solid ${open ? 'rgba(245,158,11,0.6)' : 'rgba(168,159,140,0.2)'}`,
          background: open ? 'rgba(245,158,11,0.14)' : 'transparent',
          color: open ? '#F59E0B' : 'rgba(168,159,140,0.38)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', padding: 0,
          transition: 'border-color 0.15s, background 0.15s, color 0.15s',
          ...MONO, fontSize: `${Math.floor(size * 0.6)}px`, fontWeight: 700, lineHeight: 1,
        }}
        onMouseEnter={e => {
          if (!open) {
            e.currentTarget.style.borderColor = 'rgba(245,158,11,0.5)';
            e.currentTarget.style.color       = '#F59E0B';
            e.currentTarget.style.background  = 'rgba(245,158,11,0.09)';
          }
        }}
        onMouseLeave={e => {
          if (!open) {
            e.currentTarget.style.borderColor = 'rgba(168,159,140,0.2)';
            e.currentTarget.style.color       = 'rgba(168,159,140,0.38)';
            e.currentTarget.style.background  = 'transparent';
          }
        }}
      >i</button>

      {/* Popover */}
      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            ...(alignRight ? { left: 0 } : { right: 0 }),
            width: '210px',
            zIndex: 300,
            background: 'rgb(16,15,12)',
            border: '1px solid rgba(245,158,11,0.22)',
            borderRadius: '10px',
            padding: '11px 14px',
            boxShadow: '0 16px 48px rgba(0,0,0,0.7), 0 0 0 1px rgba(245,158,11,0.04)',
            animation: 'itIn 0.14s ease',
            pointerEvents: 'auto',
          }}
        >
          {/* Arrow caret */}
          <div style={{
            position: 'absolute',
            top: '-5px',
            ...(alignRight ? { left: '5px' } : { right: '5px' }),
            width: '8px', height: '8px',
            background: 'rgb(16,15,12)',
            border: '1px solid rgba(245,158,11,0.22)',
            borderBottom: 'none', borderRight: 'none',
            transform: 'rotate(45deg)',
          }} />
          <p style={{ ...UI, fontSize: '11px', lineHeight: 1.65, color: 'rgb(168,159,140)', margin: 0 }}>
            {info}
          </p>
        </div>
      )}
    </div>
  );
}
