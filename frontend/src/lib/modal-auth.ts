/**
 * Shared headers for authenticated requests to Modal backend endpoints.
 * Reads AREOPAGUS_API_KEY from server-side env vars and injects it as X-API-Key.
 */
export function modalAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const apiKey = process.env.AREOPAGUS_API_KEY;
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  return headers;
}
