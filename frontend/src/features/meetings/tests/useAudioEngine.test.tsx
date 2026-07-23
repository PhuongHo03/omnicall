import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAudioEngine } from "../hooks/useAudioEngine";

describe("useAudioEngine", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses decoded Web Audio duration when WebM metadata has no finite duration", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)) }));
    vi.stubGlobal("AudioContext", class {
      decodeAudioData() {
        return Promise.resolve({
          duration: 1.3335,
          getChannelData: () => new Float32Array([0, 0.5, -0.25, 0.1]),
        });
      }
      close() {
        return Promise.resolve();
      }
    });

    const { result } = renderHook(() => useAudioEngine("blob:missing-duration"));
    await waitFor(() => expect(result.current.duration).toBeCloseTo(1.3335));

    const media = { currentTime: 0, duration: Number.POSITIVE_INFINITY } as HTMLAudioElement;
    result.current.mediaRef.current = media;
    act(() => result.current.seek(1));
    expect(media.currentTime).toBe(1);
    expect(result.current.currentTime).toBe(1);
  });
});
