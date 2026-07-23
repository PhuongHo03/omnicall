import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Meeting } from "../types/meetingTypes";

type UseMeetingSelectionArgs = {
  hasLoadedMeetings: boolean;
  lockedMeetingIdRef?: React.RefObject<string | null>;
  meetings: Meeting[];
  onSelectedMeetingChange: (meetingId: string | null) => void;
  requestedMeetingId: string | null;
};

export function useMeetingSelection({
  hasLoadedMeetings,
  lockedMeetingIdRef,
  meetings,
  onSelectedMeetingChange,
  requestedMeetingId,
}: UseMeetingSelectionArgs) {
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(requestedMeetingId);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentMeetingIdRef = useRef<string | null>(selectedMeetingId);

  const selectedMeeting = useMemo(
    () => meetings.find((meeting) => meeting.id === selectedMeetingId) ?? null,
    [meetings, selectedMeetingId]
  );

  const selectMeeting = useCallback(
    (meetingId: string | null) => {
      const lockedMeetingId = lockedMeetingIdRef?.current;
      if (lockedMeetingId && meetingId !== lockedMeetingId) {
        onSelectedMeetingChange(lockedMeetingId);
        return;
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();
      setSelectedMeetingId(meetingId);
      currentMeetingIdRef.current = meetingId;
      onSelectedMeetingChange(meetingId);
    },
    [lockedMeetingIdRef, onSelectedMeetingChange]
  );

  useEffect(() => {
    if (!hasLoadedMeetings) {
      return;
    }
    const lockedMeetingId = lockedMeetingIdRef?.current;
    if (lockedMeetingId && requestedMeetingId !== lockedMeetingId) {
      setSelectedMeetingId(lockedMeetingId);
      currentMeetingIdRef.current = lockedMeetingId;
      onSelectedMeetingChange(lockedMeetingId);
      return;
    }
    if (!requestedMeetingId) {
      setSelectedMeetingId(null);
      currentMeetingIdRef.current = null;
      return;
    }
    if (meetings.some((meeting) => meeting.id === requestedMeetingId)) {
      setSelectedMeetingId(requestedMeetingId);
      currentMeetingIdRef.current = requestedMeetingId;
      return;
    }
    setSelectedMeetingId(null);
    currentMeetingIdRef.current = null;
    onSelectedMeetingChange(null);
  }, [hasLoadedMeetings, lockedMeetingIdRef, meetings, onSelectedMeetingChange, requestedMeetingId]);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return {
    abortControllerRef,
    currentMeetingIdRef,
    selectedMeeting,
    selectedMeetingId,
    selectMeeting,
  };
}
