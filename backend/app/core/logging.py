import logging

import structlog


def configure_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog once at app startup.

    json_logs=False gives a pretty console renderer for local dev.
    """
    logging.basicConfig(level=log_level, format="%(message)s")
    renderer = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
