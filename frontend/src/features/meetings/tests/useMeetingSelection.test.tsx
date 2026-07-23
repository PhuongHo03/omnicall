import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useMeetingSelection } from "../hooks/useMeetingSelection";
import type { Meeting } from "../types/meetingTypes";

function meeting(id: string): Meeting {
  return {
    id,
    title: id,
    status: "DRAFT",
    failureCode: null,
    failureReason: null,
    pendingChatStatus: null,
    createdAt: "2026-07-16T00:00:00Z",
    updatedAt: "2026-07-16T00:00:00Z",
    latestAsset: null,
    retryAllowed: false,
  };
}

describe("useMeetingSelection recording lock", () => {
  it("restores the owner meeting when URL or UI tries to select another meeting", async () => {
    const onSelectedMeetingChange = vi.fn();
    const lockedMeetingIdRef = { current: "meeting-1" };
    const { result } = renderHook(() => useMeetingSelection({
      hasLoadedMeetings: true,
      lockedMeetingIdRef,
      meetings: [meeting("meeting-1"), meeting("meeting-2")],
      onSelectedMeetingChange,
      requestedMeetingId: "meeting-2",
    }));

    await waitFor(() => expect(result.current.selectedMeetingId).toBe("meeting-1"));
    expect(onSelectedMeetingChange).toHaveBeenCalledWith("meeting-1");

    act(() => result.current.selectMeeting("meeting-2"));
    expect(result.current.selectedMeetingId).toBe("meeting-1");
    expect(onSelectedMeetingChange).toHaveBeenLastCalledWith("meeting-1");
  });
});
