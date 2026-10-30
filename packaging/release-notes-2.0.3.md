RuneFetch 2.0.3 adds HiAnime episode downloads with embedded English subtitles, episode selection, and optional ZIP archives.

- Choose one episode or all available episodes.
- Download Japanese audio with selectable English subtitles and a separate subtitle file.
- Bundle episodes and subtitles into a ZIP while keeping the original files.
- Restore paused series downloads after restarting.
- Try alternative supported video servers when extraction fails.
- Package the application's HTML, CSS, and JavaScript inside the build.
- Fix the version check getting stuck on "Checking…" and the startup version label.
- Fix Python runtime detection in installer CI checks.

Validation: 116 Python tests, 19 frontend tests, and 25 integration checks passed. Installed-build checks covered downloads, subtitles, episode selection, ZIP integrity, updater detection, and reinstall.

Testing limits:
- A full 64-episode download was not tested.
- The complete in-app "Update & restart" process was not tested.

Download **RuneFetch-Setup-2.0.3.exe** to install or upgrade. The portable ZIP is available for users who prefer no installer. The installer SHA-256 checksum, dependency lock, and validation report accompany this release.
