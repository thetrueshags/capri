import json
import os
import uuid
import copy
from pathlib import Path
from .persona import ensure_persona

PROJECT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    'model': 'qwen2.5:3b', 'ollama_url': 'http://127.0.0.1:11434',
    'roaming': True, 'quiet': False, 'size': 180, 'sleep_after': 300,
    'loop_min_seconds': 15, 'loop_max_seconds': 35,
    'transition_seconds': 0.85,
    'personality_behavior': True, 'mouse_awareness': True, 'mouse_reactions': True,
    'media_avoidance': True, 'automatic_media_watch': True, 'protected_media_screens': [],
}

def profile_path(value=None):
    return Path(value or os.environ.get('CAPRI_DATA_DIR') or PROJECT / 'data').resolve()

class Config:
    def __init__(self, directory=None):
        self.directory = profile_path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        ensure_persona(self.directory)
        self.path = self.directory / 'config.json'
        self.values = copy.deepcopy(DEFAULTS)
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            # Existing roaming intervals now govern selection of another loop.
            raw.setdefault('loop_min_seconds', raw.get('roam_min_seconds', 15))
            raw.setdefault('loop_max_seconds', raw.get('roam_max_seconds', 35))
            self.values.update({k: v for k, v in raw.items() if k in DEFAULTS})
        self.values['size'] = max(100, min(300, int(self.values['size'])))
        self.values['transition_seconds'] = max(.3, min(2, float(self.values['transition_seconds'])))
        self.save()

    def __getitem__(self, key):
        return self.values[key]

    def set(self, key, value):
        if key not in DEFAULTS:
            raise KeyError(key)
        self.values[key] = value
        self.save()

    def save(self):
        staged = self.path.with_name('config.' + uuid.uuid4().hex + '.tmp')
        staged.write_text(json.dumps(self.values, indent=2) + '\n', encoding='utf-8')
        staged.replace(self.path)

