import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    backup_dir: Path
    command_timeout_seconds: int


def get_settings() -> Settings:
    return Settings(
        postgres_host=os.getenv("POSTGRES_HOST", "postgres"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_db=os.getenv("POSTGRES_DB", "backup_manager"),
        postgres_user=os.getenv("POSTGRES_USER", "backup_user"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "backup_password"),
        backup_dir=Path(os.getenv("BACKUP_DIR", "/backups")),
        command_timeout_seconds=int(os.getenv("COMMAND_TIMEOUT_SECONDS", "300")),
    )
