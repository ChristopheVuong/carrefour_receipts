"""Structured logging setup (structlog).

A single :func:`configure_logging` call wires structlog so the ELT loader and the
API extractor emit structured events (key/value pairs) instead of bare ``print``s —
the observability item from the roadmap's risk-mitigation section. Output is
human-readable console by default, or line-delimited JSON when ``LOG_JSON=true``
(or ``LOG_FORMAT=json``), which is what you want when shipping logs to a collector.

Idempotent: calling it more than once just re-applies the configuration. The log
level comes from ``LOG_LEVEL`` (default ``INFO``).
"""

from __future__ import annotations

import logging
import os

import structlog


def _json_requested() -> bool:
    return (
        os.getenv("LOG_JSON", "").lower() == "true" or os.getenv("LOG_FORMAT", "").lower() == "json"
    )


def configure_logging(level: str | None = None, *, json_logs: bool | None = None) -> None:
    """Configure structlog once. ``level`` overrides ``LOG_LEVEL`` (default INFO)."""
    resolved = level if level else os.getenv("LOG_LEVEL", "INFO")
    log_level = resolved.upper()
    use_json = _json_requested() if json_logs is None else json_logs

    logging.basicConfig(format="%(message)s", level=log_level)

    renderer = structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger (configures logging on first use if needed)."""
    if not structlog.is_configured():
        configure_logging()
    return structlog.get_logger(name)
