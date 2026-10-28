import json
import random
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest,QSignalSpy
from PySide6.QtWidgets import QApplication
from capri.companion.config import Config
from capri.companion.interactions import PointerReactions
from capri.companion.media import MediaGuard,MediaController,screen_key
from capri.companion.media_windows import match_playback
from capri.companion.behavior import BehaviorProfile
from capri.companion.motion import Area
from capri.companion.window import DesktopPet

class PointerPolicyTests(unittest.TestCase):
    def test_hover_loops_until_pointer_leaves_with_a_grace_period(self):
        r=PointerReactions()
        self.assertIsNone(r.update(True,1))
        self.assertEqual(r.update(True,1.2),'hover')
        self.assertIsNone(r.update(True,10))
        self.assertIsNone(r.update(False,10.1))
        self.assertIsNone(r.update(True,10.2))
        self.assertEqual(r.active,'hover')
        r.update(False,11)
        self.assertEqual(r.update(False,11.5),'base')

    def test_poke_temporarily_wins_then_returns_to_hover_or_activity(self):
        r=PointerReactions();r.update(True,1);r.update(True,1.2)
        r.poke(2,2)
        self.assertIsNone(r.update(True,3))
        self.assertEqual(r.update(True,4.1),'hover')
        r.poke(5,2)
        self.assertEqual(r.update(False,7.1),'base')
        self.assertEqual(r.last_poke,5)

class MediaPolicyTests(unittest.TestCase):
    def test_playing_browser_metadata_is_matched_to_its_actual_window(self):
        windows=[{'app':'chrome.exe','title':'A film - YouTube','origin':[-3840,5],'fullscreen':False},
                 {'app':'chrome.exe','title':'Source code documentation','origin':[0,0],'fullscreen':False}]
        sessions=[{'app_id':'chrome.exe','title':'A film','video':False,'music':True}]
        result=match_playback(windows,sessions)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['origin'],[-3840,5])

    def test_audio_player_is_not_assumed_to_be_a_video_screen(self):
        windows=[{'app':'spotify.exe','title':'Spotify','origin':[0,0],'fullscreen':False}]
        sessions=[{'app_id':'spotify.exe','title':'A song','video':False,'music':True}]
        self.assertEqual(match_playback(windows,sessions),[])

    def test_fullscreen_and_visible_game_windows_are_protected(self):
        windows=[{'app':'game.exe','title':'Game','origin':[0,0],'fullscreen':True},
                 {'app':'othergame.exe','title':'Windowed game','origin':[-3840,5],'fullscreen':False,'game':True}]
        self.assertEqual(len(match_playback(windows,[])),2)

    def test_mixed_dpi_origins_and_all_screens_protected(self):
        areas=[Area(-3840,5,2560,1392),Area(0,0,2560,1392)]
        guard=MediaGuard()
        guard.update([{'origin':[-3840,0],'app':'chrome.exe'}],areas)
        self.assertEqual(guard.allowed(areas),[areas[1]])
        guard.manual.add(screen_key(areas[1]))
        self.assertEqual(guard.allowed(areas),[])

    def test_watch_perch_faces_the_screen_centre(self):
        area=Area(-3840,5,2560,1392);guard=MediaGuard()
        directions=set()
        for i in range(20):
            point,loop=guard.watch_perch(screen_key(area),[area],(270,290),random.Random(i))
            self.assertTrue(area.contains(point,(270,290)))
            directions.add(loop)
            if loop=='watch-right':self.assertLess(point[0]+135,area.x+area.width/2)
            else:self.assertGreater(point[0]+135,area.x+area.width/2)
        self.assertEqual(directions,{'watch-right','watch-left'})

class WidgetInteractionMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.config=Config(self.temp.name)
        self.config.set('quiet',True)
        self.pet=DesktopPet(self.config);self.pet.timer.stop();self.pet._bubble=''

    def tearDown(self):
        self.pet.close();self.pet.deleteLater();self.app.processEvents();self.temp.cleanup()

    def finish(self):
        if self.pet._transition:
            t=self.pet._transition;t['start']=time.monotonic()-t['duration']-.01
            self.pet.tick()

    def solid_point(self):
        image=self.pet.pose.toImage();scale=self.config['size']/192
        for y in range(75,145):
            for x in range(70,125):
                if all(image.pixelColor(x+dx,y+dy).alpha()>240
                       for dx in (-1,0,1) for dy in (-1,0,1)):
                    return QPoint(round(45+x*scale),round(80+y*scale))
        raise AssertionError('No solid sprite pixel found')

    def test_hover_is_pixel_aware_and_has_a_distinct_loop(self):
        self.assertFalse(self.pet.hit_sprite((self.pet.x()+2,self.pet.y()+2)))
        local=self.solid_point();point=(self.pet.x()+local.x(),self.pet.y()+local.y())
        self.assertTrue(self.pet.hit_sprite(point))
        now=time.monotonic();rect=(self.pet.x()+45,self.pet.y()+80,180,195)
        self.pet.cursor.sample(point,'screen',1,rect,now,over_sprite=True)
        self.pet._sense_next=now+3
        with patch('capri.companion.window.time.monotonic',return_value=now):self.pet.tick()
        with patch('capri.companion.window.time.monotonic',return_value=now+.25):self.pet.tick()
        self.assertEqual(self.pet._target_loop.name,'hover')
        self.assertEqual(self.pet._transition['target'],self.pet._transition['origin'])

    def test_click_pokes_double_click_opens_chat_and_drag_does_not_poke(self):
        spy=QSignalSpy(self.pet.chat_requested)
        point=self.solid_point()
        QTest.mouseClick(self.pet,Qt.MouseButton.LeftButton,pos=point)
        self.assertEqual(self.pet.interactions.active,'poke')
        self.assertTrue(self.pet._target_loop.name.startswith('poke'))
        self.assertEqual(spy.count(),0)
        QTest.mouseDClick(self.pet,Qt.MouseButton.LeftButton,pos=point)
        self.assertEqual(spy.count(),1)
        self.finish()
        self.pet.interactions.update(False,time.monotonic(),False)
        self.pet._transition=None
        point=self.solid_point()
        QTest.mousePress(self.pet,Qt.MouseButton.LeftButton,pos=point)
        QTest.mouseMove(self.pet,point+QPoint(25,0))
        QTest.mouseRelease(self.pet,Qt.MouseButton.LeftButton,pos=point+QPoint(25,0))
        self.assertIsNone(self.pet.interactions.active)

    def test_poke_returns_to_latest_software_state(self):
        self.pet.poke();self.finish()
        self.pet.set_state('working')
        self.assertEqual(self.pet._logical_state,'working')
        self.assertTrue(self.pet.loop.name.startswith('poke'))
        self.pet.interactions._poke_until=time.monotonic()-1
        self.pet.cursor.disable();self.pet._sense_next=time.monotonic()+3
        self.pet.tick();self.finish()
        self.assertEqual(self.pet.loop.name,'typing')

    def test_media_evicts_pet_and_restricts_every_normal_destination(self):
        areas=self.pet.areas()
        if len(areas)<2:self.skipTest('Two monitor integration requires two screens')
        guard=MediaGuard();self.pet.media_guard=guard
        guard.detected={screen_key(areas[0]):{'app':'chrome.exe'}}
        self.pet.move(areas[0].x+50,areas[0].y+50)
        self.pet.enforce_media();self.finish()
        self.assertTrue(areas[1].contains((self.pet.x(),self.pet.y()),self.pet.dimensions()))
        for _ in range(10):
            self.pet.morph();self.finish()
            self.assertTrue(areas[1].contains((self.pet.x(),self.pet.y()),self.pet.dimensions()))
        guard.manual.add(screen_key(areas[1]));self.pet.enforce_media()
        self.assertFalse(self.pet.isVisible())

    def test_explicit_watch_enters_with_popcorn_then_exits_media_screen(self):
        areas=self.pet.areas()
        if len(areas)<2:self.skipTest('Two monitor integration requires two screens')
        guard=MediaGuard();self.pet.media_guard=guard
        key=screen_key(areas[0]);guard.detected={key:{'app':'chrome.exe'}};guard.watching=key
        self.pet.start_watching(key);self.finish()
        self.assertTrue(self.pet.loop.name.startswith('watch-'))
        self.assertTrue(areas[0].contains((self.pet.x(),self.pet.y()),self.pet.dimensions()))
        self.pet.set_state('working')
        self.assertTrue(self.pet.loop.name.startswith('watch-'))
        guard.watching=None;self.pet.stop_watching();self.finish()
        self.assertEqual(self.pet.loop.name,'typing')
        self.assertTrue(areas[1].contains((self.pet.x(),self.pet.y()),self.pet.dimensions()))

    def test_stale_watch_decisions_and_busy_chat_cannot_start_watch(self):
        guard=MediaGuard();key=screen_key(self.pet.areas()[0]);guard.detected={key:{'app':'chrome.exe','title':'new'}}
        controller=MediaController(self.config,guard,self.pet.areas,BehaviorProfile)
        controller.apply_decision({'action':'watch','seconds':60,'screen':key,'candidate':['chrome.exe','old']})
        self.assertIsNone(guard.watching)
        controller._chat_busy=True
        controller.apply_decision({'action':'watch','seconds':60,'screen':key})
        self.assertIsNone(guard.watching)

    def test_watch_ends_when_playback_stops_even_with_manual_protection(self):
        guard=MediaGuard();key=screen_key(self.pet.areas()[0])
        self.config.set('protected_media_screens',[key])
        guard.manual={key};guard.watching=key
        controller=MediaController(self.config,guard,self.pet.areas,BehaviorProfile)
        controller._scanning=True
        controller._watch_until=time.monotonic()+60
        spy=QSignalSpy(controller.watch_stopped)
        controller.tick()
        self.assertIsNone(guard.watching)
        self.assertIn(key,guard.protected())
        self.assertEqual(spy.count(),1)
        self.assertGreater(controller._next_decision,time.monotonic()+590)

    def test_geometry_refresh_cannot_move_onto_protected_screens(self):
        guard=MediaGuard();self.pet.media_guard=guard
        guard.manual={screen_key(a) for a in self.pet.areas()}
        self.pet.show()
        self.pet.ensure_visible()
        self.assertFalse(self.pet.isVisible())

if __name__=='__main__':unittest.main()
