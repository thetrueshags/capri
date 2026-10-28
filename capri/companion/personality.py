"""Reinterpret edited persona text locally; persist the last valid bounded profile."""
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
from PySide6.QtCore import QObject, Signal
from .behavior import BehaviorProfile
from .model import LocalModel
from .persona import load_persona

def persona_key(text, model):
    return hashlib.sha256((model + '\0' + text).encode('utf-8')).hexdigest()

class PersonalitySync(QObject):
    ready = Signal(object)
    status = Signal(str)
    _finished = Signal(str, object)
    _failed = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.profile = BehaviorProfile()
        self.key = None
        self.path = config.directory / 'behavior-profile.json'
        self.busy = False
        self._next_check = 0.
        self._next_attempt = 0.
        self._finished.connect(self.finish)
        self._failed.connect(self.failed)
        if self.path.exists() and load_persona(config).strip():
            try:
                saved = json.loads(self.path.read_text(encoding='utf-8'))
                self.profile = BehaviorProfile.from_dict(saved['traits'])
                self.key = saved['persona_sha256']
            except (ValueError, KeyError, OSError):
                self.key = None

    def refresh(self, chat_busy=False):
        now = time.monotonic()
        if not self.config['personality_behavior']:
            self.status.emit('Personality behavior is off')
            return
        if now < self._next_check or self.busy:
            return
        self._next_check = now + 2
        try:
            text = load_persona(self.config)
            if not text.strip():
                key=persona_key('',self.config['model'])
                if self.key!=key or self.profile!=BehaviorProfile():
                    self.profile=BehaviorProfile()
                    self.key=key
                    self.ready.emit(self.profile)
                self.status.emit('Persona template is blank; using neutral desktop behavior')
                return
            key = persona_key(text, self.config['model'])
        except (OSError, UnicodeError, ValueError):
            self.status.emit('Cannot read persona.txt; retaining the last behavior profile')
            return
        if key == self.key:
            self.status.emit('Personality is synchronized with persona.txt')
            return
        if chat_busy:
            self.status.emit('Desktop personality will update after the current reply finishes')
            return
        if now < self._next_attempt:
            return
        self.busy = True
        self.status.emit('Interpreting personality for desktop behavior locally…')
        def work():
            try:
                result = LocalModel(self.config).personality_traits(text)
                self._finished.emit(key, result)
            except Exception:
                self._failed.emit('Personality interpretation unavailable; retaining the last behavior profile')
        threading.Thread(target=work, name='capri-personality', daemon=True).start()

    def finish(self, key, raw):
        self.busy = False
        try:
            profile = BehaviorProfile.from_dict(raw)
            # Do not apply an inference for a prompt/model that changed while it ran.
            text = load_persona(self.config)
            if not text.strip() or key != persona_key(text, self.config['model']):
                self._next_check = 0
                return
            record = {'version': 1, 'persona_sha256': key, 'traits': profile.as_dict()}
            staged = self.path.with_name('behavior-profile.' + uuid.uuid4().hex + '.tmp')
            staged.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
            staged.replace(self.path)
            self.profile, self.key = profile, key
            self.ready.emit(profile)
            self.status.emit('Personality is synchronized with persona.txt')
        except (ValueError, OSError):
            self.failed('Invalid personality interpretation; retaining the last behavior profile')

    def failed(self, message):
        self.busy = False
        self._next_attempt = time.monotonic() + 60
        self.status.emit(message)
