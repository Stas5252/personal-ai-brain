"""Production Telegram entrypoint with enqueue-only document ingestion."""
from __future__ import annotations

from pathlib import Path

from src.brain.channels import telegram_production_runner as production

_original_reply = production.ProductionGuidedBot.reply


def _queued_reply(self, message):
    document = message.get("document") or message.get("video")
    if document:
        from src.brain.knowledge.registration import IngestionRegistrar
        filename = document.get("file_name") or ("video.mp4" if message.get("video") else "document.bin")
        local = self.delivery_api.download(document, Path(filename).suffix.lower())
        try:
            result = IngestionRegistrar().register_file(
                local, original_filename=filename, title=filename,
                metadata={"channel": "telegram", "telegram_owner_id": str(self.owner)},
            )
        finally:
            local.unlink(missing_ok=True)
        return (
            f"✅ Материал принят: *{filename}*\n"
            f"Статус: {result.job.status.value}; задача: `{result.job.job_id}`.\n"
            "Индексация выполняется последовательно в фоне."
        )
    return _original_reply(self, message)


production.ProductionGuidedBot.reply = _queued_reply


if __name__ == "__main__":
    production.run_polling()
