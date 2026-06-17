import { Volume2 } from "lucide-react";

import type { MeetingAsset } from "../types/meetingTypes";

type MeetingAssetPlaybackPanelProps = {
  asset: MeetingAsset | null;
  playbackUrl: string | null;
};

export function MeetingAssetPlaybackPanel({ asset, playbackUrl }: MeetingAssetPlaybackPanelProps) {
  if (!asset || !asset.contentType.startsWith("audio/")) {
    return null;
  }

  return (
    <section className="asset-playback-panel">
      <div className="section-heading">
        <h2>
          <Volume2 size={16} />
          Audio Playback
        </h2>
        <span>{asset.fileName}</span>
      </div>
      {playbackUrl ? (
        <audio className="asset-playback-panel__audio" src={playbackUrl} controls preload="metadata" />
      ) : (
        <div className="asset-playback-panel__loading">Loading audio...</div>
      )}
    </section>
  );
}
