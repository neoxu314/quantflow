"""Block and record outbound traffic from offline Python tests and their children."""

import os
import socket
from functools import wraps
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urljoin, urlsplit

NETWORK_LOG = "QUANTFLOW_TEST_NETWORK_LOG"


def _check(host):
    filename = os.environ.get(NETWORK_LOG)
    if not filename or host in (None, "", "localhost"):
        return
    if isinstance(host, bytes):
        host = host.decode("ascii")
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None and (getattr(address, "ipv4_mapped", None) or address).is_loopback:
        return

    # Log only the host, never the URL, query, credentials or request body.
    with Path(filename).open("a", encoding="utf-8") as log:
        log.write(f"{host!r}\n")
    raise OSError(f"Offline QuantFlow test blocked a request to {host!r}")


def install(setattr):
    """Guard Python sockets and the native curl transport used by Yahoo providers."""
    from curl_cffi.requests import AsyncSession, Session

    def socket_address(method):
        @wraps(method)
        def guarded(self, *args, **kwargs):
            address = args[-1] if args else kwargs.get("address")
            if isinstance(address, tuple):
                _check(address[0])
            return method(self, *args, **kwargs)

        return guarded

    original_getaddrinfo = socket.getaddrinfo

    @wraps(original_getaddrinfo)
    def getaddrinfo(host, *args, **kwargs):
        _check(host)
        return original_getaddrinfo(host, *args, **kwargs)

    def curl_request(original):
        @wraps(original)
        def guarded(self, method, url, *args, **kwargs):
            _check(urlsplit(urljoin(self.base_url or "", url)).hostname)
            return original(self, method, url, *args, **kwargs)

        return guarded

    for name in ("connect", "connect_ex", "sendto"):
        setattr(socket.socket, name, socket_address(getattr(socket.socket, name)))
    setattr(socket, "getaddrinfo", getaddrinfo)
    for session in (Session, AsyncSession):
        setattr(session, "request", curl_request(session.request))
