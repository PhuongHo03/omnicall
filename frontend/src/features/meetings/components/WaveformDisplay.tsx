import { useCallback, useEffect, useRef, useState } from "react";

type WaveformDisplayProps = {
  peaks: number[];
  progress: number;
  isAnalyzing: boolean;
  onSeek: (progress: number) => void;
};

const BAR_WIDTH = 3;
const BAR_GAP = 1;
const BAR_MIN_HEIGHT = 2;

function readCssVar(el: HTMLElement, name: string, fallback: string): string {
  return getComputedStyle(el).getPropertyValue(name).trim() || fallback;
}

export function WaveformDisplay({ peaks, progress, isAnalyzing, onSeek }: WaveformDisplayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  // Track container size changes (sidebar toggle, window resize)
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height } = entry.contentRect;
        setContainerSize({ width: Math.floor(width), height: Math.floor(height) });
      }
    });

    observer.observe(container);

    // Initial size
    const rect = container.getBoundingClientRect();
    setContainerSize({ width: Math.floor(rect.width), height: Math.floor(rect.height) });

    return () => observer.disconnect();
  }, []);

  // Redraw canvas whenever size, peaks, or progress change
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    if (containerSize.width === 0 || containerSize.height === 0) return;

    const dpr = window.devicePixelRatio || 1;
    const width = containerSize.width;
    const height = containerSize.height;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const activeColor = readCssVar(container, "--apb-waveform-active", "#0d9488");
    const bgColor = readCssVar(container, "--apb-waveform-bg", "#d1d5db");

    const totalBarWidth = BAR_WIDTH + BAR_GAP;
    const barCount = Math.floor(width / totalBarWidth);

    if (peaks.length === 0) {
      for (let i = 0; i < barCount; i++) {
        const x = i * totalBarWidth;
        const barHeight = Math.max(BAR_MIN_HEIGHT, height * 0.15);
        const y = (height - barHeight) / 2;
        ctx.fillStyle = bgColor;
        ctx.fillRect(x, y, BAR_WIDTH, barHeight);
      }
      return;
    }

    const progressIndex = Math.floor(progress * barCount);

    for (let i = 0; i < barCount; i++) {
      const x = i * totalBarWidth;
      const peakValue = peaks[Math.floor((i / barCount) * peaks.length)] ?? 0;
      const barHeight = Math.max(BAR_MIN_HEIGHT, peakValue * (height - 4));
      const y = (height - barHeight) / 2;

      ctx.fillStyle = i < progressIndex ? activeColor : bgColor;
      ctx.fillRect(x, y, BAR_WIDTH, barHeight);
    }
  }, [peaks, progress, containerSize]);

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      if (peaks.length === 0) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const clickX = event.clientX - rect.left;
      const clickProgress = Math.max(0, Math.min(1, clickX / rect.width));
      onSeek(clickProgress);
    },
    [peaks, onSeek]
  );

  return (
    <div
      ref={containerRef}
      className={`apb-waveform${isAnalyzing ? " apb-waveform--analyzing" : ""}${peaks.length === 0 ? " apb-waveform--empty" : ""}`}
    >
      <canvas
        ref={canvasRef}
        className="apb-waveform__canvas"
        role="slider"
        aria-label="Audio waveform seek"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        tabIndex={0}
        onClick={handleClick}
      />
      {isAnalyzing && (
        <div className="apb-waveform__loading">Analyzing waveform…</div>
      )}
    </div>
  );
}
