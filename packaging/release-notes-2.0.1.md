RuneFetch 2.0.1 ships the web interface and in-app updater in a standalone Windows installer.

- Fix Spotify downloads in the packaged app by dispatching spotdl explicitly and including its dictionary data.
- Shut down the UI and browser bridge servers cleanly.
- Reject incomplete update downloads before an installer can be launched.
- Include the browser extension in the installation folder.
- Add a repeatable local installer build and packaged executable checks.

Download **RuneFetch-Setup-2.0.1.exe** and run it to install or upgrade RuneFetch. The adjacent `.sha256` file contains its SHA-256 checksum.

Validation: all runtime dependencies and project modules import; update comparison, download integrity, WebSocket authentication/origin checks, JavaScript syntax, packaged Spotify CLI startup, packaged application startup, and a real YouTube video download passed on Windows.

The installer is unsigned. A full Spotify track download and upgrades from every historical installer have not been tested. Older builds without the in-app updater require a manual installation.
