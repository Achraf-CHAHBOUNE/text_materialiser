"""One line per event, the same shape from every service, on stdout -- where Docker
collects it (`docker compose logs backend`), ready for any log tool.

    {"ts": "2026-10-16T16:46:47Z", "level": "info", "service": "api", "msg": "request",
     "rid": "3f2a9c1e0b7d", "method": "GET", "path": "/api/browse/rulings", "status": 200, "ms": 42}

LOG_FORMAT=text gives plain lines instead, for reading in a terminal. Nothing personal is
logged on purpose: a request is logged by its route's pattern (/api/crm/users/{email}),
never its address, query string or body -- a search can hold a name.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class _Json(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": dt.datetime.fromtimestamp(record.created, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "level": record.levelname.lower(), "service": self.service, "msg": record.getMessage()}
        out.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD})
        if record.exc_info:
            out["error"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def setup(service: str) -> logging.Logger:
    """Configure the root logger once for this process and return the service's logger."""
    root = logging.getLogger()
    if not getattr(root, "_tok_configured", False):
        handler = logging.StreamHandler(sys.stdout)
        if os.getenv("LOG_FORMAT", "json") == "text":
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        else:
            handler.setFormatter(_Json(service))
        root.handlers = [handler]
        root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
        root._tok_configured = True
    return logging.getLogger(service)
