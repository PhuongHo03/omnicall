import "fake-indexeddb/auto";

import { beforeEach, describe, expect, it } from "vitest";

import {
  buildRecordingFile,
  deleteRecordingSession,
  listRecordingSessions,
  readRecordingChunks,
  saveRecordingChunk,
  saveRecordingSession,
} from "../api/recordingStorage";
import type { StoredRecordingSession } from "../types/meetingTypes";

const DATABASE_NAME = "omnicall-meeting-recordings";

function deleteDatabase(): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(DATABASE_NAME);
    request.addEventListener("success", () => resolve());
    request.addEventListener("error", () => reject(request.error));
  });
}

function session(id: string, ownerId: string): StoredRecordingSession {
  return {
    id,
    ownerId,
    meetingId: id.split(":").at(-1) ?? id,
    phase: "recording",
    mimeType: "audio/webm",
    fileName: `${id}.webm`,
    startedAt: 1,
    updatedAt: 2,
    durationMs: 1000,
    chunkCount: 2,
    uploadProgress: null,
    isPartial: false,
    error: null,
  };
}

describe("recordingStorage", () => {
  beforeEach(async () => {
    await deleteDatabase();
  });

  it("isolates saved sessions by owner", async () => {
    await saveRecordingSession(session("owner-1:meeting-1", "owner-1"));
    await saveRecordingSession(session("owner-2:meeting-2", "owner-2"));

    expect((await listRecordingSessions("owner-1")).map((item) => item.id)).toEqual(["owner-1:meeting-1"]);
    expect((await listRecordingSessions("owner-2")).map((item) => item.id)).toEqual(["owner-2:meeting-2"]);
  });

  it("rebuilds a file from ordered chunks and deletes all persisted data", async () => {
    const saved = session("owner-1:meeting-1", "owner-1");
    await saveRecordingSession(saved);
    await saveRecordingChunk({ sessionId: saved.id, sequence: 1, data: new TextEncoder().encode("second").buffer, createdAt: 2 });
    await saveRecordingChunk({ sessionId: saved.id, sequence: 0, data: new TextEncoder().encode("first-").buffer, createdAt: 1 });

    const file = await buildRecordingFile(saved);
    expect(await file.text()).toBe("first-second");
    expect((await readRecordingChunks(saved.id)).map((item) => item.sequence)).toEqual([0, 1]);

    await deleteRecordingSession(saved.id);
    expect(await listRecordingSessions("owner-1")).toEqual([]);
    expect(await readRecordingChunks(saved.id)).toEqual([]);
  });
});
