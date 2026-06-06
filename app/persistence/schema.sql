PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  project_name TEXT NOT NULL,
  source_path_ids_json TEXT NOT NULL,
  replica_path_ids_json TEXT NOT NULL,
  state TEXT NOT NULL,
  current_step TEXT,
  stats_json TEXT NOT NULL DEFAULT '{}',
  policy_json TEXT NOT NULL DEFAULT '{}',
  operator_origin TEXT NOT NULL,
  recovery_cursor_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at TEXT,
  ended_at TEXT
);

CREATE TABLE IF NOT EXISTS job_events (
  event_id TEXT PRIMARY KEY,
  job_id TEXT REFERENCES jobs(job_id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  state_before TEXT,
  state_after TEXT,
  command TEXT,
  accepted INTEGER,
  reason TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  operator_origin TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_files (
  file_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  source_path_id TEXT NOT NULL,
  source_relpath TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  checksum_source TEXT,
  status TEXT NOT NULL,
  error_code TEXT,
  error_message TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_file_replicas (
  file_id TEXT NOT NULL REFERENCES job_files(file_id) ON DELETE CASCADE,
  path_id TEXT NOT NULL,
  dest_relpath TEXT,
  checksum TEXT,
  status TEXT NOT NULL,
  error_code TEXT,
  error_message TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (file_id, path_id)
);

CREATE TABLE IF NOT EXISTS clips (
  clip_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  file_id TEXT NOT NULL REFERENCES job_files(file_id) ON DELETE CASCADE,
  format_name TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  integrity_status TEXT NOT NULL,
  capture_status TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
  report_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  report_type TEXT NOT NULL,
  artifact_relpath TEXT NOT NULL,
  status TEXT NOT NULL,
  checksum TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_id, report_type)
);

CREATE TABLE IF NOT EXISTS system_volumes (
  volume_id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  display_path TEXT NOT NULL,
  status TEXT NOT NULL,
  bytes_available INTEGER,
  policy_json TEXT NOT NULL DEFAULT '{}',
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
