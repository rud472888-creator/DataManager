export async function apiFetch(path, { token, ...options } = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return response.json();
}

export function fetchRuntimeStatus(token) {
  return apiFetch("/api/runtime/status", { token });
}

export function fetchVolumes(token) {
  return apiFetch("/api/volumes", { token });
}

export function fetchJobs(token) {
  return apiFetch("/api/jobs", { token });
}

export function createJob(token, payload) {
  return apiFetch("/api/jobs", {
    token,
    method: "POST",
    body: JSON.stringify({
      ...payload,
      operator_origin: "remote_web",
    }),
  });
}

export function sendJobCommand(token, jobId, command) {
  return apiFetch(`/api/jobs/${jobId}/command`, {
    token,
    method: "POST",
    body: JSON.stringify({
      command,
      operator_origin: "remote_web",
    }),
  });
}
