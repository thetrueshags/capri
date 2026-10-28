import concurrent.futures
import json
from pathlib import Path
import random
import tempfile
import time
import tomllib
import unittest
from capri.companion.events import Activity, clean_event, drain, emit, hook_event
from capri.companion.memory import Memory
from capri.companion.model import local_url
from capri.companion.motion import Area, destination, nearest_visible, transition_phase
from tools.codex_with_capri import overrides
from capri.companion.config import Config

class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.memory = Memory(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_memory_and_conversation_survive_restart(self):
        item = self.memory.remember('I prefer quiet company while coding.')
        self.memory.say('user', '<script>not markup</script>')
        self.memory.say('assistant', 'Got it.')
        restored = Memory(self.root)
        self.assertEqual(restored.facts()[0]['source'], 'explicit_user_edit')
        self.assertEqual(restored.recent()[0]['content'], '<script>not markup</script>')
        self.assertTrue(restored.forget(item))
        self.assertEqual(Memory(self.root).facts(), [])

    def test_clear_and_export_have_separate_scopes(self):
        self.memory.remember('Remember the project name.')
        self.memory.say('user', 'Hi')
        self.memory.clear_dialogue()
        self.assertEqual(self.memory.recent(), [])
        target = self.root / 'export.json'
        self.memory.export(target)
        result = json.loads(target.read_text())
        self.assertEqual(len(result['facts']), 1)
        self.assertEqual(result['dialogue'], [])

    def test_hooks_discard_private_payload(self):
        payload = {'hook_event_name': 'PermissionRequest', 'session_id': 'abc',
                   'cwd': 'C:\\projects\\private-app', 'prompt': 'SECRET',
                   'tool_input': {'api_key': 'SECRET'}, 'transcript_path': 'SECRET'}
        event = hook_event(payload)
        self.assertEqual(event['state'], 'waiting')
        self.assertEqual(event['project'], 'private-app')
        self.assertNotIn('SECRET', json.dumps(event))

    def test_structured_tool_failures_react_without_copying_output(self):
        event = hook_event({'hook_event_name': 'PostToolUse',
                            'tool_response': {'exit_code': 1, 'output': 'SECRET'}})
        self.assertEqual(event['state'], 'blocked')
        self.assertNotIn('SECRET', json.dumps(event))

    def test_profile_settings_survive_without_changing_other_profiles(self):
        one, two = Config(self.root / 'one'), Config(self.root / 'two')
        one.set('roaming', False)
        self.assertFalse(Config(self.root / 'one')['roaming'])
        self.assertTrue(two['roaming'])

    def test_parallel_hook_writers_are_atomic_and_deduplicated(self):
        def write(_):
            return emit(self.root, {'state': 'working', 'source': 'codex', 'session': 'a'})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            events = list(pool.map(write, range(24)))
        activity = Activity()
        self.assertEqual(drain(self.root, self.memory, activity), 24)
        self.assertEqual(drain(self.root, self.memory, activity), 0)
        emit(self.root, events[0])
        self.assertEqual(drain(self.root, self.memory, activity), 0)
        self.assertEqual(len(self.memory.events()), 24)

    def test_partial_input_is_ignored_and_malformed_input_retained(self):
        inbox = self.root / 'inbox'
        inbox.mkdir()
        (inbox / 'partial.tmp').write_text('{')
        (inbox / 'bad.json').write_text('{')
        self.assertEqual(drain(self.root, self.memory, Activity()), 0)
        self.assertTrue((inbox / 'partial.tmp').exists())
        self.assertTrue((inbox / 'bad.rejected').exists())

    def test_waiting_session_is_not_hidden_by_other_busy_session(self):
        activity = Activity()
        now = time.time()
        activity.apply(clean_event({'source': 'codex', 'session': 'a', 'state': 'waiting', 'time': now}), now)
        activity.apply(clean_event({'source': 'codex', 'session': 'b', 'state': 'working', 'time': now + 1}), now + 1)
        self.assertEqual(activity.current(now + 2)['state'], 'waiting')
        activity.apply(clean_event({'source': 'codex', 'session': 'a', 'state': 'ready', 'time': now + 3}), now + 3)
        self.assertEqual(activity.current(now + 4)['state'], 'working')

    def test_stale_events_and_out_of_order_completion(self):
        activity = Activity()
        now = time.time()
        stale = clean_event({'state': 'working', 'time': now - 600})
        activity.apply(stale, now)
        self.assertIsNone(activity.current(now))
        activity.apply(clean_event({'state': 'ready', 'time': now}), now)
        activity.apply(clean_event({'state': 'working', 'time': now - 2}), now)
        self.assertEqual(activity.current(now)['state'], 'ready')
        self.assertIsNone(activity.current(now + 19))

    def test_negative_and_disjoint_monitor_geometry(self):
        areas = [Area(-1920, -200, 1920, 1040), Area(0, 0, 2560, 1400)]
        size = (270, 290)
        rng = random.Random(42)
        visited = set()
        for _ in range(500):
            point = destination(areas, size, rng)
            self.assertTrue(any(a.contains(point, size) for a in areas))
            visited.add(next(i for i,a in enumerate(areas) if a.contains(point,size)))
        self.assertEqual(visited, {0,1})
        for point in [(-30,-300), (-2500,1200), (5000,5000), (-1,900)]:
            bounded = nearest_visible(point, size, areas)
            self.assertTrue(any(a.contains(bounded,size) for a in areas))

    def test_removed_monitor_recovers_to_remaining_screen(self):
        screen = Area(0, 0, 1920, 1040)
        self.assertEqual(nearest_visible((-1800, 700), (270,290), [screen]), (0,700))

    def test_transition_is_decompile_zip_recompile(self):
        self.assertEqual([transition_phase(t)[0] for t in (0,.2,.3,.5,.65,1)],
                         ['decompile','decompile','zip','zip','recompile','recompile'])

    def test_only_loopback_model_endpoints(self):
        self.assertEqual(local_url('http://127.0.0.1:11434/'), 'http://127.0.0.1:11434')
        for url in ['https://remote.example', 'http://192.168.1.1:11434', 'http://user:pass@localhost']:
            with self.assertRaises(ValueError):
                local_url(url)

    def test_codex_overrides_are_valid_toml_and_retain_timeouts(self):
        args = overrides(self.root)
        for argument in args[1::2]:
            config = tomllib.loads(argument)
            event = next(iter(config['hooks']))
            hook = config['hooks'][event][0]['hooks'][0]
            self.assertEqual(hook['timeout'], 2)
            self.assertIn('bridge.py', hook['command'])

if __name__ == '__main__':
    unittest.main()
