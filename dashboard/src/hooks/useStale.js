import { useState, useEffect, useRef } from 'react';

/**
 * useStale — tracks how long since the last successful data fetch.
 * Returns { lastAt, secAgo, isStale, markFresh }
 * @param {number} staleAfterMs - ms of silence before isStale becomes true (default 30s)
 */
export function useStale(staleAfterMs = 30000) {
  const [lastAt, setLastAt] = useState(null);
  const [secAgo, setSecAgo] = useState(null);
  const [isStale, setIsStale] = useState(false);
  const timerRef = useRef(null);

  const markFresh = () => setLastAt(Date.now());

  useEffect(() => {
    timerRef.current = setInterval(() => {
      if (lastAt == null) return;
      const diff = Date.now() - lastAt;
      setSecAgo(Math.round(diff / 1000));
      setIsStale(diff > staleAfterMs);
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [lastAt, staleAfterMs]);

  return { lastAt, secAgo, isStale, markFresh };
}
