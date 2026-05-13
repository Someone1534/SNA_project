from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from app.backup_manager import BackupError, BackupManager
from app.config import get_settings


app = FastAPI(title="Backup Manager Service", version="0.1.0")
manager = BackupManager(get_settings())


@app.get("/health")
def health() -> dict[str, str]:
    try:
        manager.check_database()
    except BackupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"status": "ok", "database": "ready"}


@app.post("/backups")
def create_backup() -> dict[str, object]:
    try:
        backup = manager.create_backup()
    except BackupError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"message": "Backup created", "backup": backup}


@app.get("/backups")
def list_backups() -> dict[str, list[object]]:
    return {"backups": manager.list_backups()}


@app.get("/backups/{filename}/download")
def download_backup(filename: str) -> FileResponse:
    try:
        backup_path = manager.resolve_backup_path(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        path=backup_path,
        filename=backup_path.name,
        media_type="application/octet-stream",
    )


@app.post("/restore/{filename}")
def restore_backup(
    filename: str,
    confirm: bool = Query(default=False, description="Must be true to run restore"),
) -> dict[str, object]:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Restore is destructive. Repeat request with confirm=true.",
        )

    try:
        backup = manager.restore_backup(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BackupError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"message": "Database restored", "backup": backup}
