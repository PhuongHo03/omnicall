export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  options: { maxRetries?: number; baseDelayMs?: number; shouldRetry?: (error: unknown) => boolean; signal?: AbortSignal } = {}
): Promise<T> {
  const { maxRetries = 2, baseDelayMs = 1000, shouldRetry = isNetworkError, signal } = options;

  let lastError: unknown;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (signal?.aborted) {
      throw signal.reason ?? new DOMException("The operation was aborted.", "AbortError");
    }
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      // Never retry on abort
      if (error instanceof Error && error.name === "AbortError") {
        throw error;
      }
      if (attempt >= maxRetries || !shouldRetry(error)) {
        throw error;
      }
      const delay = baseDelayMs * Math.pow(2, attempt);
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(resolve, delay);
        signal?.addEventListener("abort", () => {
          clearTimeout(timer);
          reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
        }, { once: true });
      });
    }
  }
  throw lastError;
}

function isNetworkError(error: unknown): boolean {
  if (error instanceof TypeError) return true;
  if (error instanceof Error && /network|fetch|load failed|failed to fetch|connection/i.test(error.message)) {
    return true;
  }
  return false;
}
