import { useCallback, useEffect, useRef } from "react";

export function useDebounceCallback<T extends (...args: never[]) => void>(
  callback: T,
  delay = 400
) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clean up pending timer on unmount.
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  const debounced = useCallback(
    (...args: Parameters<T>) => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
      timerRef.current = setTimeout(() => {
        callback(...args);
        timerRef.current = null;
      }, delay);
    },
    [callback, delay]
  );

  const cancel = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Attach cancel method so callers can call `debounced.cancel()`.
  const result = debounced as typeof debounced & { cancel: () => void };
  result.cancel = cancel;

  return result;
}
