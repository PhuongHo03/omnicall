import { useEffect, useState } from "react";

import { downloadMeetingAsset } from "../api/meetingApi";
import { isPlayableAsset } from "../states/meetingState";
import type { Meeting, MeetingAsset } from "../types/meetingTypes";

export function useMeetingAssetPlayback(
  token: string,
  selectedMeeting: Meeting | null,
  lastAsset: MeetingAsset | null,
  onError: (message: string) => void,
): string | null {
  const [assetPlaybackUrl, setAssetPlaybackUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedMeeting || !lastAsset || !isPlayableAsset(lastAsset) || lastAsset.meetingId !== selectedMeeting.id) {
      setAssetPlaybackUrl(null);
      return;
    }

    let isActive = true;
    let objectUrl: string | null = null;
    void downloadMeetingAsset(token, selectedMeeting.id, lastAsset.id)
      .then((blob) => {
        if (!isActive) {
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setAssetPlaybackUrl(objectUrl);
      })
      .catch((caught) => {
        if (isActive) {
          setAssetPlaybackUrl(null);
          onError(caught instanceof Error ? caught.message : "Asset playback failed.");
        }
      });

    return () => {
      isActive = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [lastAsset?.id, onError, selectedMeeting?.id, token]);

  return assetPlaybackUrl;
}
