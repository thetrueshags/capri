import threading
import time
from PySide6.QtCore import QObject, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget)
from .events import emit
from .model import LocalModel

STYLE = '''
QWidget { background:#121019; color:#e0e7e1; font-family:'Segoe UI'; font-size:12px; }
QLabel#Title { color:#75f5ac; font-size:22px; font-weight:600; }
QTextEdit,QLineEdit,QComboBox,QSpinBox { background:#1c1928; border:1px solid #423049; border-radius:6px; padding:7px; }
QPushButton { background:#372139; border:1px solid #75426d; border-radius:6px; padding:7px 12px; }
QPushButton:hover { background:#5c2c51; }
QPushButton:disabled { color:#777; }
QTabBar::tab { background:#201a2b; padding:9px 16px; }
QTabBar::tab:selected { color:#75f5ac; background:#38213a; }
'''

class Signals(QObject):
    token = Signal(str)
    done = Signal(str)
    error = Signal(str)

class CompanionPanel(QDialog):
    busy_changed = Signal(bool)

    def __init__(self, config, memory, pet):
        super().__init__()
        self.config, self.memory, self.pet = config, memory, pet
        self.model = LocalModel(config)
        self.busy = False
        self._generation = 0
        self.signals = Signals(self)
        self.signals.token.connect(self.on_token)
        self.signals.done.connect(self.on_done)
        self.signals.error.connect(self.on_error)
        self.setWindowTitle('Capri · local companion')
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(540, 620)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        title = QLabel('CAPRI  /  desktop construct')
        title.setObjectName('Title')
        layout.addWidget(title)
        self.status = QLabel('Local conversation · memories stay on this computer')
        layout.addWidget(self.status)
        self.body_status = QLabel('Personality behavior is loading…')
        self.body_status.setWordWrap(True)
        layout.addWidget(self.body_status)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.make_chat()
        self.make_memory()
        self.make_activity()
        self.make_settings()
        self.load_chat()

    def button(self, text, callback):
        result = QPushButton(text)
        result.clicked.connect(callback)
        return result

    def make_chat(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setAcceptRichText(False)
        layout.addWidget(self.chat)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText('Talk to Capri, or /remember something about you')
        self.input.setMaxLength(8000)
        self.input.returnPressed.connect(self.send)
        row.addWidget(self.input)
        self.send_button = self.button('Send', self.send)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        layout.addWidget(QLabel('/remember text   ·   /memories   ·   /forget ID   ·   /clear'))
        self.tabs.addTab(page, 'Chat')

    def load_chat(self):
        self.chat.setPlainText('\n\n'.join(('You' if r['role'] == 'user' else 'Capri') + ': ' + r['content'] for r in self.memory.recent(30)))
        self.chat.moveCursor(QTextCursor.MoveOperation.End)

    def append_plain(self, text):
        self.chat.moveCursor(QTextCursor.MoveOperation.End)
        self.chat.insertPlainText(text)
        self.chat.ensureCursorVisible()

    def send(self):
        text = self.input.text().strip()
        if not text or self.busy:
            return
        self.input.clear()
        self.pet._last_interaction = time.monotonic()
        if text.startswith('/'):
            try:
                if text.startswith('/remember '):
                    item = self.memory.remember(text[10:])
                    self.append_plain(f'\n\nMemory #{item} saved.')
                elif text == '/memories':
                    self.open_tab(1)
                elif text.startswith('/forget '):
                    if not self.memory.forget(int(text[8:])):
                        raise ValueError('That memory ID does not exist.')
                    self.append_plain('\n\nMemory removed. Old chat text is separate; /clear removes that.')
                elif text == '/clear':
                    self.memory.clear_dialogue()
                    self.load_chat()
                else:
                    raise ValueError('Commands: /remember text, /memories, /forget ID, /clear')
            except ValueError as e:
                self.append_plain('\n\n' + str(e))
            self.refresh_memory()
            return
        self.memory.say('user', text)
        self.append_plain('\n\nYou: ' + text + '\n\nCapri: ')
        messages, facts = self.memory.recent(20), self.memory.facts()
        observed = self.pet.observation()
        self.busy = True
        self._generation += 1
        self.input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.status.setText('Capri is thinking locally…')
        self.busy_changed.emit(True)
        def work():
            try:
                reply = self.model.reply(messages, facts, self.signals.token.emit, observation=observed)
                self.signals.done.emit(reply)
            except Exception as error:
                self.signals.error.emit(str(error))
        threading.Thread(target=work, name='capri-local-chat', daemon=True).start()

    def on_token(self, text):
        self.append_plain(text)

    def finished(self):
        self.busy = False
        self.input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.busy_changed.emit(False)
        self.input.setFocus()

    def on_done(self, reply):
        self.memory.say('assistant', reply)
        emit(self.config.directory, {'source': 'capri', 'session': 'chat', 'state': 'ready'})
        self.status.setText('Saved locally · ' + self.config['model'])
        self.pet.say(reply)
        self.finished()

    def on_error(self, error):
        emit(self.config.directory, {'source': 'capri', 'session': 'chat', 'state': 'blocked'})
        self.append_plain('\n\n[Local model unavailable] ' + error + '\nYou can still use memory commands and desktop reactions.')
        self.status.setText('Check the local model and Ollama settings')
        self.finished()

    def make_memory(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        note_label = QLabel('Facts are saved only when you explicitly add them. Chats are logged separately.')
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
        self.memory_view = QTextEdit()
        self.memory_view.setReadOnly(True)
        layout.addWidget(self.memory_view)
        self.note = QLineEdit()
        self.note.setPlaceholderText('A preference, name, boundary, or project to remember')
        self.note.setMaxLength(2000)
        layout.addWidget(self.note)
        layout.addWidget(self.button('Remember this', self.add_memory))
        row = QHBoxLayout()
        self.forget_id = QSpinBox()
        self.forget_id.setRange(1, 10000000)
        row.addWidget(QLabel('Memory ID'))
        row.addWidget(self.forget_id)
        row.addWidget(self.button('Forget note', self.forget_note))
        layout.addLayout(row)
        layout.addWidget(self.button('Export local journal…', self.export))
        self.clear_chat_button = self.button('Clear conversation log', self.clear_chat)
        layout.addWidget(self.clear_chat_button)
        self.tabs.addTab(page, 'Memory')

    def refresh_memory(self):
        facts = self.memory.facts()
        self.memory_view.setPlainText('\n\n'.join(f"#{f['id']} · {f['created_at']}\n{f['content']}" for f in facts) or 'No memory notes yet.')

    def add_memory(self):
        try:
            self.memory.remember(self.note.text())
            self.note.clear()
            self.refresh_memory()
        except ValueError as e:
            QMessageBox.information(self, 'Memory', str(e))

    def forget_note(self):
        self.memory.forget(self.forget_id.value())
        self.refresh_memory()

    def clear_chat(self):
        if self.busy:
            QMessageBox.information(self, 'Conversation', 'Wait for the current reply to finish before clearing it.')
            return
        if QMessageBox.question(self, 'Clear conversation', 'Delete Capri’s saved conversation log? Memory notes remain.') == QMessageBox.StandardButton.Yes:
            self.memory.clear_dialogue()
            self.load_chat()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export local journal', str(self.config.directory / 'journal-export.json'), 'JSON (*.json)')
        if path:
            self.memory.export(path)

    def make_activity(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel('Activity hooks supply state and project names, never prompts or tool output.\nUse Start-Codex-With-Capri.ps1 for instrumented Codex sessions.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.activity_view = QTextEdit()
        self.activity_view.setReadOnly(True)
        layout.addWidget(self.activity_view)
        row = QHBoxLayout()
        for state in ('working', 'waiting', 'ready', 'blocked', 'idle'):
            row.addWidget(self.button(state.title(), lambda _=False, s=state: emit(self.config.directory, {'state': s, 'source': 'demo', 'session': 'preview'})))
        layout.addLayout(row)
        layout.addWidget(self.button('Clear activity journal', self.clear_events))
        self.tabs.addTab(page, 'Activity')

    def clear_events(self):
        self.memory.clear_events()
        self.refresh_activity()

    def refresh_activity(self):
        rows = self.memory.events()
        self.activity_view.setPlainText('\n'.join(f"{r['created_at']}  {r['source']} / {r['state']}  {r['project']}" for r in rows) or 'No activity received yet.')

    def make_settings(self):
        page = QWidget()
        layout = QFormLayout(page)
        self.model_input = QLineEdit(self.config['model'])
        layout.addRow('Installed Ollama model', self.model_input)
        layout.addRow('Ollama endpoint', QLabel(self.config['ollama_url']))
        self.roam = QCheckBox('Zip between monitors')
        self.roam.setChecked(self.config['roaming'])
        layout.addRow('Movement', self.roam)
        self.quiet = QCheckBox('Hide reaction bubbles')
        self.quiet.setChecked(self.config['quiet'])
        layout.addRow('Quiet', self.quiet)
        self.personality_behavior = QCheckBox('Let persona.txt shape desktop behavior')
        self.personality_behavior.setChecked(self.config['personality_behavior'])
        layout.addRow('Personality', self.personality_behavior)
        layout.addRow(self.button('Edit my seed prompt', lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.config.directory/'persona.txt')))))
        self.mouse_awareness = QCheckBox('Know the pointer position and monitor')
        self.mouse_awareness.setChecked(self.config['mouse_awareness'])
        layout.addRow('Mouse awareness', self.mouse_awareness)
        self.mouse_reactions = QCheckBox('Animate on hover, pokes, and nearby-pointer greetings')
        self.mouse_reactions.setChecked(self.config['mouse_reactions'])
        layout.addRow('Mouse reactions', self.mouse_reactions)
        controls=QLabel('Hover: attention · Click: poke · Double-click: chat · Drag: move')
        controls.setWordWrap(True)
        layout.addRow(controls)
        self.media_avoidance=QCheckBox('Stay off screens with active media or fullscreen apps')
        self.media_avoidance.setChecked(self.config['media_avoidance'])
        layout.addRow('Media screens',self.media_avoidance)
        self.automatic_media_watch=QCheckBox('Occasionally decide to watch with popcorn')
        self.automatic_media_watch.setChecked(self.config['automatic_media_watch'])
        layout.addRow('Watch mode',self.automatic_media_watch)
        self.media_status=QLabel('Checking Windows media sessions and fullscreen windows…')
        self.media_status.setTextFormat(Qt.TextFormat.PlainText)
        self.media_status.setWordWrap(True)
        layout.addRow(self.media_status)
        self.mouse_status = QLabel('Pointer position is sampled locally; no pointer trail is saved.')
        self.mouse_status.setWordWrap(True)
        layout.addRow(self.mouse_status)
        layout.addRow(self.button('Save settings', self.save_settings))
        layout.addRow(self.button('Open local data folder', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config.directory)))))
        info = QLabel('Microphone, screen capture, and computer control are not enabled.\nSprite loops play continuously; switching loops triggers glitch travel.\nNew software can publish events through the local bridge.')
        info.setWordWrap(True)
        layout.addRow(info)
        self.tabs.addTab(page, 'Settings')

    def save_settings(self):
        model = self.model_input.text().strip()
        if not model or ':cloud' in model.lower():
            QMessageBox.information(self, 'Model', 'Choose an installed local model name.')
            return
        self.config.set('model', model)
        self.config.set('roaming', self.roam.isChecked())
        self.config.set('quiet', self.quiet.isChecked())
        self.config.set('personality_behavior', self.personality_behavior.isChecked())
        self.config.set('mouse_awareness', self.mouse_awareness.isChecked())
        self.config.set('mouse_reactions', self.mouse_reactions.isChecked())
        self.config.set('media_avoidance',self.media_avoidance.isChecked())
        self.config.set('automatic_media_watch',self.automatic_media_watch.isChecked())
        self.status.setText('Settings saved locally')

    def open_tab(self, index=0):
        self.refresh_memory()
        self.refresh_activity()
        self.tabs.setCurrentIndex(index)
        screen = self.pet.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = max(area.left(), min(self.pet.x() - self.width(), area.right() - self.width() + 1))
        y = max(area.top(), min(self.pet.y() - self.height() + self.pet.height(), area.bottom() - self.height() + 1))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        if index == 0:
            self.input.setFocus()

    def closeEvent(self, event):
        self.hide()
        event.ignore()
