import { Drawer } from "../../../shared/components/Drawer";
import { AssetPlaybackPanel } from "./AssetPlaybackPanel";
import type { MeetingAsset, PlaybackSeekRequest, TranscriptEntry } from "../types/meetingTypes";

type PlaybackDrawerProps = {
  isOpen: boolean;
  asset: MeetingAsset | null;
  playbackUrl: string | null;
  playbackStatus: "idle" | "loading" | "ready" | "error";
  playbackError: string | null;
  transcriptEntries: TranscriptEntry[];
  onDownload: () => void;
  onClose: () => void;
  seekRequest: PlaybackSeekRequest | null;
};

export function PlaybackDrawer({ isOpen, asset, playbackUrl, playbackStatus, playbackError, transcriptEntries, onDownload, onClose, seekRequest }: PlaybackDrawerProps) {
  return (
    <Drawer isOpen={isOpen} title="Playback" ariaLabel="Playback panel" onClose={onClose}>
      {!asset ? (
        <div className="apb__loading">No playable asset is available.</div>
      ) : playbackStatus === "error" ? (
        <div className="apb__loading" role="alert">{playbackError ?? "Asset playback failed."}</div>
      ) : (
        <AssetPlaybackPanel
          asset={asset}
          playbackUrl={playbackUrl}
          transcriptEntries={transcriptEntries}
          onDownload={onDownload}
          seekRequest={seekRequest}
        />
      )}
    </Drawer>
  );
}
