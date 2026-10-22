import unittest

from winwhisper.hotkey import VK_LMENU, VK_RMENU, HoldDetector, parse_hotkey

VK_TAB, VK_SHIFT, VK_A = 0x09, 0xA0, 0x41


class Recorder:
    def __init__(self):
        self.events = []

    def started(self):
        self.events.append("started")

    def confirmed(self):
        self.events.append("confirmed")

    def cancelled(self):
        self.events.append("cancelled")

    def finished(self):
        self.events.append("finished")


class ManualTimer:
    def __init__(self):
        self.pending = []

    def __call__(self, delay, callback, arg):
        self.pending.append((callback, arg))

    def fire(self):
        pending, self.pending = self.pending, []
        for callback, arg in pending:
            callback(arg)


class HoldDetectorTest(unittest.TestCase):
    def setUp(self):
        self.listener = Recorder()
        self.timer = ManualTimer()
        self.detector = HoldDetector(parse_hotkey("alt"), 0.35, self.listener, self.timer)

    def press(self, vk):
        self.detector.on_key(vk, True)

    def release(self, vk):
        self.detector.on_key(vk, False)

    def test_hold_then_release_dictates(self):
        self.press(VK_LMENU)
        self.timer.fire()
        for _ in range(5):
            self.press(VK_LMENU)  # auto-repeat
        self.release(VK_LMENU)
        self.assertEqual(self.listener.events, ["started", "confirmed", "finished"])

    def test_quick_tap_is_ignored(self):
        self.press(VK_LMENU)
        self.release(VK_LMENU)
        self.timer.fire()  # late timer must not confirm
        self.assertEqual(self.listener.events, ["started", "cancelled"])

    def test_alt_tab_cancels_and_waits_for_release(self):
        self.press(VK_LMENU)
        self.press(VK_TAB)
        self.timer.fire()
        self.release(VK_TAB)
        self.press(VK_TAB)
        self.release(VK_LMENU)
        self.assertEqual(self.listener.events, ["started", "cancelled"])
        self.press(VK_LMENU)
        self.timer.fire()
        self.release(VK_LMENU)
        self.assertEqual(self.listener.events[-3:], ["started", "confirmed", "finished"])

    def test_other_key_during_dictation_cancels(self):
        self.press(VK_LMENU)
        self.timer.fire()
        self.press(VK_SHIFT)  # Alt+Shift switches keyboard layout
        self.release(VK_LMENU)
        self.assertEqual(self.listener.events, ["started", "confirmed", "cancelled"])

    def test_right_alt_also_triggers(self):
        self.press(VK_RMENU)
        self.timer.fire()
        self.release(VK_RMENU)
        self.assertEqual(self.listener.events, ["started", "confirmed", "finished"])

    def test_left_alt_only(self):
        detector = HoldDetector(parse_hotkey("left_alt"), 0.35, self.listener, self.timer)
        detector.on_key(VK_RMENU, True)
        detector.on_key(VK_RMENU, False)
        self.assertEqual(self.listener.events, [])

    def test_stale_timer_from_previous_press_is_ignored(self):
        self.press(VK_LMENU)
        stale = self.timer.pending.pop()
        self.release(VK_LMENU)
        self.press(VK_LMENU)
        stale[0](stale[1])
        self.assertEqual(self.listener.events, ["started", "cancelled", "started"])

    def test_unrelated_keys_while_idle(self):
        self.press(VK_A)
        self.release(VK_A)
        self.assertEqual(self.listener.events, [])

    def test_parse_hotkey(self):
        self.assertEqual(parse_hotkey("right_ctrl"), (0xA3,))
        self.assertEqual(parse_hotkey("0x7E"), (0x7E,))
        with self.assertRaises(ValueError):
            parse_hotkey("meta")


if __name__ == "__main__":
    unittest.main()
