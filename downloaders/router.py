"""
Router — dispatches a DownloadItem to the correct backend engine.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from core.detector import (
    TYPE_YOUTUBE, TYPE_SPOTIFY, TYPE_YTDLP, TYPE_DIRECT, TYPE_DRM, TYPE_UNKNOWN
)

_log = logging.getLogger(__name__)

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        addr = ipaddress.ip_address(socket.gethostbyname(host))
        return any(addr in net for net in _PRIVATE_NETS)
    except Exception:
        return False


def run_download(item, progress_cb):
    """Called in a worker thread. Raises on unrecoverable failure."""
    t = item.dl_type
    _log.info("Router  id=%s  type=%s  url=%s", item.id, t, item.url[:80])

    if t == TYPE_DRM:
        raise Exception(
            "⛔ DRM-protected content cannot be downloaded by RuneFetch.\n"
            "Netflix, Prime Video, Hotstar, and Disney+ use Widevine encryption.\n"
            "Use the official app's built-in offline/download feature instead."
        )

    if t in (TYPE_YOUTUBE, TYPE_YTDLP):
        from downloaders.ytdlp_downloader import download_ytdlp
        download_ytdlp(item, progress_cb)

    elif t == TYPE_SPOTIFY:
        from downloaders.spotdl_downloader import download_spotify
        download_spotify(item, progress_cb)

    elif t == TYPE_DIRECT:
        from downloaders.segmented_downloader import download as download_segmented
        ok = download_segmented(item, progress_cb)
        if not ok:
            err = getattr(item, "error", "Download failed")
            _log.error("Segmented download failed  id=%s  err=%s", item.id, err)
            raise Exception(err)

    else:
        if _is_private_url(item.url):
            raise Exception(
                "⛔ Download blocked: URL resolves to a private/local address.\n"
                "RuneFetch does not fetch content from internal network hosts."
            )
        _log.info("Unknown type %r — trying yt-dlp then direct  id=%s", t, item.id)
        try:
            from downloaders.ytdlp_downloader import download_ytdlp
            download_ytdlp(item, progress_cb)
        except Exception as exc:
            _log.warning("yt-dlp fallback failed (%s), retrying with direct  id=%s", exc, item.id)
            from downloaders.direct_downloader import download_direct
            download_direct(item, progress_cb)
