import { Drawer } from "../../../shared/components/Drawer";
import { AssetPlaybackPanel } from "./AssetPlaybackPanel";
import type { MeetingAsset, TranscriptEntry } from "../types/meetingTypes";

type PlaybackDrawerProps = {
  isOpen: boolean;
  asset: MeetingAsset | null;
  playbackUrl: string | null;
  transcriptEntries: TranscriptEntry[];
  onDownload: () => void;
  onClose: () => void;
};

export function PlaybackDrawer({ isOpen, asset, playbackUrl, transcriptEntries, onDownload, onClose }: PlaybackDrawerProps) {
  return (
    <Drawer isOpen={isOpen} title="Playback" ariaLabel="Playback panel" onClose={onClose}>
      <AssetPlaybackPanel
        asset={asset!}
        playbackUrl={playbackUrl}
        transcriptEntries={transcriptEntries}
        onDownload={onDownload}
      />
    </Drawer>
  );
}
