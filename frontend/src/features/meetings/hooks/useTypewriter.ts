import { useEffect, useRef, useState } from "react";

const DEFAULT_SPEED_MS = 20;

export function useTypewriter(text: string, enabled: boolean, speedMs: number = DEFAULT_SPEED_MS) {
  const [displayed, setDisplayed] = useState(enabled ? "" : text);
  const [isAnimating, setIsAnimating] = useState(enabled);
  const indexRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!enabled) {
      setDisplayed(text);
      setIsAnimating(false);
      return;
    }

    setDisplayed("");
    setIsAnimating(true);
    indexRef.current = 0;

    timerRef.current = setInterval(() => {
      indexRef.current += 1;
      if (indexRef.current >= text.length) {
        setDisplayed(text);
        setIsAnimating(false);
        if (timerRef.current) clearInterval(timerRef.current);
        return;
      }
      setDisplayed(text.slice(0, indexRef.current));
    }, speedMs);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [text, enabled, speedMs]);

  return { displayed, isAnimating };
}
