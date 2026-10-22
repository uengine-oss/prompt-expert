"""Hold-to-talk detection, independent of the OS keyboard hook.

The detector is fed raw key events and decides when a "hold" of the trigger
key starts, gets confirmed, is cancelled (tap or key combo such as Alt+Tab),
or finishes. It does no I/O itself; it calls methods on a listener.
"""

import threading

VK_LSHIFT, VK_RSHIFT = 0xA0, 0xA1
VK_LCONTROL, VK_RCONTROL = 0xA2, 0xA3
VK_LMENU, VK_RMENU = 0xA4, 0xA5

HOTKEYS = {
    "alt": (VK_LMENU, VK_RMENU),
    "left_alt": (VK_LMENU,),
    "right_alt": (VK_RMENU,),
    "ctrl": (VK_LCONTROL, VK_RCONTROL),
    "right_ctrl": (VK_RCONTROL,),
    "f13": (0x7C,),
    "f14": (0x7D,),
}


def parse_hotkey(name):
    if isinstance(name, int):
        return (name,)
    key = str(name).strip().lower()
    if key in HOTKEYS:
        return HOTKEYS[key]
    if key.startswith("0x"):
        return (int(key, 16),)
    raise ValueError(f"unknown hotkey: {name!r} (choose from {', '.join(HOTKEYS)})")


class HoldListener:
    def started(self):
        """Trigger went down; start capturing audio right away."""

    def confirmed(self):
        """Held long enough without other keys; this is a real dictation."""

    def cancelled(self):
        """Tap or combo; throw away whatever was captured."""

    def finished(self):
        """Trigger released after a confirmed hold; transcribe."""


IDLE, PENDING, ACTIVE, BLOCKED = "idle", "pending", "active", "blocked"


class HoldDetector:
    def __init__(self, trigger_vks, min_hold, listener, timer_factory=None):
        self.trigger_vks = set(trigger_vks)
        self.min_hold = min_hold
        self.listener = listener
        self.state = IDLE
        self._lock = threading.Lock()
        self._generation = 0
        self._timer_factory = timer_factory or _thread_timer

    def on_key(self, vk, is_down):
        with self._lock:
            event = self._step(vk, is_down)
        self._emit(event)

    def _step(self, vk, is_down):
        is_trigger = vk in self.trigger_vks
        if self.state == IDLE:
            if is_trigger and is_down:
                self.state = PENDING
                self._generation += 1
                self._timer_factory(self.min_hold, self._on_timer, self._generation)
                return "started"
            return None
        if is_trigger:
            if is_down:
                return None  # auto-repeat, or the other Alt
            previous = self.state
            self.state = IDLE
            return {PENDING: "cancelled", ACTIVE: "finished", BLOCKED: None}[previous]
        if is_down and self.state in (PENDING, ACTIVE):
            self.state = BLOCKED
            return "cancelled"
        return None

    def _on_timer(self, generation):
        with self._lock:
            if generation != self._generation or self.state != PENDING:
                return
            self.state = ACTIVE
        self._emit("confirmed")

    def _emit(self, event):
        if event:
            getattr(self.listener, event)()


def _thread_timer(delay, callback, arg):
    timer = threading.Timer(delay, callback, args=(arg,))
    timer.daemon = True
    timer.start()
