"""Entry point of the stream service: ``python -m app.stream.run``."""

import signal

from app.core.logging import configure_logging
from app.stream.service import StreamService


def main() -> None:
    configure_logging()
    service = StreamService()
    signal.signal(signal.SIGTERM, lambda *_: service.stop())
    service.run()


if __name__ == "__main__":
    main()
