"""Run a Python script with the network disabled (P1.17): a tripwire that proves `predict.py` is offline.

    python scripts/no_network.py scripts/run_eval.py --set dev --mode offline
    python scripts/no_network.py scripts/smoke_api.py --serve --offline

Before the script starts, every way to open a connection or resolve a name raises `OSError("network
disabled by scripts/no_network.py")`: `socket.socket.connect`/`connect_ex`, `socket.create_connection`,
`socket.getaddrinfo` and `socket.gethostbyname(_ex)`. Loopback is allowed (`127.*`, `::1`, `localhost`):
the API smoke talks to its own server on 127.0.0.1, and local socketpairs used by asyncio and ONNX Runtime
threads keep working. The script runs as `__main__` with its own argv; its exit code is passed through.
Stdlib only.
"""

from __future__ import annotations

import runpy
import socket
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

MESSAGE = "network disabled by scripts/no_network.py"


def _blocked(*_args: object, **_kwargs: object) -> NoReturn:
    raise OSError(MESSAGE)


def is_loopback(host: object) -> bool:
    """True for 127.*, ::1 and localhost (and None, the wildcard used for local binds)."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if not isinstance(host, str):
        return False
    h = host.strip().lower().strip("[]")
    return h == "localhost" or h == "::1" or h.startswith("127.")


def _host_of(address: object) -> object:
    if isinstance(address, tuple) and address:
        return address[0]
    return address


def disable_network() -> None:
    """Patch the socket module so no connection or DNS lookup can leave this machine."""
    orig_create = socket.create_connection
    orig_getaddrinfo = socket.getaddrinfo
    orig_byname = socket.gethostbyname
    orig_byname_ex = socket.gethostbyname_ex
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex

    def create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        if not is_loopback(_host_of(address)):
            _blocked()
        return orig_create(address, *args, **kwargs)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if not is_loopback(host):
            _blocked()
        return orig_getaddrinfo(host, *args, **kwargs)

    def gethostbyname(host: Any) -> str:
        if not is_loopback(host):
            _blocked()
        return orig_byname(host)

    def gethostbyname_ex(host: Any) -> Any:
        if not is_loopback(host):
            _blocked()
        return orig_byname_ex(host)

    def connect(self: socket.socket, address: Any) -> None:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not is_loopback(_host_of(address)):
            _blocked()
        orig_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not is_loopback(_host_of(address)):
            _blocked()
        return orig_connect_ex(self, address)

    patches: dict[str, Callable[..., Any]] = {
        "create_connection": create_connection,
        "getaddrinfo": getaddrinfo,
        "gethostbyname": gethostbyname,
        "gethostbyname_ex": gethostbyname_ex,
    }
    for name, fn in patches.items():
        setattr(socket, name, fn)
    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python scripts/no_network.py <script.py> [args...]", file=sys.stderr)
        return 2
    script = Path(args[0])
    if not script.is_file():
        print(f"error: {script} not found", file=sys.stderr)
        return 2
    disable_network()
    sys.argv = [str(script), *args[1:]]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
