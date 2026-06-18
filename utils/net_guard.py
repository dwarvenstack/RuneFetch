"""
Network egress guard — SSRF protection for RuneFetch's raw HTTP downloaders.

Why this exists
───────────────
The direct/segmented downloaders fetch arbitrary user-supplied URLs with
`requests`. Without guarding, a URL (or an HTTP redirect) can point the
downloader at loopback / LAN / link-local addresses (e.g. cloud metadata at
169.254.169.254, internal admin panels, etc.) — a classic SSRF.

This module provides:
  • assert_url_allowed(url)  — resolve the host and raise if *any* resolved
    address is private/loopback/link-local/reserved. Fails CLOSED: a DNS
    failure raises rather than silently allowing the request.
  • safe_request(...)        — a drop-in for requests.head/get that follows
    redirects MANUALLY, re-validating every hop, so a public URL cannot
    bounce to an internal address.

Proxy note
──────────
When the user configures a proxy, DNS resolution and the actual connection
happen *at the proxy*, not locally. Resolving the host on this machine would
be both ineffective (the proxy decides the real route) and wrong (a public
host might resolve to a private IP locally yet route fine through the proxy).
So IP validation is skipped when a proxy is in use; redirect-following is
still performed.
"""

import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

import requests

_log = logging.getLogger(__name__)

# Explicit private ranges (kept for clarity; the is_* checks below also cover
# most of these, but being explicit guards against surprises across versions).
_PRIVATE_NETS = [
    ipaddress.ip_network(n) for n in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "169.254.0.0/16", "100.64.0.0/10",
        "::1/128", "fc00::/7", "fe80::/10", "::ffff:0:0/96",
    )
]

SAFE_MAX_REDIRECTS = 10

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
_LOCAL_ORIGIN_SCHEMES = (
    "file:", "app:", "ms-appx", "chrome-extension:", "moz-extension:",
    "safari-web-extension:",
)


class BlockedAddressError(Exception):
    """Raised when a URL resolves to a disallowed (private/local) address."""


def ws_origin_allowed(origin: str | None) -> bool:
    """
    Ingress guard for the loopback WebSocket servers (UI 8770, bridge 8765).

    Browsers do NOT apply same-origin policy to WebSocket connections, so any
    web page the user visits could open ws://127.0.0.1:<port>. The shared token
    is the primary defense; this is defense-in-depth that rejects connections
    carrying a real website Origin while allowing the legitimate clients:

      • pywebview web UI         → Origin "null" / "file://" / missing
      • browser extension worker → Origin "chrome-extension://…"
      • local dev / loopback     → Origin "http://localhost" / "127.0.0.1"

    A malicious page is identified by its own document Origin (e.g.
    "http://evil.com") — note that DNS-rebinding does NOT change the Origin
    header, so loopback-host origins remain safe to allow.
    """
    if not origin or origin.lower() == "null":
        return True
    low = origin.lower()
    if low.startswith(_LOCAL_ORIGIN_SCHEMES):
        return True
    try:
        host = (urlparse(origin).hostname or "").lower()
    except Exception:
        return False
    return host in _LOOPBACK_HOSTS


def get_ws_origin(websocket) -> str | None:
    """
    Extract the Origin header from a websockets connection across library
    versions (>=13 exposes ``websocket.request.headers``; older versions use
    ``websocket.request_headers``).
    """
    req = getattr(websocket, "request", None)
    headers = getattr(req, "headers", None)
    if headers is None:
        headers = getattr(websocket, "request_headers", None)
    if headers is None:
        return None
    try:
        return headers.get("Origin")
    except Exception:
        return None


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable → block (fail closed)
    # IPv4-mapped IPv6 (::ffff:a.b.c.d) → unwrap and re-check the v4 address
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped
    if (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
        return True
    return any(addr in net for net in _PRIVATE_NETS)


def _resolve_all(host: str) -> set[str]:
    """Return every IP (v4 + v6) the host resolves to. Raises on failure."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return {info[4][0] for info in infos}


def assert_url_allowed(url: str) -> set[str]:
    """
    Validate that *url*'s host resolves only to public addresses.

    Returns the set of resolved IPs on success.
    Raises BlockedAddressError if the host is missing, unresolvable, or
    resolves to any private/local address (fail closed).
    """
    host = (urlparse(url).hostname or "").strip()
    if not host:
        raise BlockedAddressError("URL has no host")

    # Host may already be a literal IP
    try:
        ipaddress.ip_address(host)
        ips = {host}
    except ValueError:
        try:
            ips = _resolve_all(host)
        except Exception as exc:
            # Fail CLOSED — do not let an unresolved host through.
            raise BlockedAddressError(f"DNS resolution failed for {host!r}: {exc}") from exc

    if not ips:
        raise BlockedAddressError(f"{host!r} resolved to no addresses")

    for ip in ips:
        if _is_blocked_ip(ip):
            raise BlockedAddressError(
                f"blocked private/local address {ip} (host {host!r})"
            )
    return ips


def safe_request(method: str, url: str, *, proxies=None, allow_redirects: bool = True,
                 session: requests.Session | None = None, **kwargs) -> requests.Response:
    """
    Like requests.request(method, url, ...) but SSRF-safe.

    Redirects are followed manually (up to SAFE_MAX_REDIRECTS); each hop is
    re-validated with assert_url_allowed. When *proxies* is set, IP validation
    is skipped (the proxy resolves and routes) but redirects are still bounded.

    Returns the final Response. For streaming responses pass stream=True in
    kwargs as usual; the returned Response is the (non-redirect) final one.
    """
    own_session = session is None
    sess = session or requests.Session()
    current = url
    try:
        for _ in range(SAFE_MAX_REDIRECTS + 1):
            if not proxies:
                assert_url_allowed(current)
            resp = sess.request(method, current, proxies=proxies,
                                allow_redirects=False, **kwargs)
            if allow_redirects and resp.is_redirect:
                location = resp.headers.get("Location")
                if not location:
                    return resp
                nxt = urljoin(current, location)
                resp.close()
                current = nxt
                continue
            return resp
        raise BlockedAddressError("too many redirects")
    finally:
        # Only close the session if we created it AND we're not streaming a
        # body the caller still needs. Streaming callers pass their own use;
        # closing the Session does not close an already-returned Response's
        # underlying connection until the Response is consumed/closed.
        if own_session:
            # Defer close to caller for streamed responses by not closing here
            # when stream=True; otherwise safe to close.
            if not kwargs.get("stream"):
                sess.close()
