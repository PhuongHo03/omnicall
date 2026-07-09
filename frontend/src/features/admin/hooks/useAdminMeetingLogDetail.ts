import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getMeeting } from "../../meetings/api/meetingApi";
import { getAdminMeetingLogs } from "../api/adminApi";

export function useAdminMeetingLogDetail(token: string, meetingId: string, isLogsLoading: boolean) {
  const navigate = useNavigate();
  const [currentMeetingName, setCurrentMeetingName] = useState<string | null>(null);
  const [meetingNames, setMeetingNames] = useState<Map<string, string>>(new Map());
  const hasCheckedRef = useRef(false);

  useEffect(() => {
    hasCheckedRef.current = false;
  }, [meetingId]);

  useEffect(() => {
    if (!meetingId) return;
    let isActive = true;
    void getMeeting(token, meetingId).then((meeting) => {
      if (!isActive) return;
      setCurrentMeetingName(meeting.title);
      const names = new Map<string, string>();
      names.set(meeting.id, meeting.title);
      setMeetingNames(names);
    }).catch(() => {});
    return () => { isActive = false; };
  }, [token, meetingId]);

  useEffect(() => {
    if (hasCheckedRef.current) return;
    if (isLogsLoading) return;
    hasCheckedRef.current = true;
    void getAdminMeetingLogs(token).then((items) => {
      if (!items.some((item) => item.meetingId === meetingId)) {
        navigate("/admin/logs", { replace: true });
      }
    });
  }, [isLogsLoading, token, meetingId, navigate]);

  const navigateToLogList = useCallback(() => {
    navigate("/admin/logs");
  }, [navigate]);

  return {
    currentMeetingName,
    displayName: currentMeetingName || meetingId.slice(0, 8),
    meetingNames,
    navigateToLogList,
  };
}
