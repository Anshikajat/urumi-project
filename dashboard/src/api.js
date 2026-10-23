// All requests go to /api/..., which Vite (and later nginx) forwards to the gateway.

export async function apiFetch(path, key, options = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + key,
      ...(options.headers || {}),
    },
  });

  let data = null;
  try {
    data = await response.json();
  } catch (e) {
    data = null;
  }

  if (!response.ok) {
    const message =
      data && typeof data.detail === "string"
        ? data.detail
        : "Request failed (" + response.status + ")";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  return data;
}