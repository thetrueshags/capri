"""Transient pointer reactions do not replace the underlying software activity."""
class PointerReactions:
    def __init__(self):
        self.active=None
        self._entered=None
        self._left=None
        self._poke_until=0.
        self.last_poke=None

    def poke(self,now,duration=2.2):
        self.active='poke'
        self._poke_until=now+duration
        self.last_poke=now

    def update(self,over_sprite,now,enabled=True):
        if not enabled:
            was_active=self.active is not None
            self.active=None
            self._entered=self._left=None
            return 'base' if was_active else None
        if self.active=='poke':
            if now<self._poke_until:return None
            self.active=None
            self._entered=now-.2 if over_sprite else None
            if not over_sprite:return 'base'
        if over_sprite:
            self._left=None
            if self._entered is None:self._entered=now
            if self.active is None and now-self._entered>=.18:
                self.active='hover'
                return 'hover'
        else:
            self._entered=None
            if self.active=='hover':
                if self._left is None:self._left=now
                if now-self._left>=.4:
                    self.active=None
                    self._left=None
                    return 'base'
        return None
