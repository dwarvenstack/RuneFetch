# HiAnime download experiment

Local branch: `feature/hianime-download`, based on `release/2.0.3`.
The release branch preserves embedded frontend packaging and the updater UI repair.
No remote push, published release, or installed application replacement is part of this experiment.

## Scope

- Resolves exact `hianime.at/watch/...?...ep=...` episode URLs through the page's public server-list endpoint.
- Supports the ZokoAnime subtitled server and its publicly delivered player configuration.
- Uses existing yt-dlp HLS transfer, progress, pause/cancel hooks, format selectors and postprocessing.
- Validates explicit page, server, embed and stream URLs against existing public-network rules.
- Keeps other sites on their existing yt-dlp path.
- Allows HLS video resolutions in the quality picker when the manifest omits codec metadata.

Dub selection, subtitle embedding, full-season playlists, other mirrors and alternate video hosts are not implemented. Site and host changes may break this experimental adapter. No CAPTCHA solving or DRM bypass is implemented.

## Validation

- 73 Python regression tests passed, including 9 extractor tests.
- 7 JavaScript regression tests passed, including HLS quality selection and updater UI.
- Mob Psycho 100 episode 2: 1920x1080 H.264 + AAC; duration 1452.116900 seconds; completed MP4 385081857 bytes; full ffmpeg decode passed.
- Black Clover Season 2 episode 3: 1920x1080 H.264 + AAC; duration 1429.461333 seconds; completed MP4 914473202 bytes. Full ffmpeg decode passed.
- Both real URLs resolved through RuneFetch's format-picker backend; Black Clover offers 360p, 720p and 1080p.
- Live downloads ran through `downloaders.router.run_download` in isolated project build folders; no personal queue or settings changed.

To repeat a live download and full decode (requires ffmpeg and ffprobe):

```powershell
.venv\Scripts\python.exe ci/smoke_hianime.py 'https://hianime.at/watch/black-clover-season-2-1-10492?ep=150266'
```

After review, merge this branch into `release/2.0.3`; to discard it, switch back to `release/2.0.3` and remove the experiment branch. The embedded frontend and updater fixes remain on the release branch either way.

## Automatic discovery follow-up

- Accepts pasted `hianime.<single suffix>` episode URLs after checking recognizable page markers; API requests use the pasted domain. A brand rename or multi-part suffix is not automatically inferred.
- Discovers up to six unique HTTPS subtitled player links from the live server list instead of requiring a fixed player hostname.
- Recognizes the existing public player configuration across hostnames, detects explicit HLS source URLs, and tries upstream yt-dlp extractors for other players.
- Tries the next server when lookup or manifest extraction fails, retaining subtitled playback rather than silently switching to a dub.
- Validates each explicit player/stream address before fetching. Limits player discovery and sets a ten-second socket timeout for this adapter.
- Does not discover a new site address when the old domain disappears, execute unknown player scripts, bypass CAPTCHA/DRM, or switch servers mid-download. An unsupported player still needs an adapter update.
- Added nine automated tests for host/domain changes, failed-server fallback, unsupported pages, public-network restrictions, standard HLS, generic extraction and bounded discovery.
- Live Black Clover format lookup still returns 360p, 720p and 1080p.
