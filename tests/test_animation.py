import math
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from capri.companion.animation import frame_index, timed_frame_index
from capri.companion.config import Config
from capri.companion.window import DesktopPet
from capri.companion.behavior import BehaviorEngine, BehaviorProfile

class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(self.temp.name)
        self.config.set('quiet', True)
        self.config.set('mouse_reactions',False)
        self.pet = DesktopPet(self.config)
        self.pet.timer.stop()
        self.pet._bubble = ''

    def tearDown(self):
        self.pet.close()
        self.pet.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def finish_transition(self):
        self.pet._transition['start'] = time.monotonic() - self.pet._transition['duration'] - .01
        self.pet.tick()

    def test_frame_clock_wraps_without_selecting_another_loop(self):
        self.assertEqual([frame_index(t, 4, 4) for t in (0,.25,.5,.75,1.,1.25)], [0,1,2,3,0,1])
        for fps in (0, -1, math.nan):
            with self.assertRaises(ValueError):
                frame_index(1, fps, 3)

    def test_animation_frames_change_in_place_and_wrap(self):
        point, name = self.pet.pos(), self.pet.loop.name
        first = self.pet.pose.toImage()
        self.pet.advance_loop(self.pet._loop_started + self.pet.loop.durations_ms[0]/1000 + .001)
        self.assertNotEqual(first, self.pet.pose.toImage())
        self.assertIsNone(self.pet._transition)
        self.assertEqual(self.pet.pos(), point)
        self.assertEqual(self.pet.loop.name, name)
        self.pet.advance_loop(self.pet._loop_started + self.pet.loop.duration + .001)
        self.assertEqual(first, self.pet.pose.toImage())

    def test_loop_switch_starts_glitch_then_new_loop_at_frame_zero(self):
        old_name = self.pet.loop.name
        self.pet.advance_loop(self.pet._loop_started + .26)
        old_frame = self.pet.pose.cacheKey()
        self.pet.morph()
        self.assertIsNotNone(self.pet._transition)
        self.assertNotEqual(self.pet._target_loop.name, old_name)
        self.assertEqual(self.pet.pose.cacheKey(), old_frame)
        self.finish_transition()
        self.assertIsNone(self.pet._transition)
        self.assertEqual(self.pet._frame_index, 0)
        self.assertNotEqual(self.pet.loop.name, old_name)
        self.pet.advance_loop(self.pet._loop_started + self.pet.loop.durations_ms[0]/1000 + .001)
        self.assertEqual(self.pet._frame_index, 1)

    def test_single_loop_working_state_does_not_trigger_periodic_travel(self):
        self.pet.set_state('working')
        self.finish_transition()
        point = self.pet.pos()
        now = time.monotonic() + 120
        self.pet._switch_next = now - 1
        with patch('capri.companion.window.time.monotonic', return_value=now):
            self.pet.tick()
        self.assertEqual(self.pet.loop.name, 'typing')
        self.assertEqual(self.pet.pos(), point)
        self.assertIsNone(self.pet._transition)

    def test_frame_playback_continues_during_movement_pause_and_drag(self):
        now = time.monotonic()
        self.pet._loop_started = now - self.pet.loop.durations_ms[0]/1000 - .001
        self.pet._pause_until = now + 30
        self.pet._drag = self.pet.pos()
        with patch('capri.companion.window.time.monotonic', return_value=now):
            self.pet.tick()
        self.assertEqual(self.pet._frame_index, 1)
        self.assertIsNone(self.pet._transition)

    def test_same_visual_loop_for_another_state_keeps_playing(self):
        self.pet.loop = self.pet.loops['ready'][1]
        # Exercise shared artwork independently of this library's waiting pose.
        self.pet.loops['waiting']=[self.pet.loop]
        self.pet._logical_state = self.pet.state = 'ready'
        self.pet.pose = self.pet.loop.frames[0]
        started = self.pet._loop_started
        self.pet.set_state('waiting')
        self.assertEqual(self.pet.state, 'waiting')
        self.assertEqual(self.pet.loop.name, 'waving')
        self.assertEqual(self.pet._loop_started, started)
        self.assertIsNone(self.pet._transition)

    def test_software_change_queues_until_current_loop_transition_finishes(self):
        self.pet.morph()
        self.pet.set_state('working')
        self.finish_transition()
        self.assertIsNotNone(self.pet._transition)
        self.assertEqual(self.pet._target_loop.name, 'typing')
        self.finish_transition()
        self.assertEqual(self.pet.state, 'working')
        self.assertEqual(self.pet.loop.name, 'typing')

    def test_hover_greeting_switches_loop_without_evading_a_click(self):
        self.config.set('mouse_reactions',True)
        self.pet.behavior = BehaviorEngine(BehaviorProfile(affection=1,playfulness=1))
        now = time.monotonic()
        size = self.config['size']
        rect = (self.pet.x()+45,self.pet.y()+80,size,round(size*208/192))
        point = (rect[0]+size//2,rect[1]+size//2)
        self.pet.cursor.sample(point,'test screen',1,rect,now-2)
        self.pet.cursor.sample(point,'test screen',1,rect,now)
        self.pet._sense_next = now+1
        with patch('capri.companion.window.time.monotonic',return_value=now):
            self.pet.tick()
        self.assertEqual(self.pet._target_loop.name,'waving')
        self.assertEqual(self.pet._transition['target'],self.pet._transition['origin'])

    def test_disabling_awareness_clears_position_from_chat_context(self):
        self.pet.observation()
        self.config.set('mouse_awareness',False)
        observed = self.pet.observation()
        self.assertEqual(observed['cursor'],{'enabled':False})
        self.assertIsNone(self.pet.cursor.position)

    def test_authored_hold_times_wrap_and_once_playback(self):
        holds=[280,110,110,140,140,320]
        for t,expected in ((0,0),(.279,0),(.280,1),(.390,2),(.5,3),(.78,5),(1.1,0),(1.38,1)):
            self.assertEqual(timed_frame_index(t,holds),expected)
        self.assertEqual(timed_frame_index(20,holds,repeat=False),5)
        for bad in ([],[0,100],[100,-1],[math.nan,1]):
            with self.assertRaises(ValueError):timed_frame_index(1,bad)

    def test_relocation_occurs_only_during_authored_eye_box_frames(self):
        self.pet.move(*self.pet.areas()[0].clamp((200,300),self.pet.dimensions()))
        origin=(self.pet.x(),self.pet.y())
        target=(origin[0]+200,origin[1])
        self.pet.morph('working',target=target)
        transition=self.pet._transition
        clip=transition['clip']
        self.assertIn('move-right',clip.name)
        now=time.monotonic()
        for progress in (.2,.45,.8):
            transition['start']=now-progress*transition['duration']
            with patch('capri.companion.window.time.monotonic',return_value=now):self.pet.tick()
            point=(self.pet.x(),self.pet.y())
            if progress==.2:self.assertEqual(point,origin)
            if progress==.45:
                self.assertNotEqual(point,origin)
                frame=clip.frames[clip.index(progress*clip.duration,False)].toImage()
                occupied=[y for y in range(frame.height()) if any(frame.pixelColor(x,y).alpha()>90 for x in range(frame.width()))]
                self.assertLess(max(occupied)-min(occupied),30)
            if progress==.8:self.assertEqual(point,target)

    def test_body_reactions_keep_looping_until_controller_changes_them(self):
        self.pet._target_loop=self.pet.loops['poke'][0]
        self.pet.commit_loop(time.monotonic(),'poke')
        self.pet.advance_loop(self.pet._loop_started+self.pet.loop.duration+.001)
        self.assertEqual(self.pet._frame_index,0)

if __name__ == '__main__':
    unittest.main()
