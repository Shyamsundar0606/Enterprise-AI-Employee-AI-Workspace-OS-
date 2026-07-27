import logging
import sys


def configure_logging(log_level: str) -> None:
    """Configure predictable process-wide console logging."""
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
