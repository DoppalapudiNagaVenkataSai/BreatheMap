/**
 * Resilient API client with demo header support
 */
import { state, KEYS } from "./state.js";

export async function fetchApi(endpoint, options = {}) {
  const isDemo = state.get(KEYS.DEMO, false);
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };

  if (isDemo) {
    headers["X-BreatheMap-Demo"] = "true";
  }

  const res = await fetch(endpoint, { ...options, headers });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Request failed with status ${res.status}`;
    throw new Error(message);
  }
  const json = await res.json();
  return json.data;
}
