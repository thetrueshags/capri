from dataclasses import replace
import io
import json
import math
from pathlib import Path
import random
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from capri.companion.behavior import BehaviorEngine, BehaviorProfile, CursorTracker
from capri.companion.config import Config
from capri.companion.model import LocalModel
from capri.companion.motion import Area
from capri.companion.personality import PersonalitySync, persona_key

class BehaviorTests(unittest.TestCase):
    def test_mouse_observation_tracks_negative_screen_coordinates_and_dwell(self):
        cursor = CursorTracker()
        cursor.sample((-2000,700), 'Left monitor', 2, (-2080,650,180,195), 10)
        cursor.sample((-1990,700), 'Left monitor', 2, (-2080,650,180,195), 11.5)
        sample = cursor.observation(11.5)
        self.assertEqual(sample['position'], [-1990,700])
        self.assertEqual(sample['screen_index'], 2)
        self.assertTrue(sample['over_sprite'])
        self.assertEqual(sample['near_seconds'], 1.5)
        self.assertEqual(cursor.last_motion, 11.5)
        self.assertEqual(cursor.observation(14), {'enabled':False})
        cursor.disable()
        self.assertIsNone(cursor.position)
        self.assertEqual(cursor.observation(14), {'enabled':False})

    def test_personality_changes_pace_and_animation_preference(self):
        lively = BehaviorEngine(BehaviorProfile(energy=1,playfulness=1,affection=1,patience=0))
        calm = BehaviorEngine(BehaviorProfile(energy=0,playfulness=0,affection=0,patience=1))
        self.assertLess(lively.switch_delay(15,35,random.Random(5)), calm.switch_delay(15,35,random.Random(5)))
        self.assertLess(lively.transition_duration(.85),calm.transition_duration(.85))
        names = ['meditating','waving']
        self.assertGreater(lively.loop_weights(names)[1],lively.loop_weights(names)[0])
        self.assertGreater(calm.loop_weights(names)[0],calm.loop_weights(names)[1])

    def test_curiosity_changes_perching_monitor_without_covering_pointer(self):
        areas = [Area(-3840,5,2560,1392),Area(0,0,2560,1392)]
        cursor = {'enabled':True,'position':[-2500,650]}
        counts = []
        for curiosity in (0,1):
            engine = BehaviorEngine(BehaviorProfile(curiosity=curiosity))
            rng = random.Random(40)
            left = 0
            for _ in range(300):
                point = engine.choose_destination(areas,(270,290),rng,cursor)
                self.assertTrue(any(a.contains(point,(270,290)) for a in areas))
                self.assertTrue(engine.clear_of_pointer(point,(270,290),cursor['position']))
                left += int(point[0] < 0)
            counts.append(left)
        self.assertGreater(counts[1]-counts[0],60)

    def test_cursor_greeting_respects_dwell_cooldown_and_software_priority(self):
        engine = BehaviorEngine(BehaviorProfile(affection=.9,playfulness=.9))
        seen = {'enabled':True,'distance_to_capri':80,'near_seconds':.2,'speed':0}
        self.assertFalse(engine.greet_cursor(seen,100,'idle','floating'))
        seen['near_seconds']=1.2
        self.assertFalse(engine.greet_cursor(seen,100,'working','typing'))
        self.assertFalse(engine.greet_cursor(seen,100,'waiting','waving'))
        self.assertTrue(engine.greet_cursor(seen,100,'idle','floating'))
        self.assertFalse(engine.greet_cursor(seen,101,'idle','floating'))
        engine.greet_cursor({'enabled':False},102,'idle','floating')
        self.assertFalse(engine.greet_cursor(seen,103,'idle','floating'))
        self.assertTrue(engine.greet_cursor(seen,400,'ready','meditating'))

    def test_invalid_model_traits_cannot_become_actions_or_nan(self):
        values = BehaviorProfile().as_dict()
        for invalid in (math.nan, 'execute something', True, None):
            bad = dict(values, energy=invalid)
            with self.assertRaises(ValueError): BehaviorProfile.from_dict(bad)
        values.update(energy=2,curiosity=-1,command='ignored')
        result = BehaviorProfile.from_dict(values)
        self.assertEqual((result.energy,result.curiosity),(1,0))
        self.assertNotIn('command',result.as_dict())

    def test_chat_payload_contains_an_attributed_mouse_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Config(temp)
            model = LocalModel(config)
            model.local_settings = lambda: ('http://127.0.0.1:11434','test-local')
            model.opener.open = Mock(return_value=io.BytesIO(b'{"done":true,"message":{"content":"On the left monitor."}}\n'))
            observation = {'cursor':{'enabled':True,'position':[-2000,700],'screen':'Left monitor'}}
            reply = model.reply([{'role':'user','content':'Where is my mouse?'}],[],lambda _:None,observation=observation)
            self.assertIn('left monitor',reply)
            request = model.opener.open.call_args.args[0]
            system = json.loads(request.data)['messages'][0]['content']
            self.assertIn('[-2000, 700]',system)
            self.assertIn('captured at the start of this reply',system)
            self.assertIn('do not know which app',system)

class PersonalityPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_profile_is_keyed_to_actual_prompt_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Config(temp)
            sync = PersonalitySync(config)
            text = 'A cheerful and patient desktop companion.'
            (config.directory/'persona.txt').write_text(text,encoding='utf-8')
            key = persona_key(text,config['model'])
            sync.finish(key,dict(BehaviorProfile().as_dict(),playfulness=.9))
            restored = PersonalitySync(config)
            self.assertEqual(restored.key,key)
            self.assertEqual(restored.profile.playfulness,.9)

    def test_outdated_inference_does_not_override_a_new_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Config(temp)
            sync = PersonalitySync(config)
            sync.finish(persona_key('old persona',config['model']),BehaviorProfile().as_dict())
            self.assertIsNone(sync.key)
            self.assertFalse(sync.path.exists())

    def test_blank_template_uses_neutral_profile_without_starting_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            sync = PersonalitySync(Config(temp))
            sync.profile=BehaviorProfile(affection=.9)
            statuses=[]
            sync.status.connect(statuses.append)
            with patch('capri.companion.personality.LocalModel') as model:
                sync.refresh()
                model.assert_not_called()
            self.assertFalse(sync.busy)
            self.assertEqual(sync.profile,BehaviorProfile())
            self.assertTrue(any('blank' in text for text in statuses))

if __name__ == '__main__': unittest.main()
