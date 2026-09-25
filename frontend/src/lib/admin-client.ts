/**
 * Client-side helper for mutating API calls.
 *
 * Every POST/DELETE to /api/* is gated by middleware behind the ADMIN_PIN
 * server env var, so mutations must carry an "x-admin-pin" header. The PIN
 * is prompted once, kept in localStorage, and retried on 401 (e.g. after a
 * PIN change).
 */

const PIN_STORAGE_KEY = "areopagus_admin_pin";

export function getAdminPin(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(PIN_STORAGE_KEY) || "";
}

async function doFetch(input: RequestInfo | URL, init: RequestInit | undefined, pin: string) {
  const headers = new Headers(init?.headers);
  if (pin) {
    headers.set("x-admin-pin", pin);
  }
  if (typeof init?.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(input, { ...init, headers });
}

export async function adminFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  let response = await doFetch(input, init, getAdminPin());

  if (response.status === 401 && typeof window !== "undefined") {
    const pin = window.prompt("Enter the admin PIN to continue:");
    if (pin) {
      window.localStorage.setItem(PIN_STORAGE_KEY, pin.trim());
      response = await doFetch(input, init, pin.trim());
    }
  }

  return response;
}
