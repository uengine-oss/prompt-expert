import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np

if sys.platform == "win32":
    from winwhisper.app import DictationApp, Inserter
    from winwhisper.config import DEFAULTS


@unittest.skipUnless(sys.platform == "win32", "Windows dictation integration")
class DictationTest(unittest.TestCase):
    def make_app(self):
        with patch("winwhisper.app.Transcriber"):
            app = DictationApp(dict(DEFAULTS, sounds=False, overlay=False))
        app.recorder = Mock()
        app.recorder.stop.return_value = np.ones(16000, dtype=np.float32)
        return app

    def control(self, app, commands):
        app._control = Mock()
        app._control.get.side_effect = commands + [StopIteration]
        with self.assertRaises(StopIteration):
            app._control_loop()

    @patch("winwhisper.app.win32.tap_mask_key")
    @patch("winwhisper.app.win32.foreground_window", return_value=123)
    def test_repeated_holds_do_not_queue_stale_dictation(self, *_):
        app = self.make_app()
        self.control(app, ["start", "confirm", "finish", "start", "confirm", "finish"])
        app.recorder.start.assert_called_once()
        app.recorder.stop.assert_called_once()
        self.assertEqual(app._jobs.qsize(), 1)
        self.assertEqual(app._jobs.get()[1], 123)

    def test_failed_job_releases_busy_state(self):
        app = self.make_app()
        app._processing.set()
        app._jobs = Mock()
        app._jobs.get.side_effect = [(np.ones(16000), 123), StopIteration]
        app.transcriber.transcribe.side_effect = RuntimeError("inference failed")
        with self.assertLogs("winwhisper.app", level="ERROR"):
            with self.assertRaises(StopIteration):
                app._job_loop()
        self.assertFalse(app._processing.is_set())
        app._jobs.task_done.assert_called_once()

    @patch("winwhisper.app.win32")
    def test_changed_target_keeps_text_without_pasting(self, win32):
        win32.wait_for_modifiers_released.return_value = True
        win32.foreground_window.return_value = 456
        with self.assertRaises(RuntimeError):
            Inserter().insert("테스트", target=123)
        win32.set_clipboard_text.assert_called_once_with("테스트")
        win32.press_ctrl_v.assert_not_called()

    @patch("winwhisper.app.win32")
    def test_held_modifier_does_not_send_ctrl_v(self, win32):
        win32.wait_for_modifiers_released.return_value = False
        with self.assertRaises(RuntimeError):
            Inserter().insert("테스트", target=123)
        win32.press_ctrl_v.assert_not_called()

    @patch("winwhisper.app.time.sleep")
    @patch("winwhisper.app.win32")
    def test_same_target_pastes_and_restores_clipboard(self, win32, _):
        win32.wait_for_modifiers_released.return_value = True
        win32.foreground_window.return_value = 123
        win32.foreground_in_menu_mode.return_value = False
        win32.get_clipboard_text.return_value = "original"
        Inserter().insert("테스트", target=123)
        win32.press_ctrl_v.assert_called_once()
        self.assertEqual([call.args[0] for call in win32.set_clipboard_text.call_args_list],
                         ["테스트", "original"])
