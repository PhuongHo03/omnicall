import { afterEach, describe, expect, it, vi } from "vitest";

import {
  askMeetingChat,
  isChatBusyError,
  MeetingChatApiError,
} from "../api/meetingApi";

describe("meeting chat API errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("preserves the chat_busy code from an HTTP 409 response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: "chat_busy", message: "An answer is already being generated." }),
      {
        status: 409,
        headers: { "Content-Type": "application/json" },
      },
    )));

    const request = askMeetingChat("token", "meeting-1", "Who is the customer?");

    await expect(request).rejects.toMatchObject({
      name: "MeetingChatApiError",
      status: 409,
      code: "chat_busy",
    });
    await request.catch((error: unknown) => {
      expect(error).toBeInstanceOf(MeetingChatApiError);
      expect(isChatBusyError(error)).toBe(true);
    });
  });
});
