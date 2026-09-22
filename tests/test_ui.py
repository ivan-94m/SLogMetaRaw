# SPDX-License-Identifier: GPL-3.0-or-later
"""Startup and event-loop regressions without opening or changing a Resolve project."""
import json
import os
import sys
import time
import subprocess
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slogmetaraw import ui


class Events:
    def __getattr__(self, key):
        value = SimpleNamespace()
        setattr(self, key, value)
        return value


class Widget:
    def __init__(self, props=None, children=None):
        self.Checked = False
        self.__dict__.update(props or {})
        self.children = children or []
        self.ColumnWidth = {}
        self.Text = getattr(self, 'Text', {})
        self.rows = []
        self.Enabled = True

    def AddItem(self, value):
        self.rows.append(value)

    def SetHeaderLabels(self, labels):
        self.headers = labels

    def Clear(self):
        self.rows.clear()

    def NewItem(self):
        return Widget()

    def AddTopLevelItem(self, item):
        self.rows.append(item)

    def AddChild(self, item):
        self.children.append(item)

    def TopLevelItem(self, index):
        return self.rows[index] if index < len(self.rows) else None

    def TopLevelItemCount(self):
        return len(self.rows)


class Window(Widget):
    def __init__(self, props, child):
        super().__init__(props, [child])
        self.props = props
        self.On = Events()
        self.visible = False
        self.was_shown = False

    def GetItems(self):
        items = {}

        def visit(item):
            if hasattr(item, 'ID'):
                items[item.ID] = item
            for child in item.children:
                visit(child)

        visit(self)
        return items

    def Show(self):
        self.visible = self.was_shown = True

    def Hide(self):
        self.visible = False

    def Raise(self):
        pass


class Manager:
    def __init__(self, timer_available=True):
        self.timer_available = timer_available
        self.timer = mock.Mock()

    def Timer(self, props):
        if not self.timer_available:
            raise AttributeError('Timer unavailable')
        return self.timer

    def __getattr__(self, name):
        if name in ('VGroup', 'HGroup', 'ComboBox', 'Button', 'CheckBox', 'Label', 'Tree'):
            return Widget
        raise AttributeError(name)


class Dispatcher:
    def __init__(self):
        self.On = SimpleNamespace()
        self.run = lambda: None
        self.exit_called = False
        self.visible_when_exit = None

    def AddWindow(self, props, child):
        self.window = Window(props, child)
        return self.window

    def RunLoop(self):
        self.run()

    def ExitLoop(self):
        self.exit_called = True
        self.visible_when_exit = self.window.visible


class UIRegression(unittest.TestCase):
    def setUp(self):
        for target, value in (
            ('_exit_with_resolve', None),
            ('osx_utils.resolve_window_bounds', None),
            ('osx_utils.display_bounds', (0, 0, 1920, 1080)),
            ('osx_utils.play_sound', None),
        ):
            patcher = mock.patch('slogmetaraw.ui.' + target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch('slogmetaraw.ui.t', side_effect=lambda text: text)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.manager = Manager()
        self.dispatcher = Dispatcher()
        self.resolve = mock.Mock()
        self.project = self.resolve.GetProjectManager.return_value.GetCurrentProject.return_value
        self.pool = self.project.GetMediaPool.return_value
        self.pool.GetRootFolder.return_value.GetClipList.return_value = []
        self.pool.GetRootFolder.return_value.GetSubFolderList.return_value = []

    def launch(self, selftest=False):
        return ui.main(self.resolve, SimpleNamespace(UIManager=self.manager),
                       SimpleNamespace(UIDispatcher=lambda manager: self.dispatcher),
                       selftest=selftest)

    def add_clip(self):
        clip = mock.Mock()
        clip.GetUniqueId.return_value = 'clip-1'
        clip.GetName.return_value = 'sample.MP4'
        clip.GetClipProperty.return_value = '/sample.MP4'
        self.pool.GetRootFolder.return_value.GetClipList.return_value = [clip]
        return clip

    def test_window_opens_without_optional_timer(self):
        self.manager.timer_available = False
        result = self.launch(selftest=True)
        self.assertTrue(self.dispatcher.window.was_shown)
        self.assertEqual(result['rows'], 0)

    def test_reader_launch_error_restores_controls(self):
        self.add_clip()
        with mock.patch.object(ui, '_spawn_reader', side_effect=OSError('reader unavailable')):
            with mock.patch.object(ui, '_log_exception'):
                result = self.launch(selftest=True)
        self.assertIn('reader unavailable', result['status'])
        self.assertTrue(self.dispatcher.window.GetItems()['Read'].Enabled)

    def test_dispatcher_timeout_finishes_read_and_writes_on_ui_thread(self):
        self.add_clip()
        process = mock.Mock()
        process.poll.return_value = None
        result = {'meta': {}, 'display': {}, 'sections': [], 'warnings': []}
        writes_on = []

        def write(*args, **kwargs):
            writes_on.append(threading.get_ident())
            return {'failed': [], 'color_space': None}

        def interact():
            self.dispatcher.window.On.Read.Clicked(None)
            items = self.dispatcher.window.GetItems()
            deadline = time.monotonic() + 2
            while not items['Read'].Enabled and time.monotonic() < deadline:
                self.dispatcher.On.Timeout({'who': 'ProgressTimer'})
                time.sleep(0.001)
            self.assertTrue(items['Read'].Enabled)
            self.assertEqual(items['Clips'].TopLevelItemCount(), 1)
            self.assertIn('Lette 1 clip', items['Status'].Text)
            self.dispatcher.window.On.Write.Clicked(None)
            self.dispatcher.On.Timeout({'who': 'ProgressTimer'})
            self.assertTrue(items['Write'].Enabled)
            self.assertIn('Metadata scritti su 1 clip', items['Status'].Text)
            self.assertEqual(writes_on, [threading.get_ident()])

        self.dispatcher.run = interact
        with mock.patch.object(ui, '_spawn_reader', return_value=process):
            with mock.patch.object(ui, '_read_result', return_value={'ok': True, 'result': result}):
                with mock.patch.object(ui.plugin_cache, 'write_cache'):
                    with mock.patch.object(ui.resolve_io, 'apply_to_clip', side_effect=write):
                        self.launch()
        process.kill.assert_called_once()
        process.wait.assert_called_once()
        self.manager.timer.Stop.assert_called()

    def test_update_check_reserves_timer_until_complete(self):
        def interact():
            self.dispatcher.window.On.Version.Clicked(None)
            items = self.dispatcher.window.GetItems()
            self.assertFalse(items['Read'].Enabled)
            deadline = time.monotonic() + 2
            while not items['Read'].Enabled and time.monotonic() < deadline:
                self.dispatcher.On.Timeout({'who': 'ProgressTimer'})
                time.sleep(0.001)
            self.assertTrue(items['Read'].Enabled)
            self.assertIn('Nessuna versione', items['Status'].Text)

        self.dispatcher.run = interact
        with mock.patch.object(ui.upd, 'check', return_value={'newer': False, 'current': '1.1.0'}):
            self.launch()

    def test_closing_window_cancels_reader_and_reaps_helper(self):
        self.add_clip()
        process = mock.Mock()
        process.poll.return_value = None
        reading = threading.Event()

        def read(process, deadline, cancelled):
            reading.set()
            self.assertTrue(cancelled.wait(2))
            return None

        def interact():
            self.dispatcher.window.On.Read.Clicked(None)
            self.assertTrue(reading.wait(1))
            # Returning from RunLoop simulates closing the window mid-read.

        self.dispatcher.run = interact
        with mock.patch.object(ui, '_spawn_reader', return_value=process):
            with mock.patch.object(ui, '_read_result', side_effect=read):
                self.launch()
        process.kill.assert_called_once()
        process.wait.assert_called_once()
        self.assertFalse(self.dispatcher.window.visible)

    def test_close_event_hides_window_before_exiting_dispatcher(self):
        def interact():
            self.dispatcher.window.On.SLogMetaRawWin.Close(None)

        self.dispatcher.run = interact
        self.launch()

        self.assertTrue(self.dispatcher.exit_called)
        self.assertFalse(self.dispatcher.visible_when_exit)
        self.assertFalse(self.dispatcher.window.visible)
        self.assertFalse(self.dispatcher.window.Visible)

    def test_window_uses_nonreserved_button_id_without_close_events_key(self):
        self.launch(selftest=True)

        # 'Events': {'Close': True} breaks the native close on Resolve 21.x
        # (the click is intercepted but never forwarded), so it must be absent.
        self.assertNotIn('Events', self.dispatcher.window.props)
        self.assertIn('CloseButton', self.dispatcher.window.GetItems())
        self.assertNotIn('Close', self.dispatcher.window.GetItems())

    def test_close_event_hides_window_and_exits_dispatcher(self):
        def interact():
            event = {'what': 'Close', 'who': 'SLogMetaRawWin'}
            self.dispatcher.window.On.SLogMetaRawWin.Close(event)
            self.assertTrue(self.dispatcher.exit_called)
            self.assertFalse(self.dispatcher.window.visible)

        self.dispatcher.run = interact
        self.launch()

    def test_close_button_hides_window_and_exits_dispatcher(self):
        def interact():
            self.dispatcher.window.On.CloseButton.Clicked(None)

        self.dispatcher.run = interact
        self.launch()
        self.assertTrue(self.dispatcher.exit_called)
        self.assertFalse(self.dispatcher.visible_when_exit)
        self.assertFalse(self.dispatcher.window.visible)

    def test_watchdog_closes_loop_when_native_window_gone_without_event(self):
        def interact():
            # Some Resolve builds close the native window without forwarding a
            # Close event; two watchdog ticks must notice and exit the loop.
            self.dispatcher.window.Visible = False
            self.dispatcher.On.Timeout({'who': 'WatchdogTimer'})
            self.dispatcher.On.Timeout({'who': 'WatchdogTimer'})

        self.dispatcher.run = interact
        self.launch()

        self.assertTrue(self.dispatcher.exit_called)
        self.assertFalse(self.dispatcher.window.Visible)

    def test_watchdog_ignores_a_stray_single_tick(self):
        def interact():
            self.dispatcher.window.Visible = False
            self.dispatcher.On.Timeout({'who': 'WatchdogTimer'})
            self.dispatcher.window.Visible = True
            self.dispatcher.On.Timeout({'who': 'WatchdogTimer'})

        self.dispatcher.run = interact
        self.launch()

        self.assertFalse(self.dispatcher.exit_called)

    def test_watchdog_stays_silent_when_visibility_is_unreadable(self):
        def interact():
            # A proxy whose Visible cannot be read must never be treated as
            # closed (regression guard for healthy windows). The mock proxy
            # has no Visible attribute at all, so reading it raises.
            self.assertFalse(hasattr(self.dispatcher.window, 'Visible'))
            self.dispatcher.On.Timeout({'who': 'WatchdogTimer'})
            self.dispatcher.On.Timeout({'who': 'WatchdogTimer'})

        self.dispatcher.run = interact
        self.launch()

        self.assertFalse(self.dispatcher.exit_called)

    def test_update_failure_restores_controls(self):
        def interact():
            self.dispatcher.window.On.Version.Clicked(None)
            items = self.dispatcher.window.GetItems()
            deadline = time.monotonic() + 2
            while not items['Read'].Enabled and time.monotonic() < deadline:
                self.dispatcher.On.Timeout({'who': 'ProgressTimer'})
                time.sleep(0.001)
            self.assertTrue(items['Read'].Enabled)
            self.assertIn('broken cache', items['Status'].Text)

        self.dispatcher.run = interact
        with mock.patch.object(ui.upd, 'check', side_effect=ValueError('broken cache')):
            with mock.patch.object(ui, '_log_exception'):
                self.launch()


class ReaderRuntime(unittest.TestCase):
    def test_partial_helper_output_obeys_clip_deadline(self):
        process = subprocess.Popen(
            [sys.executable, '-c', 'import sys,time; sys.stdout.write("{"); sys.stdout.flush(); time.sleep(5)'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            started = time.monotonic()
            self.assertIsNone(ui._read_result(process, started + 0.15))
            self.assertLess(time.monotonic() - started, 1)
        finally:
            ui._stop_reader(process)

    def test_helper_imports_package_with_isolated_resolve_python(self):
        app = '/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents'
        runtime = os.path.join(app, 'Resources/ResolvePython/ResolvePython')
        if not os.path.isfile(runtime):
            self.skipTest('Resolve bundled Python is not installed')
        for host in ('MacOS/Resolve', 'Libraries/Fusion/fuscript'):
            with self.subTest(host=host):
                with mock.patch.object(ui.sys, 'executable', os.path.join(app, host)):
                    process = ui._spawn_reader()
                try:
                    output, _ = process.communicate('/missing sample.MP4\n', timeout=10)
                    self.assertEqual(process.returncode, 0)
                    result = json.loads(output)
                    self.assertFalse(result['ok'])
                    self.assertEqual(result['path'], '/missing sample.MP4')
                finally:
                    ui._stop_reader(process)


if __name__ == '__main__':
    unittest.main()
