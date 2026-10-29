# Anime subtitle support — local v2.0.3

HiAnime video downloads now retrieve English captions, retain their original VTT/SRT/ASS file and embed a selectable subtitle track in the MP4. Video is not burned in or re-encoded by the subtitle embedding step. Audio-only downloads and unrelated sites retain their existing behavior.

Player metadata may incorrectly mark every language as `en`; the adapter uses language labels to distinguish Arabic, English and other tracks. Signs/songs-only English tracks are not accepted as full English dialogue. Explicit subtitle URLs pass the existing public-network check.

When English tracks are absent during extraction, another discovered server is tried. If no suitable server provides them, the download fails instead of silently returning a video without subtitles. Network failures after extraction are reported through the existing downloader error path; this does not implement mid-download host switching.

Series downloads retain matching English sidecars and add them to the optional ZIP beside each numbered MP4. The checkbox still defaults to unchecked.

Validation:

- Live Fullmetal Alchemist: Brotherhood episode 1 resolved the English track correctly; the downloaded VTT contains 252 subtitle cues.
- Tiny local HTTP fixture passed through the actual downloader and ffmpeg postprocessing. ffprobe confirmed a `mov_text` subtitle stream marked `eng`; extracting that stream reproduced the expected text, and the original VTT remained beside the video.
- Missing-English fallback, mislabeled languages, private subtitle URLs, subtitle HTTP errors, audio-only behavior and ZIP subtitle inclusion are tested.
- 116 Python and 17 frontend tests passed. No additional full episode or full series was downloaded for this change.

User scope decisions:

- RareAnimes investigation is abandoned. No RareAnimes extractor is included.
- Next investigation: webpage asset discovery using the Riot challenge page, preserving original media formats/extensions where the original files are exposed. PNG/SVG/JPEG/WebP assets should not be rasterized or converted by default. Discovering a higher-resolution original on every arbitrary site cannot be guaranteed.
- No push or publication until the user requests the release. The published v2.0.2 update-check UI bug still needs final packaged verification of its local source fix before publishing v2.0.3.
