const statusNode = document.querySelector("#status");
const volumesNode = document.querySelector("#volumes");
const eventNode = document.querySelector("#event");
const jobsNode = document.querySelector("#jobs");
const tokenInput = document.querySelector("#tokenInput");
const reloadButton = document.querySelector("#reloadButton");
const jobForm = document.querySelector("#jobForm");
const projectNameInput = document.querySelector("#projectName");
const sourceSelect = document.querySelector("#sourceSelect");
const mainDestSelect = document.querySelector("#mainDestSelect");
const backupDestSelect = document.querySelector("#backupDestSelect");

const state = {
  token: new URLSearchParams(window.location.search).get("token") || "change-me",
  jobs: [],
  volumes: [],
  events: [],
  socket: null,
};

tokenInput.value = state.token;

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${state.token}`,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return response.json();
}

function renderVolumes() {
  volumesNode.textContent = JSON.stringify(state.volumes, null, 2);
  const sources = state.volumes.filter((item) => item.volume_role === "source");
  const destinations = state.volumes.filter((item) => item.volume_role === "destination");
  sourceSelect.innerHTML = sources
    .map((item) => `<option value="${item.volume_id}">${item.display_name}</option>`)
    .join("");
  const destinationOptions = ['<option value="">None</option>']
    .concat(destinations.map((item) => `<option value="${item.volume_id}">${item.display_name}</option>`));
  mainDestSelect.innerHTML = destinations
    .map((item) => `<option value="${item.volume_id}">${item.display_name}</option>`)
    .join("");
  backupDestSelect.innerHTML = destinationOptions.join("");
}

function renderJobs() {
  jobsNode.innerHTML = "";
  if (!state.jobs.length) {
    jobsNode.innerHTML = "<p>No jobs yet.</p>";
    return;
  }
  state.jobs.forEach((job) => {
    const wrapper = document.createElement("article");
    wrapper.className = "job-card";
    wrapper.innerHTML = `
      <header>
        <strong>${job.project_name}</strong>
        <span class="state">${job.state}</span>
      </header>
      <p>${job.current_step}</p>
      <p>File: ${job.current_file_relpath || "-"}</p>
      <p>Progress: ${job.stats.processed_files || 0}/${job.stats.total_files || 0}</p>
      <p>Warnings: ${job.warning_count} Errors: ${job.error_count}</p>
      <div class="actions">
        <button data-command="pause" data-job-id="${job.job_id}">Pause</button>
        <button data-command="resume" data-job-id="${job.job_id}">Resume</button>
        <button data-command="cancel" data-job-id="${job.job_id}">Cancel</button>
        <button data-command="retry" data-job-id="${job.job_id}">Retry</button>
      </div>
      <pre>${JSON.stringify(job.stats, null, 2)}</pre>
    `;
    jobsNode.appendChild(wrapper);
  });
}

function renderEvents() {
  const recent = state.events.slice(-12);
  eventNode.textContent = JSON.stringify(recent, null, 2);
}

async function loadRuntime() {
  const status = await apiFetch("/api/runtime/status");
  statusNode.textContent = JSON.stringify(status, null, 2);
  const volumes = await apiFetch("/api/volumes");
  state.volumes = volumes.items;
  renderVolumes();
  const jobs = await apiFetch("/api/jobs");
  state.jobs = jobs.items;
  renderJobs();
}

function connectEvents() {
  if (state.socket) {
    state.socket.close();
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.socket = new WebSocket(
    `${protocol}://${window.location.host}/ws/events?token=${encodeURIComponent(state.token)}`
  );
  state.socket.addEventListener("message", async (message) => {
    try {
      const payload = JSON.parse(message.data);
      state.events.push(payload);
      renderEvents();
      if (payload.type.startsWith("job.") || payload.type.startsWith("runtime.") || payload.type.startsWith("volume.")) {
        await loadRuntime();
      }
    } catch (error) {
      eventNode.textContent = `Failed to parse event: ${error}`;
    }
  });
  state.socket.addEventListener("error", () => {
    state.events.push({ type: "ui.error", message: "WebSocket error" });
    renderEvents();
  });
}

jobForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await apiFetch("/api/jobs", {
    method: "POST",
    body: JSON.stringify({
      project_name: projectNameInput.value,
      source_volume_id: sourceSelect.value,
      dest_main_id: mainDestSelect.value,
      dest_backup_id: backupDestSelect.value || null,
      policy: {},
    }),
  });
  await loadRuntime();
});

jobsNode.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-command]");
  if (!button) {
    return;
  }
  await apiFetch(`/api/jobs/${button.dataset.jobId}/command`, {
    method: "POST",
    body: JSON.stringify({ command: button.dataset.command }),
  });
  await loadRuntime();
});

reloadButton.addEventListener("click", async () => {
  state.token = tokenInput.value;
  await loadRuntime();
  connectEvents();
});

loadRuntime().catch((error) => {
  statusNode.textContent = `Status request failed: ${error}`;
});
connectEvents();
