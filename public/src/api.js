export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET") headers["X-Coven-Intent"] = "ui-action";
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const payload = await response.json();
  if (!response.ok) {
    if (response.status === 401) window.location.assign("/");
    const error = new Error(payload.error || "Request failed");
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

export function postJson(path, payload) {
  return api(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function postBinary(path, body, headers = {}) {
  return api(path, {
    method: "POST",
    headers,
    body,
  });
}
