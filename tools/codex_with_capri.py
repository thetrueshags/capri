"""Start Codex with metadata-only hooks in its session config layer."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from capri.companion.events import HOOK_STATES

def overrides(profile=None):
    profile = Path(profile or os.environ.get('CAPRI_DATA_DIR') or ROOT / 'data').resolve()
    # Codex invokes hook commands through the platform shell; quote each literal path.
    command = subprocess.list2cmdline([str(Path(sys.executable)),
        str(ROOT / 'capri/companion/bridge.py'), '--profile', str(profile)])
    record = '{hooks=[{type="command",command=' + json.dumps(command) + ',timeout=2}]}'
    result = []
    for event in HOOK_STATES:
        result.extend(['-c', f'hooks.{event}=[{record}]'])
    return result

def main():
    binary = shutil.which('codex.exe') if os.name == 'nt' else shutil.which('codex')
    if not binary:
        raise SystemExit('Codex is not installed or is not on PATH.')
    return subprocess.call([binary, *overrides(), *sys.argv[1:]])

if __name__ == '__main__':
    raise SystemExit(main())
