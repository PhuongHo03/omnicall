import type { StoredRecordingChunk, StoredRecordingSession } from "../types/meetingTypes";

const DATABASE_NAME = "omnicall-meeting-recordings";
const DATABASE_VERSION = 1;
const SESSION_STORE = "sessions";
const CHUNK_STORE = "chunks";

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.addEventListener("success", () => resolve(request.result));
    request.addEventListener("error", () => reject(request.error ?? new Error("IndexedDB request failed.")));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.addEventListener("complete", () => resolve());
    transaction.addEventListener("abort", () => reject(transaction.error ?? new Error("IndexedDB transaction aborted.")));
    transaction.addEventListener("error", () => reject(transaction.error ?? new Error("IndexedDB transaction failed.")));
  });
}

async function openRecordingDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") {
    throw new Error("Browser recording storage is unavailable.");
  }
  const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
  request.addEventListener("upgradeneeded", () => {
    const database = request.result;
    if (!database.objectStoreNames.contains(SESSION_STORE)) {
      const sessions = database.createObjectStore(SESSION_STORE, { keyPath: "id" });
      sessions.createIndex("ownerId", "ownerId", { unique: false });
    }
    if (!database.objectStoreNames.contains(CHUNK_STORE)) {
      const chunks = database.createObjectStore(CHUNK_STORE, { keyPath: ["sessionId", "sequence"] });
      chunks.createIndex("sessionId", "sessionId", { unique: false });
    }
  });
  return requestResult(request);
}

export function recordingSessionId(ownerId: string, meetingId: string): string {
  return `${ownerId}:${meetingId}`;
}

export async function saveRecordingSession(session: StoredRecordingSession): Promise<void> {
  const database = await openRecordingDatabase();
  try {
    const transaction = database.transaction(SESSION_STORE, "readwrite");
    transaction.objectStore(SESSION_STORE).put(session);
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}

export async function saveRecordingChunk(chunk: StoredRecordingChunk): Promise<void> {
  const database = await openRecordingDatabase();
  try {
    const transaction = database.transaction(CHUNK_STORE, "readwrite");
    transaction.objectStore(CHUNK_STORE).put(chunk);
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}

export async function listRecordingSessions(ownerId: string): Promise<StoredRecordingSession[]> {
  const database = await openRecordingDatabase();
  try {
    const transaction = database.transaction(SESSION_STORE, "readonly");
    const request = transaction.objectStore(SESSION_STORE).index("ownerId").getAll(ownerId);
    const sessions = await requestResult(request);
    await transactionDone(transaction);
    return sessions.sort((left, right) => right.updatedAt - left.updatedAt);
  } finally {
    database.close();
  }
}

export async function readRecordingChunks(sessionId: string): Promise<StoredRecordingChunk[]> {
  const database = await openRecordingDatabase();
  try {
    const transaction = database.transaction(CHUNK_STORE, "readonly");
    const request = transaction.objectStore(CHUNK_STORE).index("sessionId").getAll(sessionId);
    const chunks = await requestResult(request);
    await transactionDone(transaction);
    return chunks.sort((left, right) => left.sequence - right.sequence);
  } finally {
    database.close();
  }
}

export async function deleteRecordingSession(sessionId: string): Promise<void> {
  const database = await openRecordingDatabase();
  try {
    const transaction = database.transaction([SESSION_STORE, CHUNK_STORE], "readwrite");
    transaction.objectStore(SESSION_STORE).delete(sessionId);
    const chunkStore = transaction.objectStore(CHUNK_STORE);
    const cursorRequest = chunkStore.index("sessionId").openKeyCursor(IDBKeyRange.only(sessionId));
    cursorRequest.addEventListener("success", () => {
      const cursor = cursorRequest.result;
      if (!cursor) return;
      chunkStore.delete(cursor.primaryKey);
      cursor.continue();
    });
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}

export async function buildRecordingFile(session: StoredRecordingSession): Promise<File> {
  const chunks = await readRecordingChunks(session.id);
  if (chunks.length === 0) {
    throw new Error("The recovered recording contains no audio data.");
  }
  return new File(chunks.map((chunk) => chunk.data), session.fileName, { type: session.mimeType });
}
