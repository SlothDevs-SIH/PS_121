"""WITS0 framing and the TCP reader against a local socket."""

import socket
import threading

from app.stream import mapping as mp
from app.stream import wits0

FRAME = "&&\r\n0108 2214.3\r\n0114 812.5\r\n0131 2100\r\n!!\r\n"


def test_parse_frames_and_keeps_partial_tail() -> None:
    recs, rest = wits0.parse(FRAME + "&&\r\n0108 22")
    assert recs == [{"0108": "2214.3", "0114": "812.5", "0131": "2100"}]
    assert rest == "&&\r\n0108 22"
    recs2, rest2 = wits0.parse(rest + "15.0\r\n!!\r\n")
    assert recs2 == [{"0108": "2215.0"}] and rest2 == ""
    assert wits0.parse("noise without frames")[0] == []


def test_records_map_to_canonical_channels() -> None:
    vals, quality = mp.to_canonical(wits0.parse(FRAME)[0][0], mp.WITS0_DEFAULTS)
    assert vals["bit_depth_m"] == 2214.3 and vals["hookload_kn"] == 812.5
    assert vals["flow_in_lpm"] == 2100.0
    assert quality["torque_knm"] == "missing"


def test_reader_over_tcp_split_across_chunks() -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve() -> None:
        conn, _ = srv.accept()
        with conn:
            data = (FRAME * 3).encode()
            for i in range(0, len(data), 7):  # arbitrary chunk boundaries
                conn.sendall(data[i : i + 7])

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    try:
        recs = list(wits0.read("127.0.0.1", port, timeout_s=5))
    finally:
        srv.close()
    assert len(recs) == 3 and all(r["0108"] == "2214.3" for r in recs)
