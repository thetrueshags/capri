"""Small atomic-file event bridge: software metadata only, no transcript capture."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
import uuid

STATES = {'idle', 'working', 'waiting', 'ready', 'blocked'}
HOOK_STATES = {'SessionStart': 'idle', 'UserPromptSubmit': 'working',
               'PreToolUse': 'working', 'PostToolUse': 'working',
               'PermissionRequest': 'waiting', 'Stop': 'ready',
               'Interrupt': 'idle', 'SessionEnd': 'idle'}

def clean_event(raw):
    if not isinstance(raw, dict) or raw.get('state') not in STATES:
        raise ValueError('Invalid activity event')
    stamp = float(raw.get('time', time.time()))
    if not math.isfinite(stamp) or abs(stamp) > 1e11:
        raise ValueError('Invalid event time')
    source = raw.get('source', 'software')
    if not isinstance(source, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}', source):
        raise ValueError('Invalid source name')
    return {'id': str(uuid.UUID(str(raw.get('id', uuid.uuid4())))),
            'source': source, 'session': str(raw.get('session', 'default'))[:100],
            'state': raw['state'], 'project': str(raw.get('project', ''))[:80],
            'time': stamp, 'timestamp': datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec='seconds')}

def hook_event(payload):
    event = payload.get('hook_event_name')
    if event not in HOOK_STATES:
        return None
    # Deliberately discard prompts, tool arguments, command output and transcript paths.
    state = HOOK_STATES[event]
    response = payload.get('tool_response')
    if event == 'PostToolUse' and isinstance(response, dict):
        exit_code = response.get('exit_code')
        if response.get('is_error') is True or response.get('isError') is True or (isinstance(exit_code, int) and exit_code != 0):
            state = 'blocked'
    return clean_event({'source': 'codex', 'session': payload.get('session_id', 'default'),
                        'state': state,
                        'project': Path(str(payload.get('cwd', '')).replace('\\', '/')).name})

def emit(directory, item):
    directory = Path(directory) / 'inbox'
    directory.mkdir(parents=True, exist_ok=True)
    item = clean_event(item)
    temp = directory / (item['id'] + '.tmp')
    temp.write_text(json.dumps(item), encoding='utf-8')
    temp.replace(directory / (item['id'] + '.json'))
    return item

class Activity:
    def __init__(self):
        self.sessions = {}

    def apply(self, event, now=None):
        now = time.time() if now is None else now
        if now - event['time'] > 120 or event['time'] - now > 30:
            return
        key = event['source'], event['session']
        previous = self.sessions.get(key)
        if previous and event['time'] < previous['time']:
            return
        self.sessions[key] = event

    def current(self, now=None):
        now = time.time() if now is None else now
        leases = {'idle': 0, 'working': 600, 'waiting': 1800, 'ready': 18, 'blocked': 45}
        self.sessions = {k: v for k, v in self.sessions.items() if now - v['time'] < leases[v['state']]}
        rank = {'waiting': 4, 'blocked': 3, 'working': 2, 'ready': 1}
        return max(self.sessions.values(), key=lambda v: (rank[v['state']], v['time']), default=None)

def drain(directory, memory, activity, limit=100):
    inbox = Path(directory) / 'inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in sorted(inbox.glob('*.json'))[:limit]:
        # Only consume owned regular files with emitter UUID names; skip links entirely.
        if p.is_symlink() or not p.is_file():
            continue
        try:
            uuid.UUID(p.stem)
            if p.stat().st_size > 4096:
                raise ValueError('Event too large')
            item = clean_event(json.loads(p.read_text(encoding='utf-8')))
            if memory.event(item):
                activity.apply(item)
                count += 1
        except (ValueError, TypeError, OSError, OverflowError):
            # Preserve rejected input for inspection instead of retrying every timer tick.
            p.rename(p.with_suffix('.rejected'))
            continue
        p.unlink()
    return count

