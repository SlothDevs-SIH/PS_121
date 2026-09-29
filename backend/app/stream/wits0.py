"""WITS level 0 (ASCII) reader: records framed by ``&&`` and ``!!`` lines, one item per line
as a 4-digit code (record + item number) followed by its value, e.g. ``0108 2214.3``.

Parsing is separate from the socket so it can be tested byte by byte; a partial record at
the end of a chunk is kept for the next one.
"""

import socket
from collections.abc import Iterator

START, END = "&&", "!!"
MAX_BUFFER = 1 << 16  # a sender that never closes a record does not grow memory unbounded


def parse(buffer: str) -> tuple[list[dict[str, str]], str]:
    """Complete records in `buffer` and the unparsed remainder."""
    records: list[dict[str, str]] = []
    while True:
        s = buffer.find(START)
        if s < 0:  # no record start: keep only a possible first "&" of the next one
            return records, "&" if buffer.endswith("&") else ""
        e = buffer.find(END, s + 2)
        if e < 0:
            rest = buffer[s:]
            return records, rest[-MAX_BUFFER:]
        rec: dict[str, str] = {}
        for line in buffer[s + 2 : e].splitlines():
            line = line.strip()
            if len(line) > 4 and line[:4].isdigit():
                rec[line[:4]] = line[4:].strip()
        if rec:
            records.append(rec)
        buffer = buffer[e + 2 :]


def read(host: str, port: int, timeout_s: float = 30.0) -> Iterator[dict[str, str]]:
    """Records from a WITS0 TCP feed until the sender closes the connection."""
    with socket.create_connection((host, port), timeout=timeout_s) as sock:
        rest = ""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                return
            records, rest = parse(rest + chunk.decode("ascii", errors="replace"))
            yield from records
