import re
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings


BACKUP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+\.dump$")


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupFile:
    filename: str
    size_bytes: int
    created_at: str


class BackupManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.backup_dir.mkdir(parents=True, exist_ok=True)

    def check_database(self) -> None:
        self._run(
            [
                "pg_isready",
                "-h",
                self.settings.postgres_host,
                "-p",
                str(self.settings.postgres_port),
                "-U",
                self.settings.postgres_user,
                "-d",
                self.settings.postgres_db,
            ]
        )

    def create_backup(self) -> BackupFile:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.dump"
        output_path = self.settings.backup_dir / filename

        self._run(
            [
                "pg_dump",
                "-h",
                self.settings.postgres_host,
                "-p",
                str(self.settings.postgres_port),
                "-U",
                self.settings.postgres_user,
                "-d",
                self.settings.postgres_db,
                "-Fc",
                "--no-owner",
                "--no-privileges",
                "-f",
                str(output_path),
            ]
        )

        return self._file_info(output_path)

    def list_backups(self) -> list[BackupFile]:
        files = sorted(
            self.settings.backup_dir.glob("*.dump"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return [self._file_info(path) for path in files]

    def resolve_backup_path(self, filename: str) -> Path:
        if not BACKUP_NAME_PATTERN.fullmatch(filename):
            raise FileNotFoundError("Invalid backup filename")

        backup_dir = self.settings.backup_dir.resolve()
        backup_path = (backup_dir / filename).resolve()

        if backup_dir not in backup_path.parents:
            raise FileNotFoundError("Invalid backup filename")
        if not backup_path.exists() or not backup_path.is_file():
            raise FileNotFoundError("Backup file not found")

        return backup_path

    def restore_backup(self, filename: str) -> BackupFile:
        backup_path = self.resolve_backup_path(filename)

        self._run(
            [
                "psql",
                "-h",
                self.settings.postgres_host,
                "-p",
                str(self.settings.postgres_port),
                "-U",
                self.settings.postgres_user,
                "-d",
                self.settings.postgres_db,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
            ]
        )

        self._run(
            [
                "pg_restore",
                "-h",
                self.settings.postgres_host,
                "-p",
                str(self.settings.postgres_port),
                "-U",
                self.settings.postgres_user,
                "-d",
                self.settings.postgres_db,
                "--no-owner",
                "--no-privileges",
                str(backup_path),
            ]
        )

        return self._file_info(backup_path)

    def _file_info(self, path: Path) -> BackupFile:
        stat = path.stat()
        created_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        return BackupFile(filename=path.name, size_bytes=stat.st_size, created_at=created_at)

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PGPASSWORD"] = self.settings.postgres_password
        try:
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.settings.command_timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise BackupError(f"Command timed out: {' '.join(command)}") from exc
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise BackupError(message) from exc
