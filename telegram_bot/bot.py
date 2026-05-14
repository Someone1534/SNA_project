import io
import logging
import os
from typing import Any

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


BACKUP_SERVICE_URL = os.getenv("BACKUP_SERVICE_URL", "http://backup-service:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
MAX_LIST_ITEMS = int(os.getenv("MAX_LIST_ITEMS", "10"))


class BackupApiError(RuntimeError):
    pass


class BackupApi:
    def __init__(self, base_url: str, timeout_seconds: float):
        self.base_url = base_url
        self.timeout = httpx.Timeout(timeout_seconds)

    async def health(self) -> dict[str, Any]:
        return await self._request_json("GET", "/health")

    async def create_backup(self) -> dict[str, Any]:
        return await self._request_json("POST", "/backups")

    async def list_backups(self) -> dict[str, Any]:
        return await self._request_json("GET", "/backups")

    async def restore_backup(self, filename: str) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            f"/restore/{filename}",
            params={"confirm": "true"},
            timeout=httpx.Timeout(300),
        )

    async def download_backup(self, filename: str) -> bytes:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/backups/{filename}/download")
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as exc:
                raise BackupApiError(self._extract_error(exc.response)) from exc
            except httpx.RequestError as exc:
                raise BackupApiError(f"Backup service is unavailable: {exc}") from exc

    async def _request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=kwargs.pop("timeout", self.timeout)) as client:
            try:
                response = await client.request(method, f"{self.base_url}{path}", **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise BackupApiError(self._extract_error(exc.response)) from exc
            except httpx.RequestError as exc:
                raise BackupApiError(f"Backup service is unavailable: {exc}") from exc

    def _extract_error(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or f"HTTP {response.status_code}"

        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        return str(payload)


backup_api = BackupApi(BACKUP_SERVICE_URL, REQUEST_TIMEOUT_SECONDS)


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


def format_backup(backup: dict[str, Any]) -> str:
    filename = backup.get("filename", "unknown.dump")
    size = format_size(int(backup.get("size_bytes", 0)))
    created_at = str(backup.get("created_at", "unknown"))
    return f"{filename} | {size} | {created_at}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await update.effective_message.reply_text(
        "Backup Manager Bot\n\n"
        "/status - check backup service and database \n"
        "/backup - create a new database dump\n"
        "/list - show available dumps\n"
        "/download <filename> - download a dump file\n"
        "/restore <filename> confirm - restore database from dump"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    try:
        payload = await backup_api.health()
    except BackupApiError as exc:
        await update.effective_message.reply_text(f"Service error: {exc}")
        return

    await update.effective_message.reply_text(
        f"Status: {payload.get('status', 'unknown')}\n"
        f"Database: {payload.get('database', 'unknown')}"
    )


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    message = await update.effective_message.reply_text("Creating backup...")

    try:
        payload = await backup_api.create_backup()
    except BackupApiError as exc:
        await message.edit_text(f"Backup failed: {exc}")
        return

    backup_file = payload.get("backup", {})
    await message.edit_text(f"Backup created:\n{format_backup(backup_file)}")


async def list_backups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    try:
        payload = await backup_api.list_backups()
    except BackupApiError as exc:
        await update.effective_message.reply_text(f"Could not load backups: {exc}")
        return

    backups = payload.get("backups", [])
    if not backups:
        await update.effective_message.reply_text("No backups found yet.")
        return

    lines = [format_backup(item) for item in backups[:MAX_LIST_ITEMS]]
    await update.effective_message.reply_text("Available backups:\n" + "\n".join(lines))


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /download <filename>")
        return

    filename = context.args[0]
    message = await update.effective_message.reply_text("Downloading backup...")

    try:
        content = await backup_api.download_backup(filename)
    except BackupApiError as exc:
        await message.edit_text(f"Download failed: {exc}")
        return

    file_obj = io.BytesIO(content)
    file_obj.name = filename
    await message.delete()
    await update.effective_message.reply_document(document=file_obj, filename=filename)


async def restore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2 or context.args[1].lower() != "confirm":
        await update.effective_message.reply_text(
            "Restore replaces the current database schema.\n"
            "Usage: /restore <filename> confirm"
        )
        return

    filename = context.args[0]
    message = await update.effective_message.reply_text("Restoring database...")

    try:
        payload = await backup_api.restore_backup(filename)
    except BackupApiError as exc:
        await message.edit_text(f"Restore failed: {exc}")
        return

    backup_file = payload.get("backup", {})
    await message.edit_text(f"Database restored from:\n{format_backup(backup_file)}")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("backup", backup))
    application.add_handler(CommandHandler("list", list_backups))
    application.add_handler(CommandHandler("download", download))
    application.add_handler(CommandHandler("restore", restore))

    logger.info("Starting Telegram bot")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
