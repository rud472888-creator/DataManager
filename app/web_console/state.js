export const DEFAULT_TOKEN = "change-me";
const MAX_EVENTS = 40;

const COMMANDS_BY_STATE = {
  QUEUED: ["cancel"],
  SCANNING: ["cancel"],
  PREPARING: ["cancel"],
  COPYING: ["pause", "cancel"],
  PAUSING: ["cancel"],
  PAUSED: ["resume", "cancel"],
  WARN: ["retry"],
  FAILED: ["retry"],
  CANCELLED: ["retry"],
};

export function createState(token) {
  return {
    token: token || DEFAULT_TOKEN,
    runtimeStatus: null,
    jobs: [],
    volumes: [],
    events: [],
    socket: null,
    connectionState: "disconnected",
    consoleMessage: "",
  };
}

export function applySnapshot(state, snapshot) {
  state.runtimeStatus = snapshot.status;
  state.volumes = snapshot.volumes;
  state.jobs = snapshot.jobs;
}

export function recordEvent(state, event) {
  state.events = [...state.events, event].slice(-MAX_EVENTS);
}

export function splitVolumes(volumes) {
  return {
    sources: volumes.filter((item) => item.volume_role === "source"),
    destinations: volumes.filter((item) => item.volume_role === "destination"),
  };
}

export function allowedCommands(job) {
  return COMMANDS_BY_STATE[job.state] || [];
}

export function progressPercent(job) {
  const stats = job.stats || {};
  const totalFiles = Number(stats.total_files || 0);
  const processedFiles = Number(stats.processed_files || 0);
  if (totalFiles > 0) {
    return Math.min(100, Math.round((processedFiles / totalFiles) * 100));
  }
  const totalBytes = Number(stats.bytes_total || 0);
  const doneBytes = Number(stats.bytes_done || 0);
  if (totalBytes > 0) {
    return Math.min(100, Math.round((doneBytes / totalBytes) * 100));
  }
  return 0;
}

export function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatRate(value) {
  const rate = Number(value || 0);
  if (!Number.isFinite(rate) || rate <= 0) {
    return "—";
  }
  return `${rate.toFixed(rate >= 10 ? 0 : 1)} MB/s`;
}

export function formatEta(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "—";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function reportSummary(job, runtimeStatus) {
  const stubbed = new Set(runtimeStatus?.stubbed_components || []);
  if (stubbed.has("reports")) {
    return "Reports stay runtime-produced and remain stubbed in A2.";
  }
  if (job.state === "WARN" || job.state === "FAILED") {
    return "Check runtime output for report availability.";
  }
  return "Reports will appear only after the runtime generates them.";
}

export function dependencyMessages(runtimeStatus) {
  const dependencies = runtimeStatus?.dependencies || {};
  return Object.entries(dependencies).map(([name, info]) => {
    const details = typeof info === "object" && info !== null ? info : {};
    const status = details.status || "unknown";
    const message = details.message || "No detail provided";
    return {
      name,
      status,
      message,
    };
  });
}
