import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time
import uuid
from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon
from .config import Config, PROJECT
from .events import Activity, drain
from .memory import Memory,timestamp
from .panel import CompanionPanel
from .window import DesktopPet
from .behavior import BehaviorEngine
from .personality import PersonalitySync
from .media import MediaGuard,MediaController

class Companion:
    def __init__(self, app, config):
        self.app, self.config = app, config
        self.memory = Memory(config.directory)
        self.activity = Activity()
        self.pet = DesktopPet(config)
        self.panel = CompanionPanel(config, self.memory, self.pet)
        self.personality = PersonalitySync(config)
        self.behavior = BehaviorEngine(self.personality.profile)
        self.pet.behavior = self.behavior
        self.personality.ready.connect(self.apply_personality)
        self.personality.status.connect(self.panel.body_status.setText)
        self.media_guard=MediaGuard()
        self.pet.media_guard=self.media_guard
        self.media=MediaController(config,self.media_guard,self.pet.areas,lambda:self.behavior.profile)
        self.media.changed.connect(self.pet.enforce_media)
        self.media.watch_started.connect(self.start_watch)
        self.media.watch_stopped.connect(self.stop_watch)
        self.media.status.connect(self.panel.media_status.setText)
        self.pet.stop_watching_requested.connect(self.media.stop)
        self.pet.chat_requested.connect(lambda: self.panel.open_tab(0))
        self.pet.memory_requested.connect(lambda: self.panel.open_tab(1))
        self.pet.quit_requested.connect(app.quit)
        self.last_state = 'idle'
        self.local_busy = False
        self.panel.busy_changed.connect(self.set_busy)
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(500)
        icon = QIcon(str(PROJECT / 'assets/companion/library-v1/idle-default-00.png'))
        app.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, app)
        menu = QMenu()
        menu.addAction('Chat with Capri', lambda: self.panel.open_tab(0))
        menu.addAction('Memory and activity', lambda: self.panel.open_tab(1))
        menu.addAction('Bring Capri to this screen', self.bring_back)
        menu.addAction('Quit Capri', app.quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip('Capri · local desktop companion')
        self.tray.activated.connect(lambda reason: self.panel.open_tab(0) if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self.pet.show()
        self.pet.say('Hey. I’m here.', 4)

    def bring_back(self):
        from PySide6.QtGui import QCursor
        screen = self.app.screenAt(QCursor.pos()) or self.app.primaryScreen()
        index = self.app.screens().index(screen)
        self.pet.teleport_to_screen(index)
        self.pet.enforce_media()

    def set_busy(self, busy):
        self.local_busy = busy
        if not busy:
            self.pet._last_interaction = time.monotonic()
        self.poll()

    def apply_personality(self, profile):
        self.behavior.profile = profile
        self.pet._switch_next = time.monotonic() + self.pet.switch_delay()

    def start_watch(self,screen,decision):
        try:
            self.pet.start_watching(screen)
        except ValueError:
            self.media.stop('Media screen unavailable')
            return
        app=self.media_guard.detected.get(screen,{}).get('app','media')
        self.memory.event({'id':str(uuid.uuid4()),'source':'capri-media','session':'watch',
                          'state':'watching','project':app[:80],'timestamp':timestamp()})

    def stop_watch(self,reason):
        self.pet.stop_watching()
        self.memory.event({'id':str(uuid.uuid4()),'source':'capri-media','session':'watch',
                          'state':'stopped-watching','project':'media','timestamp':timestamp()})

    def poll(self):
        try:
            count = drain(self.config.directory, self.memory, self.activity)
            active = self.activity.current()
            self.personality.refresh(chat_busy=self.local_busy)
            self.media.tick(chat_busy=self.local_busy or self.panel.isVisible())
            state = 'working' if self.local_busy else active['state'] if active else 'idle'
            last_input = max(self.pet._last_interaction, self.pet.cursor.last_motion or 0)
            sleep_after = (self.behavior.sleep_delay(self.config['sleep_after'])
                           if self.config['personality_behavior'] else self.config['sleep_after'])
            if state == 'idle' and not self.panel.isVisible() and time.monotonic() - last_input > sleep_after:
                state = 'sleeping'
            if self.panel.isVisible():
                self.pet._pause_until = time.monotonic() + 2
                if state == 'sleeping':
                    state = 'idle'
            if state != self.last_state:
                source = active['source'] if active and not self.local_busy else 'Capri'
                messages = {'working': f'{source} is working.', 'waiting': f'{source} needs your input.',
                            'ready': f'{source} is ready.', 'blocked': f'{source} hit a snag.'}
                if state in messages:
                    self.pet.say(messages[state])
                self.pet.set_state(state)
                self.last_state = state
                self.tray.setToolTip('Capri · ' + state)
            if count and self.panel.isVisible():
                self.panel.refresh_activity()
            cursor = self.pet.cursor.observation(time.monotonic())
            if cursor.get('enabled'):
                self.panel.mouse_status.setText(f"Mouse: screen {cursor['screen_index']} · {cursor['screen']} · {cursor['direction_from_capri']} of Capri")
            else:
                self.panel.mouse_status.setText('Mouse awareness is off or no fresh pointer sample is available.')
        except Exception:
            logging.exception('Activity poll failed')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile')
    parser.add_argument('--smoke', type=float, help='Exit automatically after this many seconds')
    parser.add_argument('--evidence', help='Write window screenshots and screen geometry here')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('Capri Desktop')
    app.setQuitOnLastWindowClosed(False)
    config = Config(args.profile)
    lock = QLockFile(str(config.directory / 'desktop.lock'))
    if not lock.tryLock(0):
        if not args.smoke:
            QMessageBox.information(None, 'Capri', 'Capri is already running for this profile. Use her tray icon to open chat.')
        return 1
    handler = RotatingFileHandler(config.directory / 'runtime.log', maxBytes=1024 * 1024, backupCount=2, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s', force=True)
    # Keep error logs free of prompts and model replies; those belong in the inspectable journal.
    def exception(kind, value, tb):
        logging.error('Unhandled exception', exc_info=(kind, value, tb))
    sys.excepthook = exception
    companion = Companion(app, config)
    if args.evidence:
        directory = Path(args.evidence)
        directory.mkdir(parents=True, exist_ok=True)
        def evidence():
            screens = [{'name': s.name(), 'x': s.availableGeometry().x(), 'y': s.availableGeometry().y(),
                        'width': s.availableGeometry().width(), 'height': s.availableGeometry().height(),
                        'scale': s.devicePixelRatio()} for s in app.screens()]
            (directory / 'screens.json').write_text(json.dumps(screens, indent=2))
            companion.pet.grab().save(str(directory / 'pet.png'))
            companion.panel.open_tab(1)
            companion.panel.grab().save(str(directory / 'memory-panel.png'))
            companion.panel.hide()
        QTimer.singleShot(1300, evidence)
    if args.smoke:
        QTimer.singleShot(round(args.smoke * 1000), app.quit)
    result = app.exec()
    companion.tray.hide()
    lock.unlock()
    return result

if __name__ == '__main__':
    raise SystemExit(main())
