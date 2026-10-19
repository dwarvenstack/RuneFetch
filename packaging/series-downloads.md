# Series downloads and optional ZIP output

Implemented locally on `release/2.0.3`. Not published.

Paste a HiAnime series page or episode link and choose Download. RuneFetch reads the actual episode entries, displays their count, and waits for a choice in the quality dialog. Episode links default to the linked episode; series pages default to all episodes.

The **Create a ZIP archive** checkbox is unchecked by default and enabled for all-episode downloads. Unchecked saves numbered episode files in a series folder. Checked creates a ZIP64 archive after all episodes succeed and keeps the episode files. Videos are already compressed; ZIP mainly groups them and needs additional disk space.

A series runs as one queue job with episode progress. Pause/cancel events are shared with individual transfers and ZIP creation. The series manifest, ZIP choice and job folder identifier are persisted for paused restart recovery. Errors preserve completed episodes, and failed/cancelled archives leave no completed-looking ZIP. History redownloads receive a fresh job folder.

Validation:

- Both supplied Fullmetal Alchemist: Brotherhood URLs resolve to 64 unique episode entries (1–64); the episode URL preserves episode 1.
- The linked episode resolves to 1080p through the actual format backend.
- Native application UI checked for both links: series count, current/all defaults, unchecked ZIP default, ticking ZIP, storage note, and current-episode quality lookup.
- 105 Python tests passed, including 23 series tests for discovery, batch validation, API queueing, ordered files, ZIP CRC/content, archive failures, cancellation and persisted settings.
- 13 frontend tests passed, including six series-flow tests.
- Module import checks passed. Local builds and GitHub build/release workflows now run frontend tests too.
- A complete live 64-episode series transfer was not run. Batch/archive tests use small deterministic files; earlier live single-episode downloads were validated separately.

Existing limitations: subtitled servers, no dubbed track selector or embedded-subtitle option; source-host changes may still require adapter updates. ZIP does not switch streams mid-download and a failed episode stops the group without creating an incomplete archive.
