import React from 'react';
import InfoTip from '../InfoTip';

const MONO    = { fontFamily: "'IBM Plex Mono', monospace" };
const DISPLAY = { fontFamily: "'Bebas Neue', sans-serif" };
const UI      = { fontFamily: "'Outfit', sans-serif" };

const STATUS = {
  healthy:  { dot: '#2DD4BF', dotGlow: 'rgba(45,212,191,0.5)',  label: 'NOMINAL',   labelColor: '#2DD4BF' },
  warning:  { dot: '#F59E0B', dotGlow: 'rgba(245,158,11,0.5)',  label: 'WARNING',   labelColor: '#F59E0B' },
  critical: { dot: '#F87171', dotGlow: 'rgba(248,113,113,0.5)', label: 'CRITICAL',  labelColor: '#F87171' },
};

export default function MetricCard({ title, value, unit, status, trend, info }) {
  const s = STATUS[status] || STATUS.healthy;
  const trendUp = trend > 0;

  return (
    <div
      style={{
        background: 'rgb(22, 20, 16)',
        border: '1px solid rgba(42,40,32,0.9)',
        borderTop: `2px solid ${s.dot}`,
        borderRadius: '12px',
        padding: '20px 22px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        position: 'relative',
        boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
      }}
    >
      {/* InfoTip */}
      {info && (
        <div style={{ position: 'absolute', top: '10px', right: '10px', zIndex: 10 }}>
          <InfoTip info={info} />
        </div>
      )}

      {/* Subtle corner glow */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          width: '80px',
          height: '80px',
          borderRadius: '50%',
          background: `radial-gradient(circle, ${s.dot}12 0%, transparent 70%)`,
          pointerEvents: 'none',
        }}
      />

      {/* Title */}
      <p
        style={{
          ...MONO,
          fontSize: '10px',
          letterSpacing: '0.14em',
          color: '#6B6357',
          margin: 0,
          textTransform: 'uppercase',
        }}
      >
        {title}
      </p>

      {/* Value */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
        <span
          style={{
            ...DISPLAY,
            fontSize: '3.25rem',
            letterSpacing: '0.02em',
            lineHeight: 1,
            color: '#F5F0E8',
          }}
        >
          {value}
        </span>
        <span
          style={{
            ...MONO,
            fontSize: '13px',
            color: '#6B6357',
            letterSpacing: '0.06em',
          }}
        >
          {unit}
        </span>
      </div>

      {/* Status row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: s.dot,
            boxShadow: `0 0 8px ${s.dotGlow}`,
            flexShrink: 0,
            display: 'inline-block',
          }}
        />
        <span
          style={{
            ...MONO,
            fontSize: '10px',
            letterSpacing: '0.1em',
            color: s.labelColor,
          }}
        >
          {s.label}
        </span>
        {trend !== 0 && (
          <>
            <span style={{ color: '#3A342D', fontSize: '10px' }}>·</span>
            <span
              style={{
                ...UI,
                fontSize: '11px',
                color: trendUp ? '#F87171' : '#2DD4BF',
              }}
            >
              {trendUp ? '↑' : '↓'} {Math.abs(trend)}%
            </span>
          </>
        )}
      </div>
    </div>
  );
}
