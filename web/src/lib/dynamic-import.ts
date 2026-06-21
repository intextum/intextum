const DEFAULT_RETRY_DELAY_MS = 250;
const DEFAULT_RETRY_ATTEMPTS = 2;

const wait = (delayMs: number) =>
  new Promise((resolve) => {
    globalThis.setTimeout(resolve, delayMs);
  });

const isDynamicImportFetchError = (error: unknown) => {
  if (!(error instanceof TypeError)) {
    return false;
  }
  return error.message.includes("Failed to fetch dynamically imported module");
};

export const retryDynamicImport = async <TModule>(
  loader: () => Promise<TModule>,
  options: {
    attempts?: number;
    retryDelayMs?: number;
  } = {},
): Promise<TModule> => {
  const attempts = Math.max(1, options.attempts ?? DEFAULT_RETRY_ATTEMPTS);
  const retryDelayMs = options.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await loader();
    } catch (error) {
      lastError = error;
      if (!isDynamicImportFetchError(error) || attempt === attempts - 1) {
        break;
      }
      await wait(retryDelayMs);
    }
  }

  throw lastError;
};
