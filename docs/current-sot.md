# DataManager Current Source of Truth

This document replaces the previous implementation plans, sprint outputs, QA reports, and prompt packs.

## Core Contract

- DataManager performs checksum-based replication through the local runtime only.
- A job can contain n source paths and n replica paths.
- Replica paths are equal peers named as path entries such as `path1`, `path2`, and `path3`.
- There is no `main` destination and no `backup` destination in the job contract.
- Each supported file found under every source path is copied to every replica path.
- Every copy is checksum-verified against the source file.
- File-level persistence records one source file result plus one replica result per target path.

## Runtime API Shape

Job creation payload:

```json
{
  "project_name": "Project",
  "source_path_ids": ["src-card-a", "src-card-b"],
  "replica_path_ids": ["dest-path1", "dest-path2", "dest-path3"],
  "operator_origin": "remote_web",
  "policy": {}
}
```

## Storage Shape

- `jobs.source_path_ids_json`: JSON array of runtime-approved source path IDs.
- `jobs.replica_path_ids_json`: JSON array of runtime-approved replica path IDs.
- `job_files.source_path_id`: source path that produced the file.
- `job_files.source_relpath`: file path relative to that source path.
- `job_file_replicas`: one row per file and replica path, including destination relative path, checksum, status, and error fields.

## Output Layout

Replicated footage is written under each replica root:

```text
<replica-root>/<project-name>/01_Footage/R#<n>/<source-path-id>/<source-relative-file>
```

Reports and manifests are generated from persisted replication data under the first selected replica path for API download.

## Verification

Run:

```sh
.venv/bin/python -m pytest
```
