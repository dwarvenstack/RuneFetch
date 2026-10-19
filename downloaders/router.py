"""
Router — dispatches a DownloadItem to the correct backend engine.
"""

import logging

from core.detector import (
    TYPE_YOUTUBE, TYPE_SPOTIFY, TYPE_YTDLP, TYPE_DIRECT, TYPE_DRM, TYPE_UNKNOWN
)
from utils import net_guard

_log = logging.getLogger(__name__)


def _guard_url(item):
    """
    Block raw-fetch downloads aimed at private/local addresses (SSRF).

    Skipped when a proxy is configured — DNS resolution and routing then
    happen at the proxy, so a local resolution check is both ineffective and
    potentially wrong. Fails CLOSED: an unresolvable host raises.
    """
    if getattr(item, "proxy", ""):
        return
    try:
        net_guard.assert_url_allowed(item.url)
    except net_guard.BlockedAddressError as exc:
        _log.warning("Router blocked URL (id=%s): %s", getattr(item, "id", "?"), exc)
        raise Exception(
            "⛔ Download blocked: URL resolves to a private/local address.\n"
            "RuneFetch does not fetch content from internal network hosts."
        ) from exc


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

    # SSRF guard for every fetch path. The detector's generic fallback labels
    # arbitrary/unknown hosts as TYPE_YTDLP, so the yt-dlp branch must be
    # guarded too — otherwise http://<internal-host>/… would slip straight to
    # yt-dlp. Skipped automatically when a proxy is configured.
    _guard_url(item)

    if t == 'hianime_series':
        from downloaders.hianime_series import download_series
        download_series(item, progress_cb)

    elif t in (TYPE_YOUTUBE, TYPE_YTDLP):
        from downloaders.ytdlp_downloader import download_ytdlp
        try:
            download_ytdlp(item, progress_cb)
        except Exception as exc:
            msg = str(exc)
            # Twitter/X image tweets produce "No video could be found".
            # yt-dlp cannot download Twitter images via status URLs;
            # the user needs to append /photo/1 to get the direct image URL.
            if "No video could be found" in msg and (
                "twitter.com" in item.url or "x.com" in item.url
            ):
                raise Exception(
                    "This tweet has no downloadable video.\n"
                    "If it contains an image, open the tweet, click the image, "
                    "and copy the URL ending in /photo/1 — then paste that instead."
                ) from exc
            raise

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
        _log.info("Unknown type %r — trying yt-dlp then direct  id=%s", t, item.id)
        try:
            from downloaders.ytdlp_downloader import download_ytdlp
            download_ytdlp(item, progress_cb)
        except Exception as exc:
            _log.warning("yt-dlp fallback failed (%s), retrying with direct  id=%s", exc, item.id)
            from downloaders.direct_downloader import download_direct
            download_direct(item, progress_cb)
