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
