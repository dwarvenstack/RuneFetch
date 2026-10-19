RuneFetch 2.0.2 refreshes the desktop interface and fixes download reliability.

- A quieter charcoal/paper interface with brass accents, clearer page hierarchy, consistent line icons, responsive layouts, keyboard focus indicators and reduced-motion support. Fonts work offline.
- The DwarvenStack footer link opens the publisher page in the default browser.
- Queue jobs start once, and changing concurrency respects downloads already running.
- Direct downloads resume matching partial files, restart safely when a server ignores resume, and reject incomplete transfers. Compressed HTTP responses are handled correctly.
- Segmented downloads honor pause/cancel, verify each byte range, fall back when ranges are ignored, and use a single stream when a speed limit is set.
- Windows reserved filenames are sanitized.
- History honors the recording preference, distinguishes video from audio, and retains download types for re-downloads.
- The UI uses the configured local WebSocket port.

Download **RuneFetch-Setup-2.0.2.exe** to install or upgrade. A portable ZIP, installer SHA-256 checksum, dependency lock and validation report accompany this release.

Validation details and known limits are in `validation-2.0.2.md`. The installer is unsigned. Older installations without an updater require a manual install.
