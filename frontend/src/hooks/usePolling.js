import { useEffect, useRef, useState, useCallback } from 'react';

export function usePolling(fetchFn, interval = 4000, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const abortControllerRef = useRef(null);
  const intervalRef = useRef(null);
  const isMountedRef = useRef(true);
  const hiddenRef = useRef(false);

  const fetchData = useCallback(async () => {
    if (hiddenRef.current || !isMountedRef.current) return;
    
    abortControllerRef.current = new AbortController();
    
    try {
      const result = await fetchFn({ signal: abortControllerRef.current.signal });
      if (isMountedRef.current) {
        setData(result);
        setLastUpdated(new Date());
        setError(null);
        setLoading(false);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (isMountedRef.current) {
        setError(err.message);
        setLoading(false);
      }
    }
  }, [fetchFn]);

  useEffect(() => {
    isMountedRef.current = true;
    fetchData();
    
    intervalRef.current = setInterval(fetchData, interval);
    
    const handleVisibilityChange = () => {
      hiddenRef.current = document.hidden;
      if (!document.hidden) fetchData();
    };
    
    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      isMountedRef.current = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [fetchData, interval, ...deps]);

  const refetch = useCallback(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, lastUpdated, refetch };
}