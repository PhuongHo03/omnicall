import { useEffect, useState } from "react";

import { downloadMeetingAsset } from "../api/meetingApi";
import { isPlayableAsset } from "../states/meetingState";
import type { Meeting, MeetingAsset } from "../types/meetingTypes";

export type AssetPlaybackState = {
  status: "idle" | "loading" | "ready" | "error";
  url: string | null;
  error: string | null;
};

const IDLE_PLAYBACK: AssetPlaybackState = { status: "idle", url: null, error: null };

export function useMeetingAssetPlayback(
  token: string,
  selectedMeeting: Meeting | null,
  lastAsset: MeetingAsset | null,
  onError: (message: string) => void,
): AssetPlaybackState {
  const [playback, setPlayback] = useState<AssetPlaybackState>(IDLE_PLAYBACK);

  useEffect(() => {
    if (!selectedMeeting || !lastAsset || !isPlayableAsset(lastAsset) || lastAsset.meetingId !== selectedMeeting.id) {
      setPlayback(IDLE_PLAYBACK);
      return;
    }

    const controller = new AbortController();
    let objectUrl: string | null = null;
    setPlayback({ status: "loading", url: null, error: null });
    void downloadMeetingAsset(token, selectedMeeting.id, lastAsset.id, { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setPlayback({ status: "ready", url: objectUrl, error: null });
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        const message = caught instanceof Error ? caught.message : "Asset playback failed.";
        setPlayback({ status: "error", url: null, error: message });
        onError(message);
      });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [lastAsset?.id, onError, selectedMeeting?.id, token]);

  return playback;
}
