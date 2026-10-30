# RuneFetch 2.0.3 local candidate validation

Validated 30 October 2026 before publication. The owner subsequently approved pushing and publishing this candidate with the release notes in `release-notes-2.0.3.md`.

## Results

| Area | Result |
| --- | --- |
| Automated Python suite | 116 tests passed |
| Frontend JavaScript suite | 19 tests passed |
| Source application integration | 25 checks passed, including authentication, invalid input, settings, queue controls, history, updater, and live transfers |
| Build | PyInstaller and Inno Setup completed successfully; packaged startup and Spotify worker CLI smoke checks passed |
| Installer | All 1,426 payload files matched their hashes; reinstall replaced a stale executable; personal installation registration was preserved |
| Embedded interface | Packaged application has no loose `_internal/webui` directory |
| Installed application | Started with an isolated profile, authenticated, saved settings, changed speed controls, restored a paused 64-episode ZIP job after restart |
| Live anime | Fullmetal Alchemist: Brotherhood episode 1 downloaded at 1080p with audio, embedded English `mov_text` subtitles and a retained English VTT sidecar; full FFmpeg decode passed |
| Live audio | Requested YouTube Short downloaded as MP3, audio-only probe and full decode passed |
| Series ZIP | Packaged downloader resumed a cached, validated episode and created a ZIP containing the video and English sidecar; CRC passed; originals retained |
| Native interface | Startup version displays 2.0.3; repeated manual checks finish with up-to-date status; publisher link opens the correct GitHub profile |
| Available-update interface | Isolated installed copy temporarily identified as 2.0.1 and correctly displayed the published 2.0.2 update and release notes; Later dismissed it without installation; metadata restored to 2.0.3 afterward |
| Episode interface | Lists all 64 episodes plus All episodes, defaults to linked episode, fetches episode 2's 1080p quality, enables ZIP for all episodes and toggles the ZIP explanation |
| Extension | JavaScript syntax, manifest resource checks and backend bridge smoke checks passed |

## Fixes found during validation

- Startup version retrieval now waits for the native bridge, avoiding a persistent blank version label. Two regression checks cover this initialization and an unavailable bridge.
- Installer CI smoke validation now resolves the setup-python runtime before falling back to the local virtual environment. The previous published workflow failed because it assumed a local `.venv` existed on the hosted runner. The corrected path passed locally with the setup-python environment variable simulated; hosted CI has not been rerun.

## Artifact

- Installer: `dist_installer/RuneFetch-Setup-2.0.3.exe`
- Size: 42,834,381 bytes
- SHA-256: `032823eed2376ec332c0815c142bbcb5348a17b1aa53916f7cd6f468e83df6e5`
- Matching checksum file: `dist_installer/RuneFetch-Setup-2.0.3.exe.sha256`

## Coverage limits

No real 64-episode transfer was performed: enumeration and queue persistence used all 64, while ZIP completion used one cached real episode, supplemented by automated batch tests. No production in-app upgrade was installed. Browser extension installation, full Spotify downloads, proxy operation, and first-run FFmpeg acquisition were not exercised end to end. External sites can change; these results describe the tested URLs and current responses. Embedded frontend packaging does not prevent determined reverse engineering.

Detailed local evidence is retained under ignored `build/`: `validation-2.0.3-build-final.log`, `validation-2.0.3-installer-final.log`, `application-qa/report.json`, and `validation-2.0.3/packaged-results.json`. Test media and profiles are isolated there; the personal installation was not used for the media tests.
