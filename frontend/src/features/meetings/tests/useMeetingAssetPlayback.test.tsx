import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { downloadMeetingAsset } from "../api/meetingApi";
import { useMeetingAssetPlayback } from "../hooks/useMeetingAssetPlayback";
import type { Meeting, MeetingAsset } from "../types/meetingTypes";

vi.mock("../api/meetingApi", () => ({ downloadMeetingAsset: vi.fn() }));

const meeting: Meeting = {
  id: "meeting-1",
  title: "Call",
    status: "UPLOADED",
    failureCode: null,
    failureReason: null,
  pendingChatStatus: null,
  createdAt: "2026-07-16T00:00:00Z",
  updatedAt: "2026-07-16T00:00:00Z",
  latestAsset: null,
  retryAllowed: false,
};

const asset: MeetingAsset = {
  id: "asset-1",
  meetingId: "meeting-1",
  objectKey: "call.webm",
  fileName: "call.webm",
  contentType: "audio/webm",
  sizeBytes: 10,
  createdAt: "2026-07-16T00:00:01Z",
};

describe("useMeetingAssetPlayback", () => {
  const createObjectUrl = vi.fn(() => "blob:asset-1");
  const revokeObjectUrl = vi.fn();

  beforeEach(() => {
    vi.mocked(downloadMeetingAsset).mockReset();
    createObjectUrl.mockClear();
    revokeObjectUrl.mockClear();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
  });

  it("moves through loading and ready, then revokes the URL when the asset is cleared", async () => {
    vi.mocked(downloadMeetingAsset).mockResolvedValue(new Blob(["audio"], { type: "audio/webm" }));
    const onError = vi.fn();
    const { result, rerender } = renderHook(
      ({ selected, latest }) => useMeetingAssetPlayback("token", selected, latest, onError),
      { initialProps: { selected: meeting as Meeting | null, latest: asset as MeetingAsset | null } },
    );

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", url: "blob:asset-1" }));
    expect(downloadMeetingAsset).toHaveBeenCalledWith("token", "meeting-1", "asset-1", expect.objectContaining({ signal: expect.any(AbortSignal) }));

    act(() => rerender({ selected: null, latest: null }));
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:asset-1");
  });

  it("exposes a playback error without creating an object URL", async () => {
    vi.mocked(downloadMeetingAsset).mockRejectedValue(new Error("Playback unavailable"));
    const onError = vi.fn();
    const { result } = renderHook(() => useMeetingAssetPlayback("token", meeting, asset, onError));

    await waitFor(() => expect(result.current).toMatchObject({ status: "error", error: "Playback unavailable", url: null }));
    expect(onError).toHaveBeenCalledWith("Playback unavailable");
    expect(createObjectUrl).not.toHaveBeenCalled();
  });
});
