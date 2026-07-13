import { useCallback, useEffect, useRef, useState } from "react";

const SPEED_OPTIONS = [0.5, 1, 1.25, 1.5, 2] as const;

export type AudioEngineState = {
  mediaRef: React.RefObject<HTMLAudioElement | HTMLVideoElement | null>;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  isMuted: boolean;
  playbackRate: number;
  speedOptions: readonly number[];
  waveformPeaks: number[];
  isAnalyzingWaveform: boolean;
  buffered: TimeRanges | null;
  togglePlay: () => void;
  seek: (time: number) => void;
  seekRelative: (delta: number) => void;
  setVolume: (value: number) => void;
  toggleMute: () => void;
  setPlaybackRate: (rate: number) => void;
  cycleSpeed: () => void;
};

export function useAudioEngine(playbackUrl: string | null): AudioEngineState {
  const mediaRef = useRef<HTMLAudioElement | HTMLVideoElement | null>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolumeState] = useState(0.8);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackRate, setPlaybackRateState] = useState(1);
  const [waveformPeaks, setWaveformPeaks] = useState<number[]>([]);
  const [isAnalyzingWaveform, setIsAnalyzingWaveform] = useState(false);
  const [buffered, setBuffered] = useState<TimeRanges | null>(null);
  const animationRef = useRef<number>(0);

  // Sync time via requestAnimationFrame for smooth progress
  useEffect(() => {
    const media = mediaRef.current;
    if (!media) return;

    const tick = () => {
      setCurrentTime(media.currentTime);
      setBuffered(media.buffered.length > 0 ? media.buffered : null);
      animationRef.current = requestAnimationFrame(tick);
    };

    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);
    const handleLoadedMetadata = () => {
      setDuration(media.duration);
      if (pendingSeekRef.current !== null) {
        const pendingTime = pendingSeekRef.current;
        pendingSeekRef.current = null;
        media.currentTime = Math.max(0, Math.min(pendingTime, media.duration || pendingTime));
      }
      setCurrentTime(media.currentTime);
    };
    const handleEnded = () => setIsPlaying(false);
    const handleVolumeChange = () => {
      setVolumeState(media.volume);
      setIsMuted(media.muted);
    };
    const handleRateChange = () => setPlaybackRateState(media.playbackRate);

    media.addEventListener("play", handlePlay);
    media.addEventListener("pause", handlePause);
    media.addEventListener("loadedmetadata", handleLoadedMetadata);
    media.addEventListener("ended", handleEnded);
    media.addEventListener("volumechange", handleVolumeChange);
    media.addEventListener("ratechange", handleRateChange);
    if (media.readyState >= 1) {
      handleLoadedMetadata();
    }
    animationRef.current = requestAnimationFrame(tick);

    return () => {
      media.removeEventListener("play", handlePlay);
      media.removeEventListener("pause", handlePause);
      media.removeEventListener("loadedmetadata", handleLoadedMetadata);
      media.removeEventListener("ended", handleEnded);
      media.removeEventListener("volumechange", handleVolumeChange);
      media.removeEventListener("ratechange", handleRateChange);
      cancelAnimationFrame(animationRef.current);
    };
    pendingSeekRef.current = null;
  }, [playbackUrl]);

  // Analyze waveform via Web Audio API
  useEffect(() => {
    if (!playbackUrl) {
      setWaveformPeaks([]);
      return;
    }
    let cancelled = false;
    setIsAnalyzingWaveform(true);

    void (async () => {
      try {
        const response = await fetch(playbackUrl);
        const arrayBuffer = await response.arrayBuffer();
        if (cancelled) return;
        const audioContext = new AudioContext();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        if (cancelled) return;

        const channelData = audioBuffer.getChannelData(0);
        const sampleCount = 200;
        const samplesPerPeak = Math.floor(channelData.length / sampleCount);
        const peaks: number[] = [];
        for (let i = 0; i < sampleCount; i++) {
          let max = 0;
          const start = i * samplesPerPeak;
          const end = Math.min(start + samplesPerPeak, channelData.length);
          for (let j = start; j < end; j++) {
            const abs = Math.abs(channelData[j]);
            if (abs > max) max = abs;
          }
          peaks.push(max);
        }

        // Normalize peaks
        const maxPeak = Math.max(...peaks, 0.01);
        const normalized = peaks.map((p) => p / maxPeak);
        if (!cancelled) {
          setWaveformPeaks(normalized);
        }
        await audioContext.close();
      } catch {
        // Waveform analysis is optional — degrade gracefully
        if (!cancelled) setWaveformPeaks([]);
      } finally {
        if (!cancelled) setIsAnalyzingWaveform(false);
      }
    })();

    return () => { cancelled = true; };
  }, [playbackUrl]);

  const togglePlay = useCallback(() => {
    const media = mediaRef.current;
    if (!media) return;
    if (media.paused) {
      void media.play();
    } else {
      media.pause();
    }
  }, []);

  const seek = useCallback((time: number) => {
    const media = mediaRef.current;
    if (!media) return;
    const target = Math.max(0, time);
    if (!Number.isFinite(media.duration) || media.duration <= 0) {
      pendingSeekRef.current = target;
      return;
    }
    media.currentTime = Math.min(target, media.duration);
    setCurrentTime(media.currentTime);
  }, []);

  const seekRelative = useCallback((delta: number) => {
    const media = mediaRef.current;
    if (!media) return;
    const target = media.currentTime + delta;
    media.currentTime = Math.max(0, Math.min(target, media.duration || 0));
    setCurrentTime(media.currentTime);
  }, []);

  const setVolume = useCallback((value: number) => {
    const media = mediaRef.current;
    if (!media) return;
    const clamped = Math.max(0, Math.min(1, value));
    media.volume = clamped;
    setVolumeState(clamped);
    if (clamped > 0 && media.muted) {
      media.muted = false;
      setIsMuted(false);
    }
  }, []);

  const toggleMute = useCallback(() => {
    const media = mediaRef.current;
    if (!media) return;
    media.muted = !media.muted;
    setIsMuted(media.muted);
  }, []);

  const setPlaybackRate = useCallback((rate: number) => {
    const media = mediaRef.current;
    if (!media) return;
    media.playbackRate = rate;
    setPlaybackRateState(rate);
  }, []);

  const cycleSpeed = useCallback(() => {
    const media = mediaRef.current;
    if (!media) return;
    const currentIndex = SPEED_OPTIONS.indexOf(media.playbackRate as (typeof SPEED_OPTIONS)[number]);
    const nextIndex = (currentIndex + 1) % SPEED_OPTIONS.length;
    media.playbackRate = SPEED_OPTIONS[nextIndex];
    setPlaybackRateState(SPEED_OPTIONS[nextIndex]);
  }, []);

  return {
    mediaRef,
    isPlaying,
    currentTime,
    duration,
    volume,
    isMuted,
    playbackRate,
    speedOptions: SPEED_OPTIONS,
    waveformPeaks,
    isAnalyzingWaveform,
    buffered,
    togglePlay,
    seek,
    seekRelative,
    setVolume,
    toggleMute,
    setPlaybackRate,
    cycleSpeed,
  };
}
