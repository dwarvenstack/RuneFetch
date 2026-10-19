# RuneFetch 2.0.2 validation

Validated on Windows with Python 3.13.14. This report describes the release
candidate, not a guarantee that every supported third-party site works.

| Layer | Result |
| --- | --- |
| Regression suite | 61 tests passed, including additional table-driven cases |
| Isolated application audit | 25 dispatcher/engine integration checks passed |
| Dependency/module imports | All required dependencies and project modules passed |
| JavaScript | App, WebSocket client and browser extension syntax checks passed |
| WebSockets | Real UI/bridge round trips, authentication and origin rejection passed |
| Source live video | Requested YouTube Short downloaded; video/audio streams verified |
| Source live audio | Requested Short extracted to MP3; audio-only stream and full decode passed |
| Packaged executable | Starts with isolated profile, authenticates and displays Connected on a separate port |
| Packaged Spotify worker | Frozen CLI starts and exposes spotdl options |
| Packaged audio | Real Short download and MP3 conversion completed; full decode passed |
| Installer extraction | All 1,432 payload files matched source hashes |
| Installer reinstall | A deliberately stale executable was replaced correctly |
| Installation isolation | Existing personal application registration was unchanged |
| Installed executable | Starts and completes a real Short download; full video/audio decode passed |
| Artifact integrity | Installer SHA-256 accompanies the release; uploaded digest verified after publication |

The test URL was `https://www.youtube.com/shorts/HysJ32YP0x0`.
The test outputs were about 96.5 seconds long. Video tests verified video and audio;
MP3 tests verified audio-only output. Test profiles, downloads and history used
isolated locations. Existing user queue/history/settings were preserved.

## Coverage

Tests cover concurrency changes, duplicate worker prevention, pause/resume,
cancellation, byte-for-byte parallel HTTP ranges, ignored range fallback, direct
download resume, compressed responses, incomplete bodies, HTTP errors, file
collisions, Windows device filenames, directory traversal, Unicode filenames,
DNS failures, mixed public/private answers, private redirect rejection, redirect
limits, WebSocket origins, corrupt preferences and queue files, token persistence,
history preferences and output labels, media selector construction, update
comparison/throttling, partial update cleanup and installer handoff.

The actual installer supports `/TESTINSTALL=1` for isolated verification without
shortcuts, uninstall registration or automatic launch. Normal installations use
the existing application identity and normal update/relaunch behavior. Tests
also pass `/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS` to avoid interfering with
any running personal installation.

## Remaining limits

- The installer is unsigned.
- Full Spotify track downloads, external proxy routing, arbitrary playlists,
  every supported site, and extension installation in each browser were not
  live-tested. The Spotify worker, selectors, bridge and proxy routing branch
  have narrower automated coverage.
- The speed limit is tested for new direct transfers. Changing it during a
  transfer was not validated; a paused worker continues to occupy its queue slot.
- First-run ffmpeg download on a machine without ffmpeg, a complete interactive
  uninstall, and an in-place upgrade from every historical installer were not
  performed. Reinstall replacement and installed-app startup/download were tested
  in an isolated directory.
- The full automatic updater handoff was tested with mocked process creation;
  the installer itself and installed app were exercised separately.
