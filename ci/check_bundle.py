"""Check that the frozen Spotify worker dispatches to spotdl, not the GUI."""
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent.parent
result = subprocess.run(
    [str(root / 'dist/RuneFetch/RuneFetch.exe'), '--spotdl-worker', '--help'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
)
output = result.stdout.decode('utf-8', errors='replace')
if result.returncode != 0 or 'spotdl' not in output.lower() or '--output' not in output:
    print(output)
    sys.exit('FAIL: frozen Spotify worker did not provide spotdl help')
print('OK: frozen Spotify worker starts and exposes spotdl CLI options')
