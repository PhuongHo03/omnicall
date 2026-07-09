import {
  Gauge,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
} from "lucide-react";

import { IconOnlyButton } from "../../../shared/components/IconOnlyButton";
import { formatTime } from "../utils/meetingFormatters";

type PlayerControlsProps = {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  isMuted: boolean;
  playbackRate: number;
  onTogglePlay: () => void;
  onSeekRelative: (delta: number) => void;
  onSeek: (time: number) => void;
  onVolumeChange: (value: number) => void;
  onToggleMute: () => void;
  onCycleSpeed: () => void;
};

export function PlayerControls({
  isPlaying,
  currentTime,
  duration,
  volume,
  isMuted,
  playbackRate,
  onTogglePlay,
  onSeekRelative,
  onSeek,
  onVolumeChange,
  onToggleMute,
  onCycleSpeed,
}: PlayerControlsProps) {
  const progress = duration > 0 ? currentTime / duration : 0;

  return (
    <div className="apb-controls">
      <div className="apb-controls__transport">
        <IconOnlyButton className="apb-controls__btn--skip" icon={<SkipBack size={16} />} label="Back 10 seconds" onClick={() => onSeekRelative(-10)} />
        <IconOnlyButton className="apb-controls__btn--play" icon={isPlaying ? <Pause size={18} /> : <Play size={18} />} label={isPlaying ? "Pause" : "Play"} onClick={onTogglePlay} />
        <IconOnlyButton className="apb-controls__btn--skip" icon={<SkipForward size={16} />} label="Forward 10 seconds" onClick={() => onSeekRelative(10)} />
      </div>

      <div className="apb-controls__seek">
        <span className="apb-controls__time">{formatTime(currentTime)}</span>
        <div className="apb-controls__progress-track">
          <input
            className="apb-controls__progress-input"
            type="range"
            min={0}
            max={Math.floor(duration * 100)}
            value={Math.floor(currentTime * 100)}
            aria-label="Seek"
            onChange={(e) => onSeek(Number(e.target.value) / 100)}
          />
          <div
            className="apb-controls__progress-fill"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
        <span className="apb-controls__time">{formatTime(duration)}</span>
      </div>

      <div className="apb-controls__right">
        <button
          className="apb-controls__btn--speed"
          type="button"
          title={`Speed: ${playbackRate}x`}
          aria-label={`Playback speed: ${playbackRate}x`}
          onClick={onCycleSpeed}
        >
          <Gauge size={14} />
          <span>{playbackRate}x</span>
        </button>

        <div className="apb-controls__volume">
          <IconOnlyButton className="apb-controls__btn--volume" icon={isMuted || volume === 0 ? <VolumeX size={16} /> : <Volume2 size={16} />} label={isMuted ? "Unmute" : "Mute"} onClick={onToggleMute} />
          <input
            className="apb-controls__volume-input"
            type="range"
            min={0}
            max={100}
            value={isMuted ? 0 : Math.round(volume * 100)}
            aria-label="Volume"
            onChange={(e) => onVolumeChange(Number(e.target.value) / 100)}
          />
        </div>
      </div>
    </div>
  );
}
