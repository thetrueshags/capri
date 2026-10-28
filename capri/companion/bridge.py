"""Hook adapter. Never emits hook decisions and always fails open for Codex."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from capri.companion.config import profile_path
from capri.companion.events import emit, hook_event

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile')
    parser.add_argument('--state', choices=['idle', 'working', 'waiting', 'ready', 'blocked'])
    parser.add_argument('--source', default='software')
    parser.add_argument('--session', default='default')
    parser.add_argument('--project', default='')
    args = parser.parse_args()
    try:
        if args.state:
            item = {'state': args.state, 'source': args.source, 'session': args.session, 'project': args.project}
        else:
            raw = sys.stdin.buffer.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                return
            item = hook_event(json.loads(raw))
        if item:
            emit(profile_path(args.profile), item)
    except Exception:
        # A companion must not interrupt or inject text into the agent it observes.
        return

if __name__ == '__main__':
    main()

