PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    retry_of_job_id TEXT NULL,
    project_name TEXT NOT NULL,
    source_volume_id TEXT NOT NULL,
    dest_main_id TEXT NOT NULL,
    dest_backup_id TEXT NULL,
    state TEXT NOT NULL,
    current_step TEXT NOT NULL,
    resume_step TEXT NULL,
    operator_origin TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    warning_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    current_file_relpath TEXT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT NULL,
    ended_at TEXT NULL,
    last_event_id INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_single_active
ON jobs ((1))
WHERE state IN (
    'SCANNING',
    'PREPARING',
    'COPYING',
    'PAUSING',
    'VERIFYING',
    'PARSING',
    'CAPTURING',
    'REPORTING'
);

CREATE TABLE IF NOT EXISTS job_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NULL,
    event_type TEXT NOT NULL,
    level TEXT NOT NULL,
    from_state TEXT NULL,
    to_state TEXT NULL,
    command_name TEXT NULL,
    command_status TEXT NULL,
    origin TEXT NOT NULL,
    reason_code TEXT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_id_event_id
ON job_events (job_id, event_id);

CREATE TABLE IF NOT EXISTS job_files (
    job_file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    parser_name TEXT NULL,
    source_checksum_sha256 TEXT NULL,
    main_checksum_sha256 TEXT NULL,
    backup_checksum_sha256 TEXT NULL,
    copy_main_state TEXT NOT NULL DEFAULT 'PENDING',
    copy_backup_state TEXT NOT NULL DEFAULT 'PENDING',
    verify_main_state TEXT NOT NULL DEFAULT 'PENDING',
    verify_backup_state TEXT NOT NULL DEFAULT 'PENDING',
    parse_state TEXT NOT NULL DEFAULT 'PENDING',
    capture_state TEXT NOT NULL DEFAULT 'PENDING',
    warning_code TEXT NULL,
    error_code TEXT NULL,
    metadata_json TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_job_files_job_id_relative_path
ON job_files (job_id, relative_path);

CREATE TABLE IF NOT EXISTS clips (
    clip_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    job_file_id INTEGER NOT NULL,
    format_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    clip_name TEXT NULL,
    reel_name TEXT NULL,
    camera_id TEXT NULL,
    codec TEXT NULL,
    resolution_width INTEGER NULL,
    resolution_height INTEGER NULL,
    fps REAL NULL,
    duration_frames INTEGER NULL,
    timecode_start TEXT NULL,
    shot_date TEXT NULL,
    iso_value INTEGER NULL,
    white_balance_kelvin INTEGER NULL,
    lens_json TEXT NULL,
    raw_metadata_json TEXT NOT NULL,
    parsed_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
    FOREIGN KEY(job_file_id) REFERENCES job_files(job_file_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    report_type TEXT NOT NULL,
    status TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    size_bytes INTEGER NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS system_volumes (
    volume_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    mount_path TEXT NOT NULL,
    volume_role TEXT NOT NULL,
    is_removable INTEGER NOT NULL,
    filesystem_type TEXT NULL,
    capacity_bytes INTEGER NULL,
    free_bytes INTEGER NULL,
    serial_hint TEXT NULL,
    approval_state TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
