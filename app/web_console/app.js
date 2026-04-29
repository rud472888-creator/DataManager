const runtimeState = document.querySelector("#runtime-state");
const runtimeMessage = document.querySelector("#runtime-message");
const statusBanner = document.querySelector("#status-banner");
const activeJob = document.querySelector("#active-job");
const jobState = document.querySelector("#job-state");
const jobForm = document.querySelector("#job-form");
const jobFormState = document.querySelector("#job-form-state");
const commandState = document.querySelector("#command-state");
const jobsList = document.querySelector("#jobs-list");
const reportsList = document.querySelector("#reports-list");
const settingsState = document.querySelector("#settings-state");

const sourceSelect = document.querySelector("#source-select");
const mainSelect = document.querySelector("#main-select");
const backupSelect = document.querySelector("#backup-select");
const projectName = document.querySelector("#project-name");
const apiToken = document.querySelector("#api-token");
const operatorName = document.querySelector("#operator-name");

let selectedJobId = null;

function scheduleRefresh() {
  for (const delay of [250, 1000, 2500]) {
    window.setTimeout(() => {
      loadJobs();
      loadReports();
    }, delay);
  }
}

function authHeaders() {
  return { Authorization: `Bearer ${apiToken.value || "change-me"}` };
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) throw new Error(`${url} failed: ${response.status}`);
  return response.json();
}

function renderStatus(status) {
  runtimeState.textContent = status.runtime;
  runtimeMessage.textContent = status.messages?.[0] ?? "Runtime status received.";
  statusBanner.textContent =
    "Connected. Real file operations run on the local runtime, not in this browser.";
}

function fillSelect(select, items, includeEmpty = false) {
  select.replaceChildren();
  if (includeEmpty) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No backup";
    select.append(option);
  }
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.volume_id;
    option.textContent = `${item.label} (${item.status})`;
    select.append(option);
  }
}

async function loadVolumes() {
  const payload = await jsonFetch("/api/volumes");
  fillSelect(sourceSelect, payload.sources);
  fillSelect(mainSelect, payload.destinations);
  fillSelect(backupSelect, payload.destinations, true);
  jobFormState.textContent = `${payload.sources.length} source and ${payload.destinations.length} destination option loaded from runtime.`;
}

function renderJobs(payload) {
  jobsList.replaceChildren();
  if (!payload.jobs.length) {
    jobsList.textContent = "No jobs yet.";
    return;
  }
  for (const job of payload.jobs) {
    const button = document.createElement("button");
    button.className = job.job_id === selectedJobId ? "row selected" : "row";
    button.type = "button";
    button.textContent = `${job.project_name} - ${job.state}`;
    button.addEventListener("click", () => selectJob(job));
    jobsList.append(button);
  }
}

function selectJob(job) {
  selectedJobId = job.job_id;
  activeJob.textContent = job.job_id;
  jobState.textContent = job.state;
  loadReports();
  loadJobs();
}

async function loadJobs() {
  const payload = await jsonFetch("/api/jobs");
  renderJobs(payload);
  if (!selectedJobId && payload.jobs.length) selectJob(payload.jobs[0]);
}

async function loadReports() {
  if (!selectedJobId) return;
  const payload = await jsonFetch(`/api/jobs/${selectedJobId}/reports`);
  reportsList.replaceChildren();
  if (!payload.reports.length) {
    reportsList.textContent = "No report artifacts for this job yet.";
    return;
  }
  for (const report of payload.reports) {
    const item = document.createElement(report.status === "ready" ? "a" : "div");
    item.className = "row";
    item.textContent = `${report.report_type} - ${report.status}`;
    if (report.status === "ready") item.href = report.download_url;
    reportsList.append(item);
  }
}

jobForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await jsonFetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        project_name: projectName.value || "Untitled",
        source_volume_id: sourceSelect.value,
        dest_main_id: mainSelect.value,
        dest_backup_id: backupSelect.value || null,
        operator_origin: operatorName.value || "remote_web",
        policy: {},
      }),
    });
    jobFormState.textContent = "Job request queued by the local runtime.";
    selectJob(payload.job);
    scheduleRefresh();
  } catch (error) {
    jobFormState.textContent = error instanceof Error ? error.message : "Unable to create job.";
  }
});

document.querySelectorAll("[data-command]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!selectedJobId) {
      commandState.textContent = "Select a job before sending a command request.";
      return;
    }
    try {
      const payload = await jsonFetch(`/api/jobs/${selectedJobId}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          command: button.dataset.command,
          operator_origin: operatorName.value || "remote_web",
          request_id: `ui-${Date.now()}`,
        }),
      });
      commandState.textContent = `${payload.command} ${payload.accepted ? "accepted" : "rejected"}: ${payload.reason}`;
      await loadJobs();
      scheduleRefresh();
    } catch (error) {
      commandState.textContent = error instanceof Error ? error.message : "Command failed.";
    }
  });
});

document.querySelector("#save-settings").addEventListener("click", async () => {
  try {
    await jsonFetch("/api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ operator_name: operatorName.value }),
    });
    settingsState.textContent = "Settings request saved through the local runtime API.";
  } catch (error) {
    settingsState.textContent = error instanceof Error ? error.message : "Settings request failed.";
  }
});

function connectRuntimeSocket() {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws/runtime`);
  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "runtime_status") renderStatus(payload);
  });
}

try {
  renderStatus(await jsonFetch("/api/runtime/status"));
  await loadVolumes();
  await loadJobs();
  connectRuntimeSocket();
} catch (error) {
  runtimeState.textContent = "offline";
  runtimeMessage.textContent = error instanceof Error ? error.message : "Unable to load runtime.";
  statusBanner.textContent = "Disconnected. Browser console cannot execute file work.";
}
