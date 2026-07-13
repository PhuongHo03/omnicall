import { useCallback, useEffect, useState } from "react";

import type { MeetingAsset, PlaybackSeekRequest } from "../types/meetingTypes";
import { AssetMetadataBar } from "./AssetMetadataBar";
import { PlayerControls } from "./PlayerControls";
import { TranscriptTrack } from "./TranscriptTrack";
import type { TranscriptEntry } from "../types/meetingTypes";
import { resolveMediaKind } from "../utils/meetingFormatters";
import { useAudioEngine } from "../hooks/useAudioEngine";
import { useTranscriptSync } from "../hooks/useTranscriptSync";
import { WaveformDisplay } from "./WaveformDisplay";

type AssetPlaybackPanelProps = {
  asset: MeetingAsset;
  playbackUrl: string | null;
  transcriptEntries: TranscriptEntry[];
  onDownload: () => void;
  seekRequest: PlaybackSeekRequest | null;
};

export function AssetPlaybackPanel({
  asset,
  playbackUrl,
  transcriptEntries,
  onDownload,
  seekRequest,
}: AssetPlaybackPanelProps) {
  const engine = useAudioEngine(playbackUrl);
  const transcript = useTranscriptSync(transcriptEntries, engine.currentTime);
  const [focusedSegmentId, setFocusedSegmentId] = useState<string | null>(null);
  const mediaKind = resolveMediaKind(asset);
  const isVideo = mediaKind === "video";
  const progress = engine.duration > 0 ? engine.currentTime / engine.duration : 0;

  const handleWaveformSeek = useCallback(
    (seekProgress: number) => {
      engine.seek(seekProgress * engine.duration);
    },
    [engine]
  );

  const handleTranscriptSeek = useCallback(
    (entry: TranscriptEntry) => {
      engine.seek(entry.startMs / 1000);
    },
    [engine]
  );

  useEffect(() => {
    if (!seekRequest) {
      return;
    }
    if (seekRequest.startMs !== null) {
      engine.seek(seekRequest.startMs / 1000);
    }
    setFocusedSegmentId(seekRequest.segmentIds[0] ?? null);
  }, [engine.seek, playbackUrl, seekRequest]);

  const isEmpty = transcriptEntries.length === 0 && !playbackUrl;

  if (isEmpty) {
    return (
      <section className="apb">
        <TranscriptTrack
          entries={transcriptEntries}
          activeIndex={transcript.activeIndex}
          progressWithinEntry={transcript.progressWithinEntry}
          onSeekToEntry={handleTranscriptSeek}
          focusedSegmentId={focusedSegmentId}
        />
      </section>
    );
  }

  return (
    <section className="apb">
      <AssetMetadataBar
        asset={asset}
        mediaKind={mediaKind}
        duration={engine.duration}
        onDownload={onDownload}
      />

      {/* Media element — hidden for audio, visible for video */}
      {playbackUrl ? (
        isVideo ? (
          <video
            ref={engine.mediaRef as React.RefObject<HTMLVideoElement>}
            className="apb__video"
            src={playbackUrl}
            preload="metadata"
            playsInline
          />
        ) : (
          <audio
            ref={engine.mediaRef as React.RefObject<HTMLAudioElement>}
            className="apb__audio-hidden"
            src={playbackUrl}
            preload="metadata"
          />
        )
      ) : null}

      {!playbackUrl ? (
        <div className="apb__loading">Loading media…</div>
      ) : (
        <>
          {/* Waveform — audio only */}
          {!isVideo && (
            <WaveformDisplay
              peaks={engine.waveformPeaks}
              progress={progress}
              isAnalyzing={engine.isAnalyzingWaveform}
              onSeek={handleWaveformSeek}
            />
          )}

          <PlayerControls
            isPlaying={engine.isPlaying}
            currentTime={engine.currentTime}
            duration={engine.duration}
            volume={engine.volume}
            isMuted={engine.isMuted}
            playbackRate={engine.playbackRate}
            onTogglePlay={engine.togglePlay}
            onSeekRelative={engine.seekRelative}
            onSeek={engine.seek}
            onVolumeChange={engine.setVolume}
            onToggleMute={engine.toggleMute}
            onCycleSpeed={engine.cycleSpeed}
          />
        </>
      )}

      <TranscriptTrack
        entries={transcriptEntries}
        activeIndex={transcript.activeIndex}
        progressWithinEntry={transcript.progressWithinEntry}
        onSeekToEntry={handleTranscriptSeek}
        focusedSegmentId={focusedSegmentId}
      />
    </section>
  );
}
