#!/usr/bin/env python3
"""
Download a real video through RuneFetch's own router.

The only check that proves the whole chain works end to end: detector →
router → yt-dlp → ffmpeg merge → file on disk. Everything else in CI verifies
that code loads; this verifies it downloads.

It talks to real YouTube, so it is wired as continue-on-error in the workflow:
a failure here means yt-dlp or the site drifted, which is worth a notification
but must not block an unrelated pull request.
"""

import pathlib
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# A short, stable Creative Commons clip — small enough to keep CI fast.
TEST_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"   # Big Buck Bunny


class FakeItem:
    """Mimics the DownloadItem attributes the downloaders actually read."""

    def __init__(self, url: str, save_path: str, dl_type: str):
        self.id               = "ci-smoke"
        self.url              = url
        self.dl_type          = dl_type
        # Always end in a bare "best" fallback. A strict selector like
        # "best[height<=360]" hard-fails on videos that publish no combined
        # stream at that height, which is a property of the test video rather
        # than a real regression.
        self.fmt              = ("bestvideo[height<=360]+bestaudio/"
                                 "best[height<=360]/best")
        self.quality          = "360p"
        self.title            = ""
        self.size             = ""
        self.save_path        = save_path
        self.proxy            = ""
        self.throttle_kbps    = 0
        self.fragment_threads = 2
        self.is_playlist      = False
        self.error            = ""
        self.pause_event      = threading.Event()
        self.cancel_event     = threading.Event()
        self._log_lines       = []
        self.pause_event.set()   # not paused


def main() -> int:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from core.detector import detect
    from downloaders.router import run_download

    out_dir = tempfile.mkdtemp(prefix="runefetch_dl_")
    detection = detect(TEST_URL)
    print(f"Detected: {detection.get('label')} (type={detection.get('type')})")

    item = FakeItem(TEST_URL, out_dir, detection["type"])

    last = {"pct": 0.0}

    def progress_cb(pct, speed, eta, size, speed_bps=0.0):
        # Log every ~25% so CI output stays readable.
        if pct - last["pct"] >= 25:
            last["pct"] = pct
            print(f"  {pct:5.1f}%  {speed}  {eta}")

    try:
        run_download(item, progress_cb)
    except Exception as exc:
        print(f"\nFAIL  download raised {type(exc).__name__}: {exc}")
        return 1

    files = [f for f in pathlib.Path(out_dir).iterdir() if f.is_file()]
    if not files:
        print("\nFAIL  download reported success but produced no file")
        return 1

    for f in files:
        size_mb = f.stat().st_size / 1_048_576
        print(f"\nOK    {f.name}  ({size_mb:.2f} MB)")
        if f.stat().st_size == 0:
            print("FAIL  file is empty")
            return 1

    print("\nEnd-to-end download OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
