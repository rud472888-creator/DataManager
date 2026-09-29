"""Synthetic recorded evidence for PDF pressure checks; never a live offload."""

from app.persistence.models import JobFile, JobFileReplica

PROJECT = "DEBUG DATA | 무선 카메라 제어 및 현장 스크립트 기록 통합 검증 보고서"
DESTINATIONS = ("replica-01", "replica-02")


def pressure_files(count: int = 8) -> list[JobFile]:
    result = []
    for index in range(count):
        digest = f"{index + 1:064x}"
        replicas = [
            JobFileReplica(
                file_id=f"file-{index:03}",
                path_id=destination,
                dest_relpath=f"001_Footage/촬영본/A-CAM_take-2026_05_18_FINAL_v003_{index:03}.mov",
                checksum=digest,
                status="verified",
            )
            for destination in DESTINATIONS
        ]
        if index == 1:
            replicas[1] = JobFileReplica(
                file_id=f"file-{index:03}",
                path_id=DESTINATIONS[1],
                dest_relpath="001_Footage/재확인 <take> & camera.mov",
                checksum="f" * 64,
                status="failed",
                error_code="CHECKSUM_MISMATCH",
                error_message="촬영감독과 스크립터가 동시에 확인해야 하는 상태값이 다릅니다.",
            )
        if index == 2:
            replicas = replicas[:1]
        result.append(
            JobFile(
                file_id=f"file-{index:03}",
                job_id="DEBUG-JOB-2026-09-11",
                source_path_id="source-A-촬영카드",
                source_relpath=f"촬영본/카메라 A/A-CAM_take-2026_05_18_FINAL_v003_{index:03}.mov",
                size_bytes=0 if index == 3 else 47200000000 + index,
                status="warn" if index in (1, 2) else "verified",
                checksum_source=digest,
                replica_results=tuple(replicas),
            )
        )
    return result
