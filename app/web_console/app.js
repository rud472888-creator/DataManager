import {
  applySnapshot,
  allowedCommands,
  createState,
  DEFAULT_TOKEN,
  dependencyMessages,
  formatBytes,
  formatEta,
  formatRate,
  progressPercent,
  recordEvent,
  reportSummary,
  splitVolumes,
} from "./state.js";
import {
  createJob,
  fetchJobs,
  fetchRuntimeStatus,
  fetchVolumes,
  sendJobCommand,
} from "./api.js";
import { connectEvents } from "./ws.js";

const tokenInput = document.querySelector("#tokenInput");
const reloadButton = document.querySelector("#reloadButton");
const consoleMessageNode = document.querySelector("#consoleMessage");
const connectionBadgeNode = document.querySelector("#connectionBadge");
const runtimeSummaryNode = document.querySelector("#runtimeSummary");
const runtimeWarningsNode = document.querySelector("#runtimeWarnings");
const sourceVolumeListNode = document.querySelector("#sourceVolumeList");
const destinationVolumeListNode = document.querySelector("#destinationVolumeList");
const sourceSelect = document.querySelector("#sourceSelect");
const mainDestSelect = document.querySelector("#mainDestSelect");
const backupDestSelect = document.querySelector("#backupDestSelect");
const jobForm = document.querySelector("#jobForm");
const projectNameInput = document.querySelector("#projectName");
const jobsNode = document.querySelector("#jobs");
const eventFeedNode = document.querySelector("#eventFeed");

const state = createState(new URLSearchParams(window.location.search).get("token") || DEFAULT_TOKEN);
tokenInput.value = state.token;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setConsoleMessage(message = "") {
  state.consoleMessage = message;
  consoleMessageNode.textContent = message;
  consoleMessageNode.hidden = !message;
}

function renderConnectionState() {
  connectionBadgeNode.textContent = state.connectionState;
  connectionBadgeNode.dataset.tone =
    state.connectionState === "connected"
      ? "good"
      : state.connectionState === "error"
        ? "danger"
        : "neutral";
}

function renderRuntimeSummary() {
  const runtimeStatus = state.runtimeStatus;
  if (!runtimeStatus) {
    runtimeSummaryNode.innerHTML = "<p class=\"empty-state\">Waiting for runtime status…</p>";
    runtimeWarningsNode.innerHTML = "";
    return;
  }
  const dependencyRows = dependencyMessages(runtimeStatus);
  const stubbed = runtimeStatus.stubbed_components || [];
  runtimeSummaryNode.innerHTML = `
    <article class="metric-card">
      <p class="metric-label">Runtime</p>
      <strong>${escapeHtml(runtimeStatus.status)}</strong>
      <p>${escapeHtml(runtimeStatus.app_name)} ${escapeHtml(runtimeStatus.app_version)}</p>
    </article>
    <article class="metric-card">
      <p class="metric-label">Queue depth</p>
      <strong>${escapeHtml(runtimeStatus.queue_depth)}</strong>
      <p>Active job: ${escapeHtml(runtimeStatus.active_job_id || "none")}</p>
    </article>
    <article class="metric-card">
      <p class="metric-label">Runtime-owned output</p>
      <strong>${escapeHtml(stubbed.length ? "partial" : "ready")}</strong>
      <p>${escapeHtml(stubbed.length ? stubbed.join(", ") : "No stubbed components reported")}</p>
    </article>
    <article class="metric-card">
      <p class="metric-label">Started</p>
      <strong>${escapeHtml(runtimeStatus.started_at)}</strong>
      <p>DB: ${escapeHtml(runtimeStatus.db_path)}</p>
    </article>
  `;
  runtimeWarningsNode.innerHTML = dependencyRows
    .map(
      (item) => `
        <li class="notice" data-tone="${item.status === "ok" ? "good" : "warn"}">
          <strong>${escapeHtml(item.name)}</strong>
          <span>${escapeHtml(item.status)}</span>
          <p>${escapeHtml(item.message)}</p>
        </li>
      `
    )
    .join("");
}

function volumeListMarkup(items, emptyMessage) {
  if (!items.length) {
    return `<li class="empty-state">${escapeHtml(emptyMessage)}</li>`;
  }
  return items
    .map(
      (item) => `
        <li class="volume-row">
          <div>
            <strong>${escapeHtml(item.display_name)}</strong>
            <p>${escapeHtml(item.volume_id)}</p>
          </div>
          <div class="volume-meta">
            <span>${escapeHtml(item.approval_state || "unknown")}</span>
            <span>${escapeHtml(formatBytes(item.free_bytes))} free</span>
          </div>
        </li>
      `
    )
    .join("");
}

function renderVolumes() {
  const { sources, destinations } = splitVolumes(state.volumes);
  sourceVolumeListNode.innerHTML = volumeListMarkup(
    sources,
    "No runtime-detected source volumes yet."
  );
  destinationVolumeListNode.innerHTML = volumeListMarkup(
    destinations,
    "No approved destination volumes yet."
  );

  sourceSelect.innerHTML = sources
    .map((item) => `<option value="${escapeHtml(item.volume_id)}">${escapeHtml(item.display_name)}</option>`)
    .join("");
  mainDestSelect.innerHTML = destinations
    .map((item) => `<option value="${escapeHtml(item.volume_id)}">${escapeHtml(item.display_name)}</option>`)
    .join("");
  backupDestSelect.innerHTML = ['<option value="">None</option>']
    .concat(
      destinations.map(
        (item) => `<option value="${escapeHtml(item.volume_id)}">${escapeHtml(item.display_name)}</option>`
      )
    )
    .join("");
}

function renderJobs() {
  if (!state.jobs.length) {
    jobsNode.innerHTML = `
      <article class="empty-panel">
        <h3>No jobs yet</h3>
        <p>Create a runtime-owned job from detected volumes. The browser only submits commands and watches progress.</p>
      </article>
    `;
    return;
  }
  jobsNode.innerHTML = state.jobs
    .map((job) => {
      const stats = job.stats || {};
      const availableCommands = new Set(allowedCommands(job));
      return `
        <article class="job-card" data-state="${escapeHtml(job.state)}">
          <header class="job-header">
            <div>
              <p class="eyebrow">Job ${escapeHtml(job.job_id)}</p>
              <h3>${escapeHtml(job.project_name)}</h3>
            </div>
            <span class="state-pill">${escapeHtml(job.state)}</span>
          </header>
          <div class="job-meta">
            <span>Step: ${escapeHtml(job.current_step || "unknown")}</span>
            <span>File: ${escapeHtml(job.current_file_relpath || "—")}</span>
            <span>Origin: ${escapeHtml(job.operator_origin || "unknown")}</span>
          </div>
          <div class="progress-block">
            <div class="progress-row">
              <strong>${escapeHtml(progressPercent(job))}%</strong>
              <span>${escapeHtml(stats.processed_files || 0)}/${escapeHtml(stats.total_files || 0)} files</span>
              <span>${escapeHtml(formatBytes(stats.bytes_done))} / ${escapeHtml(formatBytes(stats.bytes_total))}</span>
            </div>
            <div class="progress-bar" aria-hidden="true">
              <span style="width: ${progressPercent(job)}%"></span>
            </div>
            <div class="job-meta">
              <span>Speed: ${escapeHtml(formatRate(stats.speed_mbps))}</span>
              <span>ETA: ${escapeHtml(formatEta(stats.eta_sec))}</span>
              <span>Warnings: ${escapeHtml(job.warning_count)}</span>
              <span>Errors: ${escapeHtml(job.error_count)}</span>
            </div>
          </div>
          <div class="job-notes">
            <p><strong>Runtime message:</strong> ${escapeHtml(stats.message || "No progress message yet.")}</p>
            <p><strong>Reports:</strong> ${escapeHtml(reportSummary(job, state.runtimeStatus))}</p>
          </div>
          <div class="actions">
            ${["pause", "resume", "cancel", "retry"]
              .map(
                (command) => `
                  <button
                    type="button"
                    data-command="${command}"
                    data-job-id="${escapeHtml(job.job_id)}"
                    ${availableCommands.has(command) ? "" : "disabled"}
                  >
                    ${command}
                  </button>
                `
              )
              .join("")}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderEvents() {
  const recentEvents = [...state.events].reverse().slice(0, 20);
  if (!recentEvents.length) {
    eventFeedNode.innerHTML = "<li class=\"empty-state\">Waiting for runtime events…</li>";
    return;
  }
  eventFeedNode.innerHTML = recentEvents
    .map((event) => {
      const payload = event.payload || {};
      const message = payload.message || payload.state || payload.command || "Event received";
      return `
        <li class="event-row">
          <div>
            <strong>${escapeHtml(event.type)}</strong>
            <p>${escapeHtml(message)}</p>
          </div>
          <div class="event-meta">
            <span>${escapeHtml(event.job_id || "runtime")}</span>
            <span>${escapeHtml(event.timestamp)}</span>
          </div>
        </li>
      `;
    })
    .join("");
}

async function loadRuntime() {
  const [status, volumesPayload, jobsPayload] = await Promise.all([
    fetchRuntimeStatus(state.token),
    fetchVolumes(state.token),
    fetchJobs(state.token),
  ]);
  applySnapshot(state, {
    status,
    volumes: volumesPayload.items,
    jobs: jobsPayload.items,
  });
  renderRuntimeSummary();
  renderVolumes();
  renderJobs();
}

function reconnectEvents() {
  if (state.socket) {
    state.socket.close();
  }
  state.socket = connectEvents({
    token: state.token,
    onStatusChange(nextState) {
      state.connectionState = nextState;
      renderConnectionState();
    },
    async onEvent(event) {
      recordEvent(state, event);
      renderEvents();
      if (
        event.type.startsWith("job.") ||
        event.type.startsWith("runtime.") ||
        event.type.startsWith("volume.")
      ) {
        try {
          await loadRuntime();
        } catch (error) {
          setConsoleMessage(`Refresh failed after event: ${error.message}`);
        }
      }
    },
    onError(error) {
      setConsoleMessage(`Event stream error: ${error.message}`);
      recordEvent(state, {
        event_id: null,
        type: "ui.error",
        timestamp: new Date().toISOString(),
        job_id: null,
        payload: { message: error.message },
      });
      renderEvents();
    },
  });
}

jobForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setConsoleMessage("");
    await createJob(state.token, {
      project_name: projectNameInput.value,
      source_volume_id: sourceSelect.value,
      dest_main_id: mainDestSelect.value,
      dest_backup_id: backupDestSelect.value || null,
      policy: {},
    });
    await loadRuntime();
  } catch (error) {
    setConsoleMessage(`Create job failed: ${error.message}`);
  }
});

jobsNode.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-command]");
  if (!button || button.disabled) {
    return;
  }
  try {
    setConsoleMessage("");
    const result = await sendJobCommand(state.token, button.dataset.jobId, button.dataset.command);
    setConsoleMessage(result.message);
    await loadRuntime();
  } catch (error) {
    setConsoleMessage(`Command failed: ${error.message}`);
  }
});

reloadButton.addEventListener("click", async () => {
  state.token = tokenInput.value || DEFAULT_TOKEN;
  tokenInput.value = state.token;
  try {
    setConsoleMessage("");
    await loadRuntime();
    reconnectEvents();
  } catch (error) {
    setConsoleMessage(`Reconnect failed: ${error.message}`);
  }
});

renderConnectionState();
renderRuntimeSummary();
renderVolumes();
renderJobs();
renderEvents();

loadRuntime()
  .then(() => {
    reconnectEvents();
  })
  .catch((error) => {
    setConsoleMessage(`Initial load failed: ${error.message}`);
    reconnectEvents();
  });
