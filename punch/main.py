#!/usr/bin/env python3
"""Punch: Lightweight self-hosted AI assistant."""

import asyncio
import logging
import signal
import sys

from punch.config import PunchConfig

logger = logging.getLogger("punch")


async def main():
    config = PunchConfig()
    config.ensure_dirs()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("Punch starting up...")

    # Components will be added in subsequent tasks
    logger.info("Punch ready.")

    # Keep running until interrupted
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()
    logger.info("Punch shutting down.")


if __name__ == "__main__":
    asyncio.run(main())
