import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            payload: dict[str, Any] = dict(record.msg)
        else:
            payload = {"message": record.getMessage()}

        payload["level"] = record.levelname.lower()
        payload["logger"] = record.name

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str, app_env: str) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    if app_env.lower() in {"production", "staging"}:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root.addHandler(handler)

    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = True
