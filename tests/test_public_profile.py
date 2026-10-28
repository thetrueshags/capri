import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from capri.companion.config import Config,PROJECT
from capri.companion.persona import load_persona
from capri.companion.model import LocalModel
from capri.companion.personality import PersonalitySync
from capri.companion.behavior import BehaviorProfile

class PublicProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_fresh_profiles_start_empty_and_never_share_a_persona(self):
        self.assertEqual((PROJECT/'persona.template.txt').read_bytes(),b'')
        with tempfile.TemporaryDirectory() as temp:
            one=Config(Path(temp)/'one');two=Config(Path(temp)/'two')
            self.assertEqual(load_persona(one),'')
            self.assertEqual(load_persona(two),'')
            (one.directory/'persona.txt').write_text('Synthetic private persona.',encoding='utf-8')
            self.assertEqual(load_persona(Config(one.directory)),'Synthetic private persona.')
            self.assertEqual(load_persona(two),'')

    def test_chat_uses_the_selected_profiles_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            config=Config(temp)
            marker='SYNTHETIC_LOCAL_PERSONA_TEST_MARKER'
            (config.directory/'persona.txt').write_text(marker,encoding='utf-8')
            model=LocalModel(config)
            model.local_settings=lambda:('http://127.0.0.1:11434','test-local')
            model.opener.open=Mock(return_value=io.BytesIO(b'{"done":true,"message":{"content":"Hello."}}\n'))
            model.reply([{'role':'user','content':'Hello'}],[],lambda token:None)
            system=json.loads(model.opener.open.call_args.args[0].data)['messages'][0]['content']
            self.assertIn(marker,system)

    def test_clearing_persona_does_not_restore_old_traits_on_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            config=Config(temp)
            (config.directory/'behavior-profile.json').write_text(json.dumps({
                'persona_sha256':'old','traits':BehaviorProfile(affection=1).as_dict()}))
            sync=PersonalitySync(config)
            self.assertEqual(sync.profile,BehaviorProfile())
            with patch('capri.companion.personality.LocalModel') as model:
                sync.refresh();model.assert_not_called()

if __name__=='__main__':unittest.main()
