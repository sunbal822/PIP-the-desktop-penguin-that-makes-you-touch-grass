import tkinter as tk
import tkinter.font as tkfont
import threading, ctypes, os, time, json, math, random, base64, urllib.request, re, asyncio, tempfile, queue
import io, wave, faulthandler, sys, datetime, statistics
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import cv2
import ollama, pyttsx3
# Optional natural-sounding neural voice. Install with: python -m pip install -U edge-tts playsound3
try:
    import edge_tts
except ImportError:
    edge_tts = None
try:
    from playsound3 import playsound
except ImportError:
    playsound = None
try:
    import winsound
except ImportError:
    winsound = None

try:
    faulthandler.enable(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log"), "w"))
except Exception:
    pass


# ---------- Safe MP3 playback (replaces playsound3, which crashes on Python 3.14) ----------
if os.name == "nt":
    _winmm = ctypes.windll.winmm
    _winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    _winmm.mciSendStringW.restype = ctypes.c_uint
    _mci_buf = ctypes.create_unicode_buffer(256)
    _mci_n = [0]

    def play_mp3(path):
        """Play an MP3 and wait until it finishes."""
        _mci_n[0] += 1
        alias = f"pipsnd{_mci_n[0]}"
        short = ctypes.create_unicode_buffer(520)
        ctypes.windll.kernel32.GetShortPathNameW(os.path.abspath(path), short, 520)
        p = short.value or os.path.abspath(path)
        err = _winmm.mciSendStringW(f'open "{p}" type mpegvideo alias {alias}', _mci_buf, 255, None)
        if err:
            raise RuntimeError(f"could not open audio (MCI error {err})")
        try:
            _winmm.mciSendStringW(f"play {alias} wait", _mci_buf, 255, None)
        finally:
            _winmm.mciSendStringW(f"close {alias}", _mci_buf, 255, None)

    playsound = play_mp3

NAME = "Pip"
GEMMA = "gemma3:4b"
VERIFY_MODEL = "gemma3:4b"   # try "gemma3:12b" (after ollama pull gemma3:12b) if the photo check or quiz judge is sloppy

# ---- Settings ----
DEMO = False   # True = fast timers for testing. Set False for real use.
if DEMO:
    LEVEL_AT = 30     # "30 minutes": Pip starts nudging (raised hand). 2x this = fuming.
    LOCK_WARN = 20    # "5 minutes": warning period between fuming and the lock
    IDLE_RESET = 20   # seconds without input = you took a break
    MIN_UNIT = 3      # a granted "minute" lasts 3 seconds in demo
    MIN_AWAY = 10     # seconds away from keyboard/mouse that count as "left the screen"
    TODO_NAG = 60     # Pip checks in about your open tasks after this many seconds
else:
    LEVEL_AT = 1800   # 30 minutes
    LOCK_WARN = 300   # 5 minutes
    IDLE_RESET = 300
    MIN_UNIT = 60
    MIN_AWAY = 300
    TODO_NAG = 5400   # 90 minutes

MAX_GRANTS = 2        # times Pip can be talked into extra time per work stretch
QUEST_CALM = 90 if DEMO else 1500   # seconds Pip stays calm (and the screen timer waits) after you accept a quest
MAX_GRANT_MIN = 30    # most extra minutes Pip can grant at once

# ---- v8 settings: camera checks, reminders, weather ----
CAM_MONITOR = True    # camera watches for: face present (away check), blink rate, posture. Frames are never saved.
BLINK_LOW = 8         # blinks per minute below this triggers a blink reminder (people blink ~15-20 normally)
WEATHER_AWARE = True  # bad weather swaps "outdoors" quests for indoor ones
MAX_HOT, MIN_COLD = 40, 3   # degrees C: hotter or colder than this counts as bad outdoor weather
if DEMO:
    EYE_REST_EVERY = 90    # seconds of screen use between 20-20-20 reminders
    POSTURE_AFTER = 15     # seconds of bad posture before Pip says something
    BLINK_WINDOW = 45      # seconds of face-on-camera needed to judge blink rate
    REMIND_GAP = 45        # seconds before the same reminder can repeat
    ANY_GAP = 12           # seconds between any two reminders
else:
    EYE_REST_EVERY = 1200  # 20 minutes
    POSTURE_AFTER = 60
    BLINK_WINDOW = 120
    REMIND_GAP = 600
    ANY_GAP = 90

ALLOW_ESCAPE = True   # Ctrl+Shift+Q unlocks the lock screen in an emergency
VOICE_INDEX = 1                 # used only by the offline pyttsx3 fallback
RATE = 175                      # slower, less rushed fallback voice
NEURAL_VOICE = "en-US-JennyNeural" # friendly, more mature-sounding neural voice
NEURAL_RATE = "+18%"             # quick and bouncy
NEURAL_PITCH = "+6Hz"            # a little brighter and quirkier
SFX_VOLUME = 0.6                 # sound effect loudness (0 to 1)
TEXT_DELAY = 0.12                # raise if text shows before the voice, lower if after
TYPE_SPEED = 0.07                # seconds per word when voice is off
MIC_DEVICE = 2        # 2 = Realtek Microphone Array on this PC. None = Windows default mic.
CAM_INDEX = 0         # your Iriun phone camera

# Weather location (Open-Meteo, free, no API key). Change these to your own.
PLACE, LAT, LON = "Lahore", 31.5204, 74.3587

W, H = 220, 262
FOOT = 40            # space under Pip's feet for the name tag
KEY = "#010203"       # this color becomes see-through
BODY, BODY_HI, BELLY = "#3d3b73", "#57539c", "#fff4e6"
RED, RED_HI = "#b3323f", "#d24b57"
PEACH, LAV, LAV_DK, PINK, BLUSH = "#ffb36b", "#c8a8ff", "#8e6fd1", "#ff8fb1", "#ff9fb2"

# ---- Look and feel ----
BG, CHAT_BG = "#fff6fb", "#fbf7ff"
INK, MUTED = "#2d2640", "#8a7fa0"
VIOLET, LILAC, MINT = "#7c5cd6", "#efe6ff", "#d9f5ea"
DANGER, DANGER_BG = "#ff5a6b", "#3a0f1a"
PLUM = "#2a1236"
CARD = BG
CARD_BG, EDGE, TRACK, HALO = "#251b4a", "#3f3180", "#0e0920", "#2f2262"   # set by apply_theme()
HEAD1, HEAD2 = "#3a2476", "#1b1436"
BUB_PIP, BUB_YOU, ON_ACCENT, GOLD = "#33276a", "#ff6fa5", "#1d1236", "#ffd34d"
FONT = "Segoe UI"

PERSONA = ("a small chronically-online penguin who lives on the user's desktop. Your life mission is to get the "
           "user off the screen. You speak in all lowercase, warm, funny and a little dramatic, with light slang "
           "(come on, you really need to be one with the earth now, please go touch grass) but always easy to "
           "understand. Never use emojis.")

# What Pip can send you to do. where = "out" / "in". when = "day" / "night" limits it to that time.
# proof = "item" (camera check) or "debrief" (time away + Pip questions you).
OUTDOOR = [
    {"id": "walk", "where": "out", "title": "Go for a stroll and bring Pip a leaf", "tag": "walking", "color": "#7ddba3",
     "hint": "", "proof": "item", "item": "a leaf", "label": "leaf", "away": 1},
    {"id": "flower", "where": "out", "title": "Find a flower and show Pip", "tag": "walking", "color": "#ff8fb1",
     "hint": "", "proof": "item", "item": "a flower", "label": "flower", "away": 1},
    {"id": "pebble", "where": "out", "title": "Find a cool pebble or rock", "tag": "walking", "color": "#b9b9c9",
     "hint": "", "proof": "item", "item": "a pebble or rock", "label": "pebble or rock", "away": 1},
    {"id": "grass", "where": "out", "title": "Go touch actual grass and show Pip", "tag": "walking", "color": "#7ddba3",
     "hint": "", "proof": "item", "item": "some grass", "label": "grass", "away": 1},
    {"id": "block", "where": "out", "title": "Walk briskly once around the block", "tag": "walking", "color": "#a8c8ff",
     "hint": "", "proof": "debrief", "away": 2},
    {"id": "sun", "where": "out", "when": "day", "title": "Sit in the sun for a bit", "tag": "sunlight",
     "color": "#ffd966", "hint": "", "proof": "debrief", "away": 1},
    {"id": "sky", "where": "out", "when": "night", "title": "Step outside and look at the sky for a few minutes",
     "tag": "sunlight", "color": "#8e6fd1", "hint": "", "proof": "debrief", "away": 1},
]
INDOOR = [
    {"id": "dance", "where": "in", "title": "Dance it out (a proper routine)", "tag": "dancing", "color": "#ff8fb1",
     "hint": "", "proof": "debrief", "away": 2},
    {"id": "cook", "where": "in", "title": "Go make something to eat", "tag": "cooking", "color": "#ffb36b",
     "hint": "", "proof": "item", "item": "a plate of food or a dish", "label": "food or dish", "away": 1},
    {"id": "tea", "where": "in", "title": "Make a hot drink or fill a big glass of water", "tag": "cooking",
     "color": "#ffd966", "hint": "", "proof": "item", "item": "a cup or glass", "label": "cup or container",
     "away": 1},
    {"id": "stretch", "where": "in", "title": "Stretch or do yoga away from the screen", "tag": "stretching",
     "color": "#a8c8ff", "hint": "", "proof": "debrief", "away": 1},
    {"id": "tidy", "where": "in", "title": "Tidy one corner of your room", "tag": "stretching", "color": "#9be7c4",
     "hint": "", "proof": "debrief", "away": 1},
    {"id": "call", "where": "in", "title": "Call or voice-message someone you like", "tag": "podcasts",
     "color": "#c8a8ff", "hint": "", "proof": "debrief", "away": 1},
]
ACTIVITIES = OUTDOOR + INDOOR
LIKES = [("walking", "walking / strolls"), ("dancing", "dancing"), ("cooking", "cooking / making"),
         ("stretching", "stretching / yoga"), ("sunlight", "sitting in the sun"), ("podcasts", "podcasts / music")]
LABELS = ["leaf", "stick or twig", "flower", "pebble or rock", "grass", "food or dish",
          "cup or container", "hand or body part", "shoe or clothing",
          "electronic device or screen", "printed picture", "wall or furniture", "other"]
SCREEN_LABELS = ("electronic device or screen", "printed picture")
GRANT_WORDS = ("minute", "min ", "mins", "hour", "meeting", "call", "later", "busy", "deadline",
               "wait", "free", "after", "soon", "exam", "class")

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "attempts.jsonl")
DATA_FILE = os.path.join(HERE, "pip_data.json")
CAPTURE_DIR = os.path.join(HERE, "captures")
os.makedirs(CAPTURE_DIR, exist_ok=True)
# ------------------


# ---------- Saved data (profile, growth, diary, to-do, memory, stats, wardrobe) ----------
def load_data():
    d = {"profile": {"name": "", "likes": []}, "quests_done": 0, "diary": [], "todo": [], "memory": [],
         "theme": "Lavender", "stats": {}, "wardrobe": {}, "cosmetics_seen": [], "photo_hashes": [],
         "cam_monitor": True}
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            d.update(json.load(f))
    except Exception:
        pass
    return d


def save_data():
    data["quests_done"] = quests_done
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


data = load_data()
quests_done = int(data.get("quests_done", 0))
THEME_NAME = data.get("theme", "Lavender")   # each completed quest makes Pip bigger

active = 0            # seconds of continuous use
grace = 0             # extra seconds Pip has granted
grants_used = 0
warned = False
locked = False
joy_until = 0.0
todo_timer = 0
todo_nudge = False
quest = None          # {"act": ..., "started": ..., "away_max": ...}
pending = {"kind": None, "act": None, "index": None, "question": ""}   # waiting for a debrief / highlight / reflection / task
busy = {"on": False}
events = []           # recent things that happened, so Pip can refer to them
history = []          # the conversation (clean text only)
weather_text = "unknown"
weather_info = {}     # {"desc": ..., "day": bool, "temp": float}, filled by fetch_weather
last_pick = {"id": None}
last_weather = 0.0
chat_win = chat_view = chat_entry = mic_button = status_label = quest_label = None
weather_label = level_label = cur_bubble = None
journal_win = journal_list = warn_win = warn_label = lock_win = proof_win = todo_win = todo_list = None
lock_body = lock_msg = lock_status = lock_mic = None
stream_text = [""]
proof = {"cam": None, "frame": None, "label": None, "status": None, "btn": None, "photo": None, "w": 480}
stt_model = None
listening = {"on": False}
speak_lock = threading.Lock()
MIC_IDLE, MIC_BUSY = "Speak", "Listening..."


def profile_name():
    return data["profile"].get("name") or "friend"


def alive(w):
    try:
        return w is not None and w.winfo_exists()
    except tk.TclError:
        return False


# ---------- Theme helpers: fonts, colors, pill buttons, bubbles, scrolling ----------
def init_fonts():
    """Pick the most game-like font that is installed (falls back to Segoe UI)."""
    global FONT
    have = set(tkfont.families())
    for name in ("Bahnschrift", "Arial Rounded MT Bold", "Segoe UI"):
        if name in have:
            FONT = name
            return


def F(size, bold=False):
    return (FONT, size, "bold" if bold else "normal")


def rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def shade(h, f):
    r, g, b = rgb(h)
    return "#%02x%02x%02x" % (min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f)))


def rounded_poly(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def gradient_image(w, h, c1, c2):
    img = tk.PhotoImage(width=w, height=h)
    r1, g1, b1 = rgb(c1)
    r2, g2, b2 = rgb(c2)
    for y in range(h):
        t = y / max(1, h - 1)
        col = "#%02x%02x%02x" % (int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))
        img.put(col, to=(0, y, w, y + 1))
    return img


class PillButton(tk.Canvas):
    """A chunky arcade button that supports .config(text=..., state=...) like a normal Button."""
    _down = False
    _keep = False

    def __init__(self, parent, text, command=None, bg=VIOLET, fg="white", font=None, height=40,
                 width=None, pad=22, outline=None):
        self._text, self._cmd, self._pbg, self._pfg = text, command, bg, fg
        self._pfont, self._poutline, self._pstate, self._hover, self._ph = font or F(11, True), outline, "normal", False, height
        w = width or (tkfont.Font(font=self._pfont).measure(text) + 2 * pad)
        super().__init__(parent, width=w, height=height, bg=parent.cget("bg"), highlightthickness=0, bd=0,
                         cursor="hand2")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self._draw()

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _press(self, e):
        if self._pstate == "normal":
            self._down = True
            self._draw()

    def _release(self, e):
        was = self._down
        self._down = False
        self._draw()
        if was and self._pstate == "normal" and self._cmd:
            self._cmd()

    def _draw(self):
        """Chunky arcade button: a coloured face sitting on a darker 3D lip that it sinks into when pressed."""
        self.delete("all")
        w = max(self.winfo_width(), int(float(self.cget("width"))))
        h = self._ph
        lip = max(3, h // 9)
        bh = h - lip
        off = lip if self._down else 0
        r = (bh - 2) // 2
        if self._pstate == "disabled":
            fill, edge, fg = shade(CARD_BG, 1.3), shade(CARD_BG, 0.8), MUTED
        else:
            base, fg = (self._pbg, self._pfg) if (self._poutline or self._keep) else (VIOLET, "white")
            fill = shade(base, 1.1) if self._hover else base
            edge = shade(base, 0.6)
        self.create_polygon(rounded_poly(1, lip + 1, w - 1, h - 1, r), smooth=True, fill=edge, outline=edge)
        self.create_polygon(rounded_poly(1, 1 + off, w - 1, bh - 1 + off, r), smooth=True, fill=fill,
                            outline=self._poutline or fill, width=2 if self._poutline else 1)
        if self._pstate != "disabled" and not self._poutline:
            self.create_line(r, 4 + off, w - r, 4 + off, fill=shade(fill, 1.3), width=2, capstyle="round")
        self.create_text(w // 2, bh // 2 + off + 1, text=self._text, fill=fg, font=self._pfont)

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self._text = kw.pop("text")
        if "state" in kw:
            self._pstate = kw.pop("state")
        if "bg" in kw:
            self._pbg = kw.pop("bg")
        if "fg" in kw:
            self._pfg = kw.pop("fg")
        if kw:
            tk.Canvas.configure(self, **kw)
        self._draw()

    config = configure


class Bubble(tk.Canvas):
    """A rounded chat bubble whose text can be updated while it streams in."""

    def __init__(self, parent, text, fill, fg, maxw=300):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self._fill = fill
        self._txt = self.create_text(14, 9, text=text or " ", anchor="nw", width=maxw, fill=fg, font=F(11))
        self.set(text)

    def set(self, text):
        self.itemconfigure(self._txt, text=text if text else " ")
        x1, y1, x2, y2 = self.bbox(self._txt)
        w, h = x2 + 14, y2 + 9
        self.delete("bubble_shape")
        self.create_polygon(rounded_poly(1, 1, w - 1, h - 1, 16), smooth=True, fill=self._fill,
                            outline=self._fill, tags="bubble_shape")
        self.tag_lower("bubble_shape")
        self.configure(width=w, height=h)


class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()

    def to_bottom(self):
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)


def styled_entry(parent, font=None, width=None):
    box = tk.Frame(parent, bg=CARD_BG, highlightthickness=2, highlightbackground=EDGE)
    e = tk.Entry(box, relief="flat", bd=0, bg=CARD_BG, fg=INK, insertbackground=INK, font=font or F(11),
                 width=width or 20)
    e.pack(fill="x", padx=10, ipady=7)
    return box, e


# ---------- Outdoors / indoors / to-do picker ----------
def is_daytime():
    d = weather_info.get("day")
    return d if d is not None else 6 <= time.localtime().tm_hour < 18


def pick_activity(where, tag=None):
    note = ""
    if where == "out":
        bad = outdoor_problem()
        if bad:                                   # weather-aware: swap the outdoor quest for an indoor one
            where, tag, note = "in", None, bad
    now = "day" if is_daytime() else "night"
    pool = [a for a in ACTIVITIES if a["where"] == where and a.get("when") in (None, now)]
    if tag and any(a["tag"] == tag for a in pool):
        pool = [a for a in pool if a["tag"] == tag]
    if len(pool) > 1:
        pool = [a for a in pool if a["id"] != last_pick["id"]] or pool     # no immediate repeats
    likes = data["profile"].get("likes", [])
    act = random.choices(pool, weights=[3 if a["tag"] in likes else 1 for a in pool])[0]
    last_pick["id"] = act["id"]
    if note:
        act = dict(act, note=note)
    return act


def todo_quest():
    op = open_tasks()
    if not op:
        return None
    t = op[0]
    return {"id": "todo", "where": "todo", "title": f"Finish your task: {t['text']}", "tag": "todo",
            "color": "#9be7c4", "hint": "", "proof": "debrief", "away": 0, "task": t["text"]}


def start_random(where):
    act = todo_quest() if where == "todo" else pick_activity(where)
    if act:
        start_activity(act)


def where_buttons(parent, on_pick, width=300):
    out_label = "outdoors" if not outdoor_problem() else "outdoors (weather alert)"
    PillButton(parent, out_label, lambda: on_pick("out"), bg=VIOLET, height=52, width=width,
               font=F(14, True)).pack(pady=6)
    PillButton(parent, "indoors", lambda: on_pick("in"), bg=PINK, fg=ON_ACCENT, height=52, width=width,
               font=F(14, True)).pack(pady=6)
    n = len(open_tasks())
    if n:
        PillButton(parent, f"finish my to-do ({n} open)", lambda: on_pick("todo"), bg=MINT, fg=ON_ACCENT, height=52,
                   width=width, font=F(14, True)).pack(pady=6)


# ---------- Windows idle detection ----------
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds():
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0


# ---------- Weather and time ----------
def weather_desc(code):
    if code == 0: return "clear sky"
    if code in (1, 2, 3): return "partly cloudy"
    if code in (45, 48): return "foggy"
    if 51 <= code <= 57: return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82: return "rain"
    if 71 <= code <= 77: return "snow"
    if code >= 95: return "thunderstorm"
    return "unsettled"


def fetch_weather():
    global weather_text
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
               "&current=temperature_2m,weather_code,is_day&timezone=auto")
        with urllib.request.urlopen(url, timeout=8) as r:
            d = json.loads(r.read().decode())["current"]
        weather_text = (f"{d['temperature_2m']:.0f} C, {weather_desc(d['weather_code'])}, "
                        f"{'daytime' if d['is_day'] else 'night'}")
        weather_info.update(desc=weather_desc(d["weather_code"]), day=bool(d["is_day"]),
                            temp=float(d["temperature_2m"]))
    except Exception:
        weather_text = "unknown (no internet)"


def day_part():
    h = time.localtime().tm_hour
    if 5 <= h < 12: return "morning"
    if 12 <= h < 17: return "afternoon"
    if 17 <= h < 23: return "evening"
    return "late night"


def time_context():
    notes = {"morning": "encourage a good start to the day",
             "afternoon": "the day is half done, help them make it count",
             "evening": "there is still some day left, help them make it worth it",
             "late night": "they should not be on screens now; encourage winding down and ask what went "
                           "right and what went wrong today"}
    return f"Local time is {time.strftime('%I:%M %p')} ({day_part()}: {notes[day_part()]})."


def greet_text():
    n = profile_name()
    return {
        "morning": f"good morning, {n}! you're already at the screen, which is fine. take a few slow "
                   "breaths, make a little to-do list, and maybe get some sunlight before the day eats you.",
        "afternoon": f"hey {n}, welcome back. the day is still going, so let's make it count. "
                     "stretch, sunlight, or a stroll? your pick.",
        "evening": f"evening, {n}. we still have part of the day left, so let's make it worth it. "
                   "how about something away from the screen?",
        "late night": f"{n}... it's late. you really shouldn't be on this device right now. tell me what went "
                      "right and what went wrong today, and then wind down, okay?",
    }[day_part()]


# ---------- Pip's memory of you (goes into every prompt) ----------
def habits_text():
    diary = [e for e in data["diary"] if e.get("id") != "reflection"]
    if not diary:
        return "They haven't completed any quests yet."
    counts = {}
    for e in diary:
        counts[e["id"]] = counts.get(e["id"], 0) + 1
    parts = ", ".join(f"{n} x {k}" for k, n in counts.items())
    last = next((e["highlight"] for e in reversed(diary) if e.get("highlight")), "")
    extra = f" The last thing they said they got from a quest: \"{last}\"." if last else ""
    return f"Quests they've completed: {parts}.{extra}"


def likes_text():
    likes = data["profile"].get("likes", [])
    return f"They said they like: {', '.join(likes)}." if likes else ""


def events_text():
    return ("Recent events: " + "; ".join(events[-5:]) + ".") if events else ""


def quest_text():
    if quest is None:
        return "They have no active quest."
    return f"Their active quest: {quest['act']['title']}."


def open_tasks():
    return [t for t in data["todo"] if not t["done"]]


def todo_text():
    op = open_tasks()
    done = [t for t in data["todo"] if t["done"]]
    if not data["todo"]:
        return "They haven't made a to-do list today."
    s = "Their to-do list: still open: " + (", ".join(t["text"] for t in op) or "nothing") + "."
    if done:
        s += " Finished: " + ", ".join(t["text"] for t in done[-3:]) + "."
    return s + " Ask about one open task at a time, and only now and then."


def memory_text():
    mem = data.get("memory", [])[-3:]
    if not mem:
        return ""
    return "Earlier you chatted about: " + " | ".join(f'they said "{m["u"][:80]}", you replied "{m["p"][:80]}"'
                                                       for m in mem) + "."


def quest_calm():
    """True while you are out on a quest you agreed to: Pip stays calm and the screen-time clock waits."""
    return quest is not None and time.time() - quest["started"] < QUEST_CALM


def reset_timers():
    """Screen-time clock back to zero: a real break, a finished quest, or an unlock."""
    global active, grace, grants_used, warned
    active, grace, grants_used, warned = 0, 0, 0, False
    EYE_STATE["timer"] = 0
    close_warning()


def raw_stage():
    if active >= 2 * LEVEL_AT + grace + LOCK_WARN: return 4   # lock
    if active >= 2 * LEVEL_AT + grace: return 3               # fuming + warning
    if active >= LEVEL_AT + grace: return 2                   # nudge: raised hand
    if active >= 0.8 * (LEVEL_AT + grace): return 1           # restless
    return 0


def get_stage():
    """Pip's mood level. While you are out on a quest he is calm (stage 0)."""
    return 0 if quest_calm() else raw_stage()


STAGE_NOTES = {
    0: "calm and happy",
    1: "a bit restless",
    2: ("nudging them with a raised hand: suggest a stroll outside and ask them to bring you a leaf "
        "when they're back"),
    3: "fuming and about to lock their screen unless they go do something",
    4: "locking their screen",
}


def stage_note():
    st = get_stage()
    if st == 2 and outdoor_problem():
        return (f"nudging them with a raised hand: it's not nice outside ({outdoor_problem()}), so suggest an "
                "indoor break like stretching, dancing or making a snack instead of a walk")
    return STAGE_NOTES[st]


# ---------- Voice (Pip only speaks when the user clicked on it) ----------
def _play_neural_voice(text):
    """Use Microsoft's natural neural speech voice through Edge TTS."""
    async def make_audio(path):
        communicate = edge_tts.Communicate(
            text=text,
            voice=NEURAL_VOICE,
            rate=NEURAL_RATE,
            pitch=NEURAL_PITCH,
        )
        await communicate.save(path)

    # A temporary MP3 is used so no audio files are left in the project folder.
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        audio_path = f.name
    try:
        asyncio.run(make_audio(audio_path))
        if playsound is None:
            raise RuntimeError("playsound3 is not installed; use the offline voice fallback")
        playsound(audio_path)
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


def speak(text):
    # The neural voice sounds much more natural. If it is unavailable/offline,
    # fall back to the Windows voice so Pip can still speak.
    with speak_lock:
        if edge_tts is not None and playsound is not None:
            try:
                _play_neural_voice(str(text))
                return
            except Exception as exc:
                print("Pip neural voice unavailable; using offline voice:", exc)
        e = pyttsx3.init()
        try:
            voices = e.getProperty("voices")
            idx = VOICE_INDEX if VOICE_INDEX < len(voices) else 0
            if voices:
                e.setProperty("voice", voices[idx].id)
            e.setProperty("rate", RATE)
            e.setProperty("volume", 1.0)
            e.say(str(text))
            e.runAndWait()
        finally:
            e.stop()


def speak_if_on(text):
    """Legacy helper for one-off lines outside streamed chat replies."""
    if voice_var.get():
        threading.Thread(target=speak, args=(text,), daemon=True).start()


# ---------- Fun facts (true ones, so Gemma never makes one up) ----------
FUN_FACTS = [
    "short breaks while working help people stay focused and feel less tired, so stepping away really does get more done",
    "a stanford study found people came up with more creative ideas while walking than while sitting",
    "the 20-20-20 rule: every 20 minutes, look at something 20 feet away for 20 seconds to rest your eyes",
    "people blink a lot less when staring at screens, which is why eyes get dry and tired",
    "morning sunlight helps set your body clock, which helps you sleep better at night",
    "some penguins give a pebble as a gift to the one they like, so a pebble is a real penguin present",
    "emperor penguins take turns standing on the cold outer edge of the huddle so nobody freezes",
    "a couple of minutes of light movement every half hour is linked to healthier blood sugar after meals",
    "looking at something green for even 40 seconds has been shown to help people focus better afterward",
]

# ---------- Sound effects (synthesized, no files needed) ----------
SFX_NAMES = ("huff", "tsk", "sigh", "gasp", "boing", "hmph")
SFX_RE = re.compile(r"\[(huff|tsk|sigh|gasp|boing|hmph)\]", re.I)
STRAY_SFX = re.compile(r"[\[*(]\s*(huff|tsk|sigh|gasp|boing|hmph)\w*(?:[ ,-]+(?:tsk|huff))*\s*[\]*)]", re.I)
SFX_LABEL = {"huff": "*huff*", "tsk": "*tsk tsk tsk*", "sigh": "*sigh*", "gasp": "*gasp*",
             "boing": "*boing!*", "hmph": "*hmph*"}
SR = 22050
_sfx_cache = {}


def _band_noise(dur, lo, hi):
    n = max(8, int(SR * dur))
    spec = np.fft.rfft(np.random.randn(n))
    f = np.fft.rfftfreq(n, 1.0 / SR)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return x / (np.max(np.abs(x)) + 1e-9)


def _puff(dur, lo, hi, k=0.6, power=1.4):
    """Breathy burst of air that swells and fades (huff, sigh, hmph)."""
    x = _band_noise(dur, lo, hi)
    t = np.linspace(0, 1, len(x))
    return x * np.sin(np.pi * t ** k) ** power


def _make_sfx(name):
    gap = lambda s: np.zeros(int(SR * s))
    if name == "huff":
        x = np.concatenate([_puff(0.32, 400, 3500), gap(0.07), _puff(0.26, 400, 3500) * 0.7])
    elif name == "tsk":
        parts = []
        for i in range(3):
            t = np.arange(int(SR * 0.075)) / SR
            click = _band_noise(0.075, 2500, 9000) * np.minimum(1, t / 0.002) * np.exp(-60 * t)
            thump = np.sin(2 * np.pi * 900 * t) * np.exp(-120 * t) * 0.5
            parts += [(click + thump) * (1 - 0.12 * i), gap(0.12)]
        x = np.concatenate(parts[:-1])
    elif name == "sigh":
        x = _puff(0.95, 300, 2800, k=0.45, power=1.0) * 0.8
    elif name == "gasp":
        n = _band_noise(0.28, 600, 6000)
        env = np.linspace(0, 1, len(n)) ** 1.5
        env[-int(SR * 0.01):] *= np.linspace(1, 0, int(SR * 0.01))
        x = n * env
    elif name == "boing":
        t = np.arange(int(SR * 0.5)) / SR
        f = (180 + 500 * np.exp(-8 * t)) * (1 + 0.25 * np.sin(2 * np.pi * 14 * t))
        x = np.sin(np.cumsum(2 * np.pi * f / SR)) * np.exp(-5 * t)
    else:  # hmph
        p = _puff(0.22, 300, 1800)
        t = np.arange(len(p)) / SR
        x = p * 0.9 + 0.25 * np.sin(2 * np.pi * 150 * t) * np.sin(np.pi * np.linspace(0, 1, len(p)))
    x = x / (np.max(np.abs(x)) + 1e-9) * SFX_VOLUME
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return buf.getvalue(), len(x) / SR


def play_sfx(name):
    if name not in _sfx_cache:
        _sfx_cache[name] = _make_sfx(name)
    wav, dur = _sfx_cache[name]
    if winsound is not None:
        try:
            winsound.PlaySound(wav, winsound.SND_MEMORY)     # blocks until it finishes
            return
        except Exception:
            pass
    time.sleep(dur)


# ---------- Reply parsing ----------
def tidy_reply(reply):
    """Normalize sloppy sound tags ('*huff*', '[tsk tsk]') and cut off a half-finished sentence."""
    reply = STRAY_SFX.sub(lambda m: f"[{m.group(1).lower()}]", reply).strip()
    if reply and reply[-1] not in ".!?]\"'":
        m = re.search(r"^(.*[.!?\]])", reply, re.S)
        if m and len(m.group(1)) > 15:
            reply = m.group(1)
    return reply


def shape_reply(reply, has_fact=False):
    """Keep Pip short and flowing: at most two sentences, and one sound only at the very start."""
    names = SFX_RE.findall(reply)
    text = SFX_RE.sub("", reply)
    text = re.sub(r"\s+", " ", re.sub(r"[\[\]*]", "", text)).strip()
    if not text:
        return reply
    limit = 38 if has_fact else 26
    out, words = [], 0
    for sent in re.split(r"(?<=[.!?])\s+", text)[:3 if has_fact else 2]:
        w = len(sent.split())
        if out and words + w > limit:
            break
        out.append(sent)
        words += w
    text = " ".join(out)
    if len(text.split()) > limit * 1.5:               # one runaway sentence: trim it
        text = " ".join(text.split()[:int(limit * 1.5)]).rstrip(",;:") + "."
    return f"[{names[0].lower()}] {text}" if names else text


def plain_reply(reply):
    """The reply without sound tags (for memory, history checks, and the judge)."""
    return re.sub(r"\s+", " ", SFX_RE.sub("", reply)).strip()


def split_reply(reply):
    segs, pos = [], 0
    for m in SFX_RE.finditer(reply):
        t = re.sub(r"[\[\]*]", "", reply[pos:m.start()]).strip()
        if t:
            segs.append(("text", t))
        segs.append(("sfx", m.group(1).lower()))
        pos = m.end()
    t = re.sub(r"[\[\]*]", "", reply[pos:]).strip()
    if t:
        segs.append(("text", t))
    return segs


def add_auto_sfx(segs, user_text):
    """Pick the sound in code so it always matches the mood of the moment."""
    if any(k == "sfx" for k, _ in segs):
        return segs
    low, st = user_text.lower(), get_stage()
    if ("don't believe" in low or "check failed" in low or "barely left" in low or "only away from" in low
            or "hasn't been long enough" in low):
        name = "tsk"
    elif "grew bigger" in low or time.time() < joy_until:
        name = "boing"
    elif st >= 3:
        name = "tsk"
    elif st == 2:
        name = random.choice(["huff", "tsk"])
    elif st == 1 and random.random() < 0.5:
        name = "huff"
    else:
        return segs
    return [("sfx", name)] + segs


# ---------- Synced speech: text appears word by word exactly as the voice says it ----------
async def _synth(text):
    kw = dict(text=text, voice=NEURAL_VOICE, rate=NEURAL_RATE, pitch=NEURAL_PITCH)
    try:
        comm = edge_tts.Communicate(boundary="WordBoundary", **kw)   # newer edge-tts
    except TypeError:
        comm = edge_tts.Communicate(**kw)                            # older versions send words by default
    audio, words = bytearray(), []
    async for ch in comm.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            words.append((ch["offset"] / 1e7, ch["text"]))           # offset is in 100 ns ticks
    return bytes(audio), words


def _synth_blocking(text):
    return asyncio.run(_synth(re.sub(r"[*_\[\]]", "", text)))


def _offline_say(text):
    e = pyttsx3.init()
    try:
        voices = e.getProperty("voices")
        if voices:
            e.setProperty("voice", voices[VOICE_INDEX if VOICE_INDEX < len(voices) else 0].id)
        e.setProperty("rate", RATE)
        e.say(str(text))
        e.runAndWait()
    finally:
        e.stop()


def token_times(tokens, words, per_word):
    n = len(tokens)
    if words:
        m = len(words)
        return [words[min(m - 1, int(j * m / n))][0] for j in range(n)]
    return [j * per_word for j in range(n)]


def play_reply(segs, voice_on):
    """Runs in a worker thread. Plays sound effects and speech in order while the chat text appears in sync."""
    neural = voice_on and edge_tts is not None and playsound is not None
    pool = ThreadPoolExecutor(max_workers=3) if neural else None
    futs = {}
    if neural:                      # start making ALL the audio right away, while earlier parts play
        for i, (kind, val) in enumerate(segs):
            if kind == "text":
                futs[i] = pool.submit(_synth_blocking, val)
    shown = ""
    try:
        with speak_lock:
            for i, (kind, val) in enumerate(segs):
                if kind == "sfx":
                    shown = (shown + " " + SFX_LABEL[val]).strip()
                    ui_call(lambda s=shown: chat_stream_set(s))
                    if voice_on:
                        play_sfx(val)
                    else:
                        time.sleep(0.2)
                    continue
                tokens = val.split()
                if not tokens:
                    continue
                audio, words = None, []
                if i in futs:
                    try:
                        audio, words = futs[i].result(timeout=25)
                        if not audio:
                            audio = None
                    except Exception as exc:
                        print("Pip neural voice failed, using offline voice:", exc)
                per_word = 0.26 if audio else ((60.0 / RATE) if voice_on else TYPE_SPEED)
                times_ = token_times(tokens, words if audio else [], per_word)
                prefix = shown
                for j, tm in enumerate(times_):       # schedule every word at its spoken moment
                    partial = (prefix + " " + " ".join(tokens[:j + 1])).strip()
                    delay = int((tm + (TEXT_DELAY if audio else 0)) * 1000) + 1
                    ui_call(lambda s=partial: chat_stream_set(s), delay)
                if audio:
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                        f.write(audio)
                        path = f.name
                    try:
                        playsound(path)
                    finally:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                elif voice_on:
                    _offline_say(val)
                else:
                    time.sleep(times_[-1] + 0.3)
                shown = (prefix + " " + " ".join(tokens)).strip()
                ui_call(lambda s=shown: chat_stream_set(s))
    finally:
        if pool:
            pool.shutdown(wait=False)


def warm_up():
    """Load the model into memory in the background so the first reply isn't slow."""
    try:
        ollama.chat(model=GEMMA, messages=[{"role": "user", "content": "hi"}],
                    options={"num_predict": 1}, keep_alive="30m")
    except Exception:
        pass


def build_system(fact="", full=False):
    mins = round(active / LEVEL_AT * 30)
    if fact:
        fact_rule = ("FUN FACT MODE: react in a few words, then say this true fact casually in under 14 words, "
                     f"starting with 'fun fact,'. The fact: {fact}. Put nothing after the fact, no question.\n")
    else:
        fact_rule = ""
    late = " they should be winding down for bed." if day_part() == "late night" else ""
    s = (
        f"You are {NAME}, {PERSONA}\n"
        f"You are chatting with {profile_name()}, your human. You adore them and want them off the screen, moving "
        "and happy.\n"
        "HOW YOU WRITE: like a friend texting. lowercase, warm, playful, plain words. ONE or TWO short sentences, "
        "10 to 25 words in total, at most one question and only at the very end. Never a lecture, never a list, "
        "never mean.\n"
        "RULES:\n"
        "1. First react to the exact thing they just said, or to the situation you are given, using its real "
        "details (names, activities, numbers). Then nudge or ask one thing.\n"
        "2. If they agree or say yes, cheer them on. Never scold someone who agreed.\n"
        "3. If they ask a question, answer it first.\n"
        "4. Be concrete. Never send vague filler like 'let's go already' or 'you're amazing' on its own.\n"
        "5. Never write sound words, asterisk actions, emojis or a name label. Never repeat an earlier message.\n"
        "6. Lines that start with SITUATION are private notes: act on them, never quote them.\n"
        + fact_rule +
        f"NOW: it is {time.strftime('%I:%M %p')} ({day_part()}).{late} Your mood: {stage_note()}. "
        f"You are level {quests_done + 1}. {quest_text()} They have been at the computer for about {mins} minutes. "
        f"Weather in {PLACE}: {weather_text}."
    )
    if full:                       # greetings only: the personal background
        s += f" {habits_text()} {likes_text()} {todo_text()} {events_text()}"
    return s


# =====================================================================
# v8 additions: verified time-away, stats dashboard, stronger proof, weather-aware quests,
# eye/blink/posture reminders, unlockable cosmetics
# =====================================================================

# ---------- Daily stats and streaks ----------
def today_key():
    return time.strftime("%Y-%m-%d")


def day_stats(key=None):
    key = key or today_key()
    d = data["stats"].setdefault(key, {})
    for k in ("screen", "away", "quests", "breaks", "blink_n", "face_s", "posture", "eye_rests"):
        d.setdefault(k, 0)
    return d


def prune_stats(keep=60):
    for k in sorted(data["stats"])[:-keep]:
        data["stats"].pop(k, None)


def streaks():
    """(current, best): consecutive days with at least one finished quest."""
    days = set()
    for k, v in data["stats"].items():
        if v.get("quests", 0) > 0:
            try:
                days.add(datetime.date.fromisoformat(k))
            except ValueError:
                pass
    if not days:
        return 0, 0
    best = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    d = datetime.date.today()
    if d not in days:
        d -= datetime.timedelta(days=1)
    cur = 0
    while d in days:
        cur += 1
        d -= datetime.timedelta(days=1)
    return cur, best


def fmt_dur(sec):
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    h, m = divmod(sec // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


# ---------- Camera presence state (filled by presence_loop, read by tick) ----------
presence = {"pause": False, "has_cam": False, "t_ok": 0.0, "face": False, "last_seen": 0.0,
            "ever_seen": False, "face_since": 0.0, "blinks": 0, "blink_rate": None,
            "posture_flag": "", "recalibrate": False, "stop": False,
            "cam_since": 0.0, "blind": False, "preview": None, "want_preview": False}
cam_state = {"on": bool(data.get("cam_monitor", True)) and CAM_MONITOR}
on_break = {"on": False, "len": 0}
blink_seen = [0]
EYE_STATE = {"timer": 0}


def cam_live():
    """True when the background camera has delivered a frame in the last few seconds."""
    return cam_state["on"] and time.time() - presence["t_ok"] < 6


def effective_away(idle):
    """Seconds you have REALLY been away from the screen.
    When the camera works it has the final say: a face in view means you are NOT away, even if you have not
    touched the keyboard. Away time only counts while the camera sees nobody AND there is no keyboard/mouse input."""
    if cam_live():
        since = max(presence["last_seen"], presence["cam_since"])
        return min(idle, time.time() - since)
    return idle


def away_mode():
    if not cam_state["on"]:
        return "camera off, keyboard only"
    if not cam_live():
        return "camera offline, keyboard only"
    if presence["blind"]:
        return "camera can't see your face, keyboard only"
    if presence["face"]:
        return "camera sees you"
    return "camera: nobody in view"


def toggle_cam():
    cam_state["on"] = bool(cam_var.get())
    data["cam_monitor"] = cam_state["on"]
    save_data()


def motion_presence_loop():
    """Fallback for when OpenCV has no face models: you count as 'there' while the camera sees movement."""
    cam, prev = None, None
    presence["error"] = "no face model"
    while not presence["stop"]:
        try:
            if not cam_state["on"] or presence["pause"]:
                if cam is not None:
                    cam.release()
                    cam = None
                    presence["has_cam"] = False
                presence["t_ok"] = 0.0
                presence["cam_since"] = 0.0
                prev = None
                time.sleep(0.4)
                continue
            if cam is None:
                cam = open_camera()
                if cam is None:
                    time.sleep(6)
                    continue
                presence["has_cam"] = True
            ok, frame = cam.read()
            if not ok:
                cam.release()
                cam = None
                presence["has_cam"] = False
                presence["cam_since"] = 0.0
                time.sleep(3)
                continue
            now = time.time()
            presence["t_ok"] = now
            if not presence["cam_since"]:
                presence["cam_since"] = now
            g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY), (9, 9), 0)
            if prev is not None:
                if float((cv2.absdiff(g, prev) > 18).mean()) > 0.01:      # more than 1% of the picture changed
                    presence["face"] = True
                    presence["last_seen"] = now
                    presence["ever_seen"] = True
                else:
                    presence["face"] = False
            prev = g
            time.sleep(0.25)
        except Exception as exc:
            print("Pip motion monitor error:", exc)
            time.sleep(1.0)


def presence_loop():
    """Background camera watcher: is a face in view (away check), rough blink rate, and posture.
    Frames are analysed in memory and never saved or sent anywhere."""
    try:
        face_cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        eye_cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
        alt_cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
        if alt_cc.empty():
            alt_cc = None
        if face_cc.empty() or eye_cc.empty():
            raise RuntimeError("OpenCV face/eye models not found")
    except Exception as exc:
        print("Pip camera monitor unavailable, using movement detection instead:", exc)
        motion_presence_loop()
        return
    cam = None

    def find_faces(gray):
        """Front-facing faces first; if none are found, try a second, differently trained model."""
        f = face_cc.detectMultiScale(gray, 1.15, 5, minSize=(36, 36))
        if len(f) == 0 and alt_cc is not None:
            f = alt_cc.detectMultiScale(gray, 1.15, 5, minSize=(36, 36))
        return f

    eyes_log, blink_log = deque(), deque()
    open_streak = closed_run = hits = 0
    base, samples, bad_since = None, [], None
    while not presence["stop"]:
        try:
            if not cam_state["on"] or presence["pause"]:
                if cam is not None:                      # let go of the camera (the proof window may need it)
                    cam.release()
                    cam = None
                    presence["has_cam"] = False
                presence["t_ok"] = 0.0
                presence["cam_since"] = 0.0
                time.sleep(0.4)
                continue
            if cam is None:
                cam = open_camera()
                if cam is None:
                    time.sleep(6)
                    continue
                presence["has_cam"] = True
            ok, frame = cam.read()
            if not ok:
                cam.release()
                cam = None
                presence["has_cam"] = False
                presence["cam_since"] = 0.0
                time.sleep(3)
                continue
            now = time.time()
            presence["t_ok"] = now
            if not presence["cam_since"]:
                presence["cam_since"] = now
            h0, w0 = frame.shape[:2]
            small = cv2.resize(frame, (480, max(1, int(h0 * 480.0 / w0))))
            gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
            faces = find_faces(gray)
            if presence["want_preview"]:                 # only used by the "Camera check" window
                vis = small.copy()
                for (fx_, fy_, fw_, fh_) in faces:
                    cv2.rectangle(vis, (int(fx_), int(fy_)), (int(fx_ + fw_), int(fy_ + fh_)), (90, 220, 120), 2)
                presence["preview"] = vis
            hits = hits + 1 if len(faces) else 0
            if len(faces) and hits < 2:                  # a face must appear twice in a row: ignores one-frame ghosts
                time.sleep(0.15)
                continue
            if len(faces) == 0:
                presence["face"] = False
                gone = now - presence["last_seen"]
                if gone > 5:
                    presence["face_since"] = 0.0
                    presence["blink_rate"] = None
                    eyes_log.clear()
                    blink_log.clear()
                    open_streak = closed_run = 0
                if gone > 60:                            # you left for a while: re-learn your sitting posture
                    base, samples, bad_since = None, [], None
                    presence["posture_flag"] = ""
                time.sleep(1.0)
                continue
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            presence["face"] = True
            presence["last_seen"] = now
            presence["ever_seen"] = True
            if not presence["face_since"]:
                presence["face_since"] = now

            # --- blinks: eyes found in the upper face = open, not found = closed (a rough estimate) ---
            roi = gray[y:y + int(h * 0.6), x:x + w]
            m = max(8, int(w * 0.14))
            eyes = eye_cc.detectMultiScale(roi, 1.1, 6, minSize=(m, m))
            eyes_open = len(eyes) >= 1
            eyes_log.append((now, eyes_open))
            while eyes_log and now - eyes_log[0][0] > BLINK_WINDOW:
                eyes_log.popleft()
            if eyes_open:
                if 1 <= closed_run <= 3 and open_streak >= 2:
                    blink_log.append(now)
                    presence["blinks"] += 1
                open_streak += 1
                closed_run = 0
            else:
                closed_run += 1
                if closed_run > 3:
                    open_streak = 0
            while blink_log and now - blink_log[0] > BLINK_WINDOW:
                blink_log.popleft()
            seen_ratio = (sum(1 for _, o in eyes_log if o) / len(eyes_log)) if eyes_log else 0
            if now - presence["face_since"] >= BLINK_WINDOW and len(eyes_log) >= 20 and seen_ratio >= 0.6:
                presence["blink_rate"] = len(blink_log) * 60.0 / BLINK_WINDOW
            else:
                presence["blink_rate"] = None            # not enough reliable data to judge

            # --- posture: face size (leaning in) and face height (head drooping) vs your own baseline ---
            cy = y + h / 2.0
            if presence["recalibrate"]:
                base, samples, bad_since = None, [], None
                presence["recalibrate"] = False
            if base is None:
                samples.append((float(w), cy))
                if len(samples) >= 25:
                    base = (statistics.median([s[0] for s in samples]), statistics.median([s[1] for s in samples]))
            else:
                reason = ""
                if w > base[0] * 1.28:
                    reason = "you're leaning really close to the screen. sit back a little."
                elif cy > base[1] + base[0] * 0.45:
                    reason = "your head is drooping toward the desk. sit up tall and relax your shoulders."
                if reason:
                    bad_since = bad_since or now
                    if now - bad_since >= POSTURE_AFTER:
                        presence["posture_flag"] = reason
                else:
                    bad_since = None
                    presence["posture_flag"] = ""
            time.sleep(0.12)
        except Exception as exc:
            print("Pip camera monitor error:", exc)
            time.sleep(1.0)


# ---------- Speech-bubble toasts and reminders (eye rest, blink, posture) ----------
toast = {"win": None, "bubble": None}
last_remind = {}


def close_toast():
    if alive(toast["win"]):
        toast["win"].destroy()
    toast["win"] = toast["bubble"] = None


def _toast_voice(text, sfx):
    try:
        if sfx:
            play_sfx(sfx)
        speak(text)
    except Exception as exc:
        print("Pip toast voice error:", exc)


def pip_toast(text, ttl=9, sfx=None, say=True):
    """A small speech bubble next to Pip. It never opens the chat window or steals keyboard focus."""
    close_toast()
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.attributes("-transparentcolor", KEY)
    win.configure(bg=KEY)
    b = Bubble(win, text, BUB_PIP, INK, maxw=250)
    b.pack(padx=4, pady=4)
    win.update_idletasks()
    tw, th = win.winfo_reqwidth(), win.winfo_reqheight()
    s = min(0.9, 0.42 + 0.06 * quests_done)
    head_y = pet.winfo_y() + H - FOOT - 236 * s
    x = int(max(8, min(win.winfo_screenwidth() - tw - 8, pet.winfo_x() + W - tw)))
    y = int(max(8, head_y - th))
    win.geometry(f"+{x}+{y}")
    b.bind("<Button-1>", lambda e: close_toast())
    toast["win"], toast["bubble"] = win, b
    if ttl:
        win.after(int(ttl * 1000), lambda w=win: close_toast() if toast["win"] is w else None)
    if say and voice_var.get():
        threading.Thread(target=_toast_voice, args=(text, sfx), daemon=True).start()
    return b


def can_remind(kind):
    now = time.time()
    if locked or quest is not None or busy["on"] or get_stage() >= 3:
        return False
    return now - last_remind.get(kind, 0) >= REMIND_GAP and now - last_remind.get("any", 0) >= ANY_GAP


def mark_remind(kind):
    last_remind[kind] = last_remind["any"] = time.time()


def eye_rest():
    """20-20-20: every 20 minutes of screen time, look 20 feet away for 20 seconds (with a countdown)."""
    mark_remind("eye")
    b = pip_toast("20-20-20 time! look at something 20 feet away for 20 seconds.", ttl=0, sfx="boing")

    def step(n):
        if toast["bubble"] is not b or not alive(toast["win"]):
            return                                        # dismissed or replaced
        if n <= 0:
            day_stats()["eye_rests"] += 1
            b.set("nice, that's one rested pair of eyes.")
            toast["win"].after(2500, lambda: close_toast() if toast["bubble"] is b else None)
            return
        b.set(f"look far away... {n}s")
        toast["win"].after(1000, lambda: step(n - 1))
    toast["win"].after(3500, lambda: step(20))


def blink_reminder(rate):
    mark_remind("blink")
    pip_toast(f"bestie, you're blinking only about {rate:.0f} times a minute. blink slowly ten times and "
              "look away for a sec.", sfx="gasp")


def posture_reminder(reason):
    mark_remind("posture")
    day_stats()["posture"] += 1
    pip_toast(reason, sfx="tsk")


def check_reminders(dt=1.0):
    """Called once a second while you are actively at the screen."""
    EYE_STATE["timer"] += dt
    if EYE_STATE["timer"] >= EYE_REST_EVERY and can_remind("eye"):
        EYE_STATE["timer"] = 0
        eye_rest()
        return
    flag = presence["posture_flag"]
    if flag and can_remind("posture"):
        presence["posture_flag"] = ""
        posture_reminder(flag)
        return
    rate = presence["blink_rate"]
    if rate is not None and rate < BLINK_LOW and can_remind("blink"):
        blink_reminder(rate)


# ---------- Weather-aware quests ----------
def outdoor_problem():
    """Why outdoors is a bad idea right now, or '' if it is fine."""
    if not WEATHER_AWARE or not weather_info:
        return ""
    desc, t = weather_info.get("desc", ""), weather_info.get("temp")
    if desc in ("rain", "drizzle", "thunderstorm", "snow"):
        return f"it's {desc} outside"
    if t is not None and t >= MAX_HOT:
        return f"it's {t:.0f} C outside, way too hot"
    if t is not None and t <= MIN_COLD:
        return f"it's freezing out there ({t:.0f} C)"
    return ""


# ---------- Stronger proof: outdoor photos can't be reused ----------
def ahash(frame):
    g = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (8, 8))
    avg = g.mean()
    return "".join("1" if v > avg else "0" for v in g.flatten())


def is_duplicate_photo(frame):
    h = ahash(frame)
    for old in data.get("photo_hashes", [])[-30:]:
        if sum(a != b for a, b in zip(h, old)) <= 4:
            return True
    return False


def remember_photo(frame):
    data.setdefault("photo_hashes", []).append(ahash(frame))
    data["photo_hashes"] = data["photo_hashes"][-30:]
    save_data()


# ---------- Unlockable cosmetics ----------
COSMETICS = [
    {"id": "scarf", "slot": "neck", "name": "cozy scarf", "level": 3},
    {"id": "partyhat", "slot": "head", "name": "party hat", "level": 5},
    {"id": "cape", "slot": "back", "name": "hero cape", "level": 8},
    {"id": "crown", "slot": "head", "name": "golden crown", "level": 10},
]
wardrobe_win = None


def pip_level():
    return quests_done + 1


def worn(slot):
    """The id of the accessory Pip is wearing in this slot ('' if none or not unlocked yet)."""
    it = data["wardrobe"].get(slot, "")
    c = next((x for x in COSMETICS if x["id"] == it), None)
    return it if c and c["level"] <= pip_level() else ""


def grant_unlocks():
    """Auto-wear accessories that the current level unlocks. Returns the newly unlocked ones."""
    seen = data.setdefault("cosmetics_seen", [])
    new = []
    for it in COSMETICS:
        if it["level"] <= pip_level() and it["id"] not in seen:
            seen.append(it["id"])
            data["wardrobe"][it["slot"]] = it["id"]
            new.append(it)
    if new:
        save_data()
    return new


def open_wardrobe():
    global wardrobe_win
    if alive(wardrobe_win):
        wardrobe_win.lift()
        return
    wardrobe_win = win = tk.Toplevel(root)
    win.title("pip's wardrobe")
    win.geometry("440x740+540+20")
    win.configure(bg=BG)
    tk.Label(win, text="wardrobe", font=F(22, True), bg=BG, fg=INK).pack(pady=(16, 0))
    tk.Label(win, text="pip unlocks new things as it levels up", font=F(10), bg=BG, fg=MUTED).pack()
    make_avatar(win, 230, lambda: "happy", BG, halo=HALO).pack(pady=6)
    lv = tk.Label(win, text="", font=F(10, True), bg=BG, fg=VIOLET)
    lv.pack()
    body = tk.Frame(win, bg=BG)
    body.pack(fill="both", expand=True, padx=16, pady=8)

    def toggle(it):
        cur = data["wardrobe"].get(it["slot"], "")
        data["wardrobe"][it["slot"]] = "" if cur == it["id"] else it["id"]
        save_data()
        build()

    def build():
        for w in body.winfo_children():
            w.destroy()
        lv.config(text=f"level {pip_level()}")
        for it in COSMETICS:
            row = tk.Frame(body, bg=CARD_BG, highlightthickness=1, highlightbackground=EDGE)
            row.pack(fill="x", pady=4)
            ok = it["level"] <= pip_level()
            on = data["wardrobe"].get(it["slot"], "") == it["id"]
            tk.Label(row, text=it["name"], font=F(11, True), bg=CARD_BG, fg=INK if ok else MUTED).pack(
                side="left", padx=12, pady=10)
            if ok:
                PillButton(row, "wearing" if on else "wear", lambda i=it: toggle(i),
                           bg=VIOLET if on else LILAC, fg="white" if on else VIOLET, height=30, pad=14,
                           font=F(9, True)).pack(side="right", padx=10)
            else:
                tk.Label(row, text=f"unlocks at level {it['level']}", font=F(9), bg=CARD_BG, fg=MUTED).pack(
                    side="right", padx=12)
    build()


# ---------- Stats dashboard ----------
stats_win = None


def draw_week_chart(parent):
    days = [datetime.date.today() - datetime.timedelta(days=i) for i in range(6, -1, -1)]
    rows = []
    for d in days:
        s = data["stats"].get(d.isoformat(), {})
        rows.append((d.strftime("%a").lower(), s.get("screen", 0) / 60.0, s.get("away", 0) / 60.0))
    cw, ch = 460, 230
    cv = tk.Canvas(parent, width=cw, height=ch, bg=CARD_BG, highlightthickness=1, highlightbackground=EDGE)
    top = max(1.0, max(max(r[1], r[2]) for r in rows))
    x0, ybase, ytop = 20, ch - 28, 44
    slot = (cw - 2 * x0) / 7.0
    cv.create_text(14, 14, text="screen vs away, last 7 days", anchor="w", font=F(10, True), fill=INK)
    cv.create_rectangle(cw - 150, 8, cw - 140, 18, fill=VIOLET, outline="")
    cv.create_text(cw - 136, 13, text="screen", anchor="w", font=F(8), fill=MUTED)
    cv.create_rectangle(cw - 84, 8, cw - 74, 18, fill="#5ccf9b", outline="")
    cv.create_text(cw - 70, 13, text="away", anchor="w", font=F(8), fill=MUTED)
    cv.create_line(x0, ybase, cw - x0, ybase, fill=EDGE)
    for i, (lab, sc, aw) in enumerate(rows):
        bx = x0 + i * slot + slot / 2
        for off, val, col in ((-12, sc, VIOLET), (12, aw, "#5ccf9b")):
            hgt = (val / top) * (ybase - ytop)
            xa = bx + off
            if val > 0:
                cv.create_rectangle(xa - 10, ybase - hgt, xa + 10, ybase, fill=col, outline="")
                cv.create_text(xa, ybase - hgt - 7, text=fmt_dur(val * 60), font=F(7), fill=MUTED)
        cv.create_text(bx, ybase + 13, text=lab, font=F(9), fill=INK if i == 6 else MUTED)
    return cv, rows


def build_stats(body):
    st = day_stats()
    cur, best = streaks()
    tracked = st["screen"] + st["away"]
    pct = int(100 * st["away"] / tracked) if tracked else 0
    rate = (st["blink_n"] * 60.0 / st["face_s"]) if st["face_s"] >= 120 else None
    cards = [("screen today", fmt_dur(st["screen"])), ("away today", fmt_dur(st["away"])),
             ("away share", f"{pct}%"), ("quests today", str(st["quests"])),
             ("streak", f"{cur} day{'s' if cur != 1 else ''}"), ("best streak", f"{best}"),
             ("breaks taken", str(st["breaks"])), ("blinks / min (est.)", f"{rate:.0f}" if rate else "-"),
             ("eye rests", str(st["eye_rests"])), ("posture nudges", str(st["posture"])),
             ("pip level", str(pip_level())), ("quests total", str(quests_done))]
    grid = tk.Frame(body, bg=BG)
    grid.pack(fill="x", padx=16, pady=(4, 8))
    for i, (lab, val) in enumerate(cards):
        card = tk.Frame(grid, bg=CARD_BG, highlightthickness=1, highlightbackground=EDGE)
        card.grid(row=i // 3, column=i % 3, padx=4, pady=4, sticky="nsew")
        tk.Label(card, text=val, font=F(17, True), bg=CARD_BG, fg=VIOLET).pack(padx=10, pady=(8, 0))
        tk.Label(card, text=lab, font=F(8), bg=CARD_BG, fg=MUTED).pack(padx=10, pady=(0, 8))
    for col in range(3):
        grid.columnconfigure(col, weight=1, uniform="stat")
    cv, rows = draw_week_chart(body)
    cv.pack(padx=16, pady=4)
    tot_s, tot_a = sum(r[1] for r in rows), sum(r[2] for r in rows)
    tk.Label(body, text=f"this week: {fmt_dur(tot_s * 60)} on screen, {fmt_dur(tot_a * 60)} away",
             font=F(10, True), bg=BG, fg=INK).pack(pady=(6, 0))
    tk.Label(body, text="everything here is measured and stored on this pc only.", font=F(9), bg=BG,
             fg=MUTED).pack()


def open_stats():
    global stats_win
    if alive(stats_win):
        stats_win.lift()
        return
    stats_win = win = tk.Toplevel(root)
    win.title("pip's stats")
    win.geometry("500x760+500+10")
    win.configure(bg=BG)
    tk.Label(win, text="your week", font=F(22, True), bg=BG, fg=INK).pack(pady=(16, 0))
    tk.Label(win, text="screen time vs time away from it", font=F(10), bg=BG, fg=MUTED).pack(pady=(0, 6))
    body = tk.Frame(win, bg=BG)
    body.pack(fill="both", expand=True)

    def render():
        if not alive(win):
            return
        for w in body.winfo_children():
            w.destroy()
        build_stats(body)
        win.after(10000, render)
    render()


def quit_app():
    presence["stop"] = True
    save_data()
    root.destroy()


# ---------- Chat: one pipeline for every Pip line (also mirrors into the lock screen) ----------
def chat_add(who, text):
    """Add a message to the chat. Pip's bubbles are lilac on the left, yours are pink on the right."""
    if not alive(chat_view):
        return None
    row = tk.Frame(chat_view.inner, bg=CHAT_BG)
    row.pack(fill="x", padx=10, pady=4)
    if who == "Pip":
        b = Bubble(row, text, BUB_PIP, INK)
        b.pack(side="left")
    elif who == "You":
        b = Bubble(row, text, BUB_YOU, ON_ACCENT)
        b.pack(side="right")
    else:
        b = tk.Label(row, text=text, bg=CHAT_BG, fg=MUTED, font=F(9), wraplength=380, justify="center")
        b.pack()
    chat_view.to_bottom()
    return b


def chat_stream_begin():
    global cur_bubble
    stream_text[0] = ""
    cur_bubble = chat_add(NAME, "")


def chat_stream_add(piece):
    stream_text[0] += piece
    if locked and alive(lock_msg):
        lock_msg.config(text=stream_text[0])
    if isinstance(cur_bubble, Bubble) and alive(cur_bubble):
        cur_bubble.set(stream_text[0])
        chat_view.to_bottom()


def chat_stream_set(full):
    stream_text[0] = full
    if locked and alive(lock_msg):
        lock_msg.config(text=full)
    if isinstance(cur_bubble, Bubble) and alive(cur_bubble):
        cur_bubble.set(full)
        chat_view.to_bottom()


def chat_stream_end():
    if isinstance(cur_bubble, Bubble) and alive(cur_bubble):
        cur_bubble.set(stream_text[0].strip())
        chat_view.to_bottom()


def chat_append(who, text):
    if locked and alive(lock_msg) and who in ("System", "You"):
        lock_msg.config(text=text if who == "System" else f"you: {text}")
    chat_add(NAME if who == NAME else who, text)


def set_status(text):
    try:
        (lock_status if locked and alive(lock_status) else status_label).config(text=text)
    except Exception:
        pass


def set_mic(text, state):
    for b in (mic_button, lock_mic):
        try:
            b.config(text=text, state=state)
        except Exception:
            pass


STOCK_LINES = ("glued to that screen forever", "officially bigger now, so proud", "right here when you're back",
               "oh no, a deadline", "touch some grass?")
AGREE_RE = re.compile(r"\b(yes|yeah|yep|yup|sure|ok|okay|alright|lets|let's|i'll go|ill go|going|on my way|"
                      r"sounds good|will do|do it)\b", re.I)
FEEL_RE = re.compile(r"\b(tired|sad|stress|stressed|anxious|bored|exhausted|sick|lonely|angry|upset|happy|excited|"
                     r"proud|worried|sleepy|overwhelmed)\b", re.I)
GREET_RE = re.compile(r"^\W*(hi|hey|hello|yo|hii+|sup|good (morning|evening|afternoon))\b", re.I)


def is_parrot(reply):
    """True when the model just echoed a line from its own instructions."""
    t = reply.lower()
    return any(s in t for s in STOCK_LINES)


def strip_model_sfx(reply):
    """The code picks the sound effect (the small model picked them at random), so drop any the model wrote."""
    reply = SFX_RE.sub("", STRAY_SFX.sub("", reply))
    reply = re.sub(r"\*[^*\n]{1,30}\*", "", reply)
    reply = re.sub(r"^\s*pip\s*:\s*", "", reply, flags=re.I)
    return re.sub(r"\s+", " ", reply).strip().strip('"')


def intent_hint(text):
    low = text.lower()
    if any(w in low for w in GRANT_WORDS) and NO_WORDS.search(text):
        return ("They are busy or want more time. React to their actual reason, be understanding, "
                "and ask once when they will be free.")
    if AGREE_RE.search(text) and not NO_WORDS.search(text):
        return ("They just AGREED. Cheer them on and react to the specific thing they said (like what they will "
                "bring or do). Do NOT scold them.")
    if "?" in text or re.match(r"\s*(what|why|how|who|where|when|can|could|do|does|are|is|should)\b", low):
        return "They asked a question: answer it directly in your first sentence, then add one small nudge."
    if GREET_RE.search(text):
        return "They are greeting you: greet them back warmly by name, then ask one specific thing."
    if FEEL_RE.search(text):
        return "They shared a feeling: react to that feeling kindly first, then gently suggest one small thing."
    return "React to the specific thing they said before you nudge them."


def final_prompt(user_text, use_fact=False):
    """The last message the model sees: the situation or the user's words, plus what a good reply looks like."""
    size = "up to 35 words" if use_fact else "10 to 25 words"
    if user_text.startswith("(stage direction"):
        body = user_text.strip()
        if body.startswith("(") and body.endswith(")"):
            body = body[1:-1]
        body = body.replace("stage direction:", "", 1).strip()
        return (f"SITUATION: {body}\nWrite Pip's next message now: one or two short sentences, {size}, specific to "
                "this situation and using its real details. No sound words, no emojis.")
    return (f"{user_text}\n\n(Reply as Pip to exactly that. {intent_hint(user_text)} One or two short sentences, "
            f"{size}, specific to what they said. No sound words, no emojis.)")


def pip_reply(user_text, grantable=False, fact=False):
    """One reply from Pip. The text appears in sync with the voice and sound effects."""
    if busy["on"]:
        return
    if not locked:
        ensure_chat()
    busy["on"] = True
    voice_on = bool(voice_var.get())
    set_status("pip is thinking...")
    history.append({"role": "user", "content": user_text})
    use_fact = fact or (get_stage() >= 1 and not user_text.startswith("(stage") and random.random() < 0.4)
    msgs = ([{"role": "system", "content": build_system(random.choice(FUN_FACTS) if use_fact else "",
                                                        "just clicked on you" in user_text)}]
            + history[-9:-1] + [{"role": "user", "content": final_prompt(user_text, bool(use_fact))}])

    def work():
        try:
            r = ollama.chat(model=GEMMA, messages=msgs, keep_alive="30m",
                            options={"temperature": 0.8, "num_predict": 90})
            reply = r["message"]["content"]
            if is_parrot(reply):          # the 4B model sometimes echoes its own examples: re-roll once
                r = ollama.chat(model=GEMMA, keep_alive="30m", options={"temperature": 1.0, "num_predict": 90},
                                messages=msgs + [{"role": "user", "content": "(stage direction: that reply was a stock "
                                                  "phrase. Say it again in completely fresh words that fit exactly "
                                                  "what just happened.)"}])
                reply = r["message"]["content"]
        except Exception as exc:
            print("Pip reply error:", exc)
            reply = "[sigh] my brain buffered. try again."
        reply = shape_reply(tidy_reply(strip_model_sfx(reply)), bool(use_fact))
        segs = add_auto_sfx(split_reply(reply), user_text)
        ui_call(chat_stream_begin)
        try:
            play_reply(segs, voice_on)
        except Exception as exc:
            print("Pip playback error:", exc)
            ui_call(lambda: chat_stream_set(plain_reply(reply)))
        ui_call(lambda: finish_reply(reply, user_text, grantable))
    threading.Thread(target=work, daemon=True).start()


def finish_reply(reply, user_text, grantable):
    chat_stream_end()
    clean = plain_reply(reply)
    history.append({"role": "assistant", "content": reply})
    busy["on"] = False
    set_status("")
    if pending["kind"] == "debrief" and user_text.startswith("(stage direction"):
        pending["question"] = clean          # remember what Pip asked, so the judge can check the answer against it
    if not user_text.startswith("(stage direction"):
        data["memory"].append({"u": user_text[:120], "p": clean[:140]})
        data["memory"] = data["memory"][-8:]
        save_data()
    if grantable and any(w in user_text.lower() for w in GRANT_WORDS):
        threading.Thread(target=check_grant, args=(user_text, clean), daemon=True).start()


def check_grant(user_text, reply):
    """A small separate call decides whether Pip actually agreed to wait (limits enforced in code)."""
    grant = 0
    try:
        prompt = (f'A penguin pet asked its owner to take a break from the computer. The owner said: "{user_text}". '
                  f'The pet replied: "{reply}". Did the pet agree to wait? If the owner gave a believable reason '
                  '(meeting, call, deadline) and the pet agreed, answer with the number of minutes the owner asked '
                  'for (1 to 30). If the pet refused, or the reason was weak, answer 0. '
                  'Reply ONLY with JSON: {"grant_minutes": <number>}')
        r = ollama.chat(model=GEMMA, messages=[{"role": "user", "content": prompt}], format="json",
                        options={"temperature": 0, "num_predict": 30})
        grant = max(0, int(float(json.loads(r["message"]["content"]).get("grant_minutes", 0) or 0)))
    except Exception:
        grant = 0
    ui_call(lambda: apply_grant(grant))


def apply_grant(grant):
    global grace, grants_used
    if grant <= 0:
        return
    if grants_used >= MAX_GRANTS:
        chat_append("System", "[no more extra time this stretch]")
        return
    grant = min(grant, MAX_GRANT_MIN)
    grace += grant * MIN_UNIT
    grants_used += 1
    events.append(f"you agreed to give them {grant} more minutes")
    chat_append("System", f"[+{grant} min granted. Pip will leave you alone until then]")


NO_WORDS = re.compile(r"\b(no|nope|not|never|later|busy|can'?t|cannot|don'?t|dont|wait|minutes?|meeting|"
                      r"tomorrow|after)\b", re.I)
YES_WORDS = re.compile(r"\b(yes|yeah|yep|yup|yea|sure|ok|okay|alright|fine|ready|lets|let's|do it|going|go)\b", re.I)
DO_WORDS = re.compile(r"walk|stroll|outside|outdoors|grass|go out|fresh air", re.I)
INVITE_WORDS = re.compile(r"walk|stroll|outside|outdoors|grass|activity|quest|touch|go for|step out|sun\b|"
                          r"fresh air|pick|moving|get up|let'?s go|go out|break", re.I)


def maybe_start_from_agreement(text):
    """If they say yes to going out (or just say they'll walk), actually start it."""
    if quest is not None or pending["kind"] is not None:
        return False
    if len(text.split()) > 20 or NO_WORDS.search(text):
        return False
    recent = " ".join(plain_reply(m["content"]) for m in history[-6:] if m["role"] == "assistant")
    says_activity = bool(DO_WORDS.search(text))
    says_yes = bool(YES_WORDS.search(text))
    if not (says_activity or (says_yes and INVITE_WORDS.search(recent))):
        return False
    both = text + " " + recent
    if re.search(r"walk|stroll", both, re.I):
        start_activity(pick_activity("out", "walking"))
    elif DO_WORDS.search(both):
        start_random("out")
    else:
        choose_activity()
    return True


def handle_user_text(text):
    """Route what the user said: a task, a debrief answer, a highlight, a night reflection, or conversation."""
    kind = pending["kind"]
    if kind == "todo":
        pending["kind"] = None
        add_task(text)
    elif kind == "debrief":
        busy["on"] = True
        set_status("pip is judging your answer...")
        act = pending["act"]
        threading.Thread(target=evaluate_debrief, args=(text, act), daemon=True).start()
    elif kind == "highlight":
        idx = pending["index"]
        pending["kind"] = None
        data["diary"][idx]["highlight"] = text
        save_data()
        write_diary(idx)
        pip_reply(f'(stage direction: the user told you the one thing they got from it: "{text}". '
                  "React warmly to that specific thing in one or two sentences.)")
    elif kind == "reflect":
        pending["kind"] = None
        entry = {"time": time.strftime("%Y-%m-%d %H:%M"), "activity": "night reflection", "id": "reflection",
                 "highlight": text, "text": "", "level": quests_done + 1}
        data["diary"].append(entry)
        save_data()
        write_diary(len(data["diary"]) - 1)
        pip_reply(f'(stage direction: the user told you about their day: "{text}". React kindly to what they said '
                  "in one or two sentences, then gently tell them to put the screen down and go to sleep.)")
    else:
        if maybe_start_from_agreement(text):
            return
        pip_reply(text, grantable=True)


def send_message(event=None):
    text = chat_entry.get().strip()
    if not text:
        return
    if busy["on"]:
        set_status("hold on, pip is still talking")
        return
    chat_entry.delete(0, "end")
    chat_append("You", text)
    handle_user_text(text)


# ---------- Voice input (offline, Vosk) ----------
def listen_once(max_seconds=14, no_speech_timeout=8):
    """Wait for Pip to finish talking, beep, then record until you stop talking.
    Returns (text, peak_level). Runs fully offline with Vosk."""
    global stt_model
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
    if stt_model is None:
        stt_model = Model(lang="en-us")     # downloads a small model (~40 MB) the first time only
    rec = KaldiRecognizer(stt_model, 16000)
    with speak_lock:
        pass                                # wait until Pip has finished talking
    if winsound:
        try:
            winsound.Beep(880, 150)         # beep = "speak now"
        except Exception:
            pass
    ui_call(lambda: set_status("listening... go ahead"))
    start = time.time()
    heard, text, peak = False, "", 0.0
    with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1,
                           device=MIC_DEVICE) as stream:
        while time.time() - start < max_seconds:
            raw = bytes(stream.read(4000)[0])
            level = float(np.sqrt(np.mean(np.frombuffer(raw, dtype=np.int16).astype(np.float32) ** 2)))
            peak = max(peak, level)
            if rec.AcceptWaveform(raw):
                text = json.loads(rec.Result()).get("text", "")
                break
            if not heard and json.loads(rec.PartialResult()).get("partial"):
                heard = True
            if not heard and time.time() - start > no_speech_timeout:
                break
    if not text:
        text = json.loads(rec.FinalResult()).get("text", "")
    return text.strip(), peak


def start_listening():
    if listening["on"] or busy["on"]:
        return
    listening["on"] = True
    set_mic(MIC_BUSY, "disabled")
    set_status("warming up my ears...")

    def work():
        err, text, peak = None, "", 0.0
        try:
            text, peak = listen_once()
        except ImportError:
            err = "Voice input needs two packages. In Command Prompt run: pip install vosk sounddevice"
        except Exception as ex:
            err = f"Microphone problem: {ex}"
        ui_call(lambda: finish_listening(text, err, peak))
    threading.Thread(target=work, daemon=True).start()


def finish_listening(text, err, peak):
    listening["on"] = False
    set_status("")
    set_mic(MIC_IDLE, "normal")
    if (err or not text) and pending["kind"] == "todo":
        pending["kind"] = None
    if err:
        chat_append("System", err)
    elif not text:
        if peak < 150:
            chat_append("System", f"I heard almost nothing (mic level {peak:.0f}). Check MIC_DEVICE at the top "
                                  "of the file, and speak right after the beep.")
        else:
            chat_append("System", f"I heard sound (level {peak:.0f}) but couldn't make out words. "
                                  "Try shorter, clearer sentences.")
    else:
        chat_append("You", text)
        handle_user_text(text)


# ---------- To-do list ("my day") ----------
def add_task(text):
    text = text.strip()
    if not text:
        return
    data["todo"].append({"text": text, "done": False, "added": time.strftime("%H:%M")})
    data["todo"] = data["todo"][-30:]
    save_data()
    events.append(f"they added a task: {text}")
    refresh_todo()


def toggle_task(i):
    global joy_until
    t = data["todo"][i]
    t["done"] = not t["done"]
    if t["done"]:
        joy_until = time.time() + 5            # Pip celebrates silently
        events.append(f"they finished a task: {t['text']}")
    save_data()
    refresh_todo()


def clear_done_tasks():
    data["todo"] = [t for t in data["todo"] if not t["done"]]
    save_data()
    refresh_todo()


def refresh_todo():
    if not alive(todo_list):
        return
    todo_list.clear()
    if not data["todo"]:
        tk.Label(todo_list.inner, text="nothing yet. add what you need to do today and i'll check in on you.",
                 font=F(10), bg=BG, fg=MUTED, wraplength=380).pack(pady=30)
    order = sorted(range(len(data["todo"])), key=lambda i: data["todo"][i]["done"])
    for i in order:
        t = data["todo"][i]
        row = tk.Frame(todo_list.inner, bg=CARD_BG, highlightthickness=1, highlightbackground=EDGE,
                       cursor="hand2")
        row.pack(fill="x", padx=16, pady=4)
        ck = tk.Canvas(row, width=30, height=30, bg=CARD_BG, highlightthickness=0)
        ck.pack(side="left", padx=(10, 6), pady=8)
        ck.create_oval(4, 4, 26, 26, outline=VIOLET, width=2, fill=VIOLET if t["done"] else CARD_BG)
        if t["done"]:
            ck.create_line(10, 16, 14, 21, 21, 10, fill="white", width=3)
        lab = tk.Label(row, text=t["text"], bg=CARD_BG, fg=MUTED if t["done"] else INK, anchor="w",
                       justify="left", wraplength=320,
                       font=(FONT, 11, "overstrike") if t["done"] else F(11))
        lab.pack(side="left", fill="x", expand=True, pady=8)
        for w in (row, ck, lab):
            w.bind("<Button-1>", lambda e, k=i: toggle_task(k))


def speak_task():
    pending["kind"] = "todo"
    start_listening()


def open_todo():
    global todo_win, todo_list
    if alive(todo_win):
        todo_win.lift()
        refresh_todo()
        return
    todo_win = win = tk.Toplevel(root)
    win.title("my day")
    win.geometry("480x660+560+30")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    win.after(400, lambda: alive(win) and win.attributes("-topmost", False))
    tk.Label(win, text="my day", font=F(22, True), bg=BG, fg=INK).pack(pady=(18, 0))
    tk.Label(win, text="tell pip what you need to do. pip will check in and cheer you on.", font=F(10), bg=BG,
             fg=MUTED, wraplength=400).pack(pady=(2, 10))
    row = tk.Frame(win, bg=BG)
    row.pack(fill="x", padx=16)
    box, entry = styled_entry(row, width=18)
    box.pack(side="left", fill="x", expand=True)
    entry.bind("<Return>", lambda e: (add_task(entry.get()), entry.delete(0, "end")))
    PillButton(row, "Add", lambda: (add_task(entry.get()), entry.delete(0, "end")), height=38, pad=16).pack(
        side="left", padx=(8, 0))
    PillButton(row, "Speak", speak_task, bg=PINK, fg=ON_ACCENT, height=38, pad=14).pack(side="left", padx=(6, 0))
    PillButton(win, "clear finished", clear_done_tasks, bg=LILAC, fg=VIOLET, height=32, pad=14,
               font=F(9, True)).pack(side="bottom", pady=10)
    todo_list = ScrollFrame(win, BG)
    todo_list.pack(fill="both", expand=True, pady=10)
    refresh_todo()
    entry.focus_force()


# ---------- Quests, proof and diary ----------
def log_attempt(path, act, accepted, result):
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "activity": act["id"], "file": os.path.basename(path),
             "accepted": accepted, "result": result}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def proof_text(act):
    if act["proof"] == "item":
        return f"show you {act['item']} on the camera when they press the I'm back button"
    return "tell you what they did when they press the I'm back button, and you will quiz them a little"


def start_activity(act):
    global quest, joy_until
    close_warning()
    quest = {"act": act, "started": time.time(), "away_max": 0.0}
    joy_until = time.time() + 4          # Pip is happy you said yes
    events.append(f"they picked: {act['title']}")
    if act.get("note"):
        chat_append("System", f"[{act['note']}, so pip picked an indoor quest]")
    update_quest_label()
    if locked:
        lock_show_quest()          # stay locked until the quest is done
    if act["proof"] == "item":
        direction = (f"(stage direction: the user is heading out for: '{act['title']}'. In one or two short "
                     f"sentences, cheer them on, then tell them to bring you {act['item']} when they're back so "
                     "you can see it on the camera. Say it as a statement, not a question. Mention the activity.)")
    else:
        direction = (f"(stage direction: the user is heading out for: '{act['title']}'. In one or two short "
                     "sentences, cheer them on and tell them to come back and tell you all about it, because "
                     "you'll have a question for them. Say it as a statement, not a question. Mention the activity.)")
    if act.get("note"):
        direction = direction[:-1] + (f" Also say, in a few words, that you picked an indoor quest because "
                                      f"{act['note']}.)")
    pip_reply(direction)


def quick_walk():
    if quest is not None:
        chat_append("System", f"you already have a quest: {quest['act']['title']}")
        return
    start_activity(ACTIVITIES[0])


def ask_debrief(act):
    """Pip asks one specific question, and remembers it so the judge can check the answer against it."""
    pending.update(kind="debrief", act=act, question="")
    pip_reply(f"(stage direction: the user says they finished '{act['title']}'. Ask ONE short, specific question "
              "that only someone who really did it could answer: what they made, did, saw, or where they went. "
              f"{time_context()} Do NOT ask about the weather.)")


def im_back():
    if quest is None:
        chat_append("System", "no active quest yet. tap 'walk' or 'activities' first.")
        return
    act = quest["act"]
    needed = MIN_AWAY * act.get("away", 1)
    away = quest["away_max"]
    if away < needed:
        chat_append("System", f"You were only away from the screen for {away:.0f}s. "
                              f"Pip wants at least {needed:.0f}s ({away_mode()}). Go do it for real first.")
        pip_reply(f"(stage direction: the user says they're back from '{act['title']}' but they were only away from "
                  f"the screen for {away:.0f} seconds and you need {needed:.0f}. Playfully tell them it hasn't been long "
                  f"enough and that they need about {max(1, needed - away):.0f} more seconds away. Mention those numbers. "
                  "One or two sentences.)")
        return
    if act["proof"] == "item":
        open_proof()
    else:
        ask_debrief(act)


NEG = re.compile(r"\b(no|not|never|without|didn't|didnt|wasn't|wasnt|isn't)\b")


def weather_conflict(text):
    """Deterministic reality check of the answer against the real weather and time of day."""
    if not weather_info:
        return ""
    t = text.lower()
    if NEG.search(t):
        return ""
    desc, day = weather_info["desc"], weather_info["day"]
    if re.search(r"cloud|overcast", t) and desc == "clear sky":
        return f"they said it was cloudy, but the sky is actually clear ({weather_text})"
    if re.search(r"\bsun(ny|shine)?\b|sunlight", t) and not day:
        return "they described sun, but it is night"
    if re.search(r"\brain|drizzl|storm", t) and desc not in ("rain", "drizzle", "thunderstorm"):
        return f"they mentioned rain, but the weather is {weather_text}"
    return ""


def evaluate_debrief(text, act):
    plausible, highlight, why = True, text[:80], ""
    if len(text.split()) < 4:
        plausible, why = False, "their answer was too short and vague"
    else:
        conflict = weather_conflict(text)
        if conflict:
            plausible, why = False, conflict
        else:
            try:
                prompt = (
                    "You are a strict judge checking whether a user really did an activity.\n"
                    f'Activity: "{act["title"]}"\nQuestion asked: "{pending.get("question", "")}"\n'
                    f'User answered: "{text}"\n'
                    f"Facts: {time_context()} Real weather in {PLACE}: {weather_text}.\n"
                    "Judge: does the answer directly answer the question, with at least one concrete detail "
                    "(not generic, not a joke, not off-topic)? Does it contradict the facts or the time of day "
                    "(e.g. describing sunshine at night, or things that cannot be seen then)?\n"
                    'Reply ONLY with JSON: {"answers_question": true/false, "specific": true/false, '
                    '"contradicts_facts": true/false, "problem": "<10 words, or empty>", '
                    '"highlight": "<their key point in 12 words or less>"}')
                r = ollama.chat(model=VERIFY_MODEL, messages=[{"role": "user", "content": prompt}],
                                format="json", options={"temperature": 0, "num_predict": 100})
                d = json.loads(r["message"]["content"])
                plausible = (d.get("answers_question") is True and d.get("specific") is True
                             and d.get("contradicts_facts") is not True)
                highlight = str(d.get("highlight") or text[:80])
                if not plausible:
                    why = str(d.get("problem") or "their answer did not hold up")
            except Exception:
                pass        # judge crashed: don't punish the user
    ui_call(lambda: after_debrief(plausible, highlight, act, why))


def after_debrief(plausible, highlight, act, why=""):
    busy["on"] = False
    set_status("")
    if plausible:
        pending["kind"] = None
        complete_quest(act, highlight)
    else:
        pip_reply(f"(stage direction: you don't believe them. Reason: {why}. In one or two sentences, gently but "
                  "sternly say what doesn't add up, then ask ONE new specific question about what they did. "
                  "Do NOT ask about the weather.)")


def complete_quest(act, highlight=""):
    global quest, quests_done, joy_until
    if act.get("task"):
        for t in data["todo"]:
            if t["text"] == act["task"] and not t["done"]:
                t["done"] = True
                break
        refresh_todo()
    quest = None
    reset_timers()                       # finishing a quest resets the screen-time clock
    quests_done += 1
    joy_until = time.time() + 10
    day_stats()["quests"] += 1
    new_items = grant_unlocks()
    entry = {"time": time.strftime("%Y-%m-%d %H:%M"), "activity": act["title"], "id": act["id"],
             "highlight": highlight, "text": "", "level": quests_done + 1}
    data["diary"].append(entry)
    idx = len(data["diary"]) - 1
    save_data()
    events.append(f"they finished: {act['title']} and you grew")
    close_proof()
    unlock_screen()
    ensure_chat()
    update_quest_label()
    show_levelup(quests_done + 1, new_items)
    chat_append("System", f"Quest complete! Pip grew to level {quests_done + 1}.")
    for it in new_items:
        chat_append("System", f"New accessory unlocked: {it['name']}! Pip is wearing it. Open the wardrobe to change.")
    if highlight:
        write_diary(idx)
        pip_reply(f'(stage direction: the user finished "{act["title"]}" and you just grew bigger. '
                  f'Celebrate in one or two sentences and mention what they said: "{highlight}".)')
    else:
        pending.update(kind="highlight", index=idx)
        pip_reply(f'(stage direction: the user finished "{act["title"]}" and you just grew bigger. Celebrate in one '
                  "sentence, then ask them: what's one thing you got from it?)")


def write_diary(idx):
    e = data["diary"][idx]

    def work():
        try:
            if e["id"] == "reflection":
                prompt = (f"You are {NAME}, {PERSONA} Write a short, gentle goodnight diary entry (2 sentences, "
                          f"max 45 words). {profile_name()} told you about their day: \"{e.get('highlight')}\". "
                          "First person, warm, a little sleepy.")
            else:
                prompt = (f"You are {NAME}, {PERSONA} Write a short diary entry (2 sentences, max 45 words) about "
                          f"today. {profile_name()} did this: {e['activity']}. Their highlight: "
                          f"{e.get('highlight') or 'not shared'}. Weather: {weather_text}. You are now level "
                          f"{e['level']}. First person, warm, a little dramatic.")
            r = ollama.chat(model=GEMMA, messages=[{"role": "user", "content": prompt}],
                            options={"temperature": 0.8, "num_predict": 90})
            e["text"] = r["message"]["content"].strip()
        except Exception:
            e["text"] = "(pip was too sleepy to write this one.)"
        save_data()
        ui_call(refresh_journal)
    threading.Thread(target=work, daemon=True).start()


# ---------- Game HUD: level badge, unlock progress, patience meter, camera status ----------
hud_cv = None
PATIENCE_COL = {0: "#5ccf9b", 1: "#ffd34d", 2: "#ff9f43", 3: "#ff5a6b", 4: "#ff5a6b"}
STAGE_NAME = {0: "calm", 1: "restless", 2: "annoyed", 3: "fuming", 4: "locking"}


def patience_frac():
    return max(0.0, min(1.0, 1.0 - active / (2 * LEVEL_AT + grace + LOCK_WARN)))


def cam_status():
    """(text, colour) describing what the camera check is doing right now."""
    if not cam_state["on"]:
        return "cam off", "#ff5a6b"
    if not cam_live():
        return "cam offline", "#ff5a6b"
    if presence.get("error"):
        return ("motion seen" if presence["face"] else "no motion"), "#ffb347"
    if presence["blind"]:
        return "cam can't see you", "#ffb347"
    if presence["face"]:
        return "cam sees you", "#5ccf9b"
    return "nobody in view", "#ffd34d"


def _bar(cv, x1, y1, x2, y2, frac, col):
    """A chunky game-style progress bar with a gloss line."""
    r = (y2 - y1) / 2.0
    cv.create_polygon(rounded_poly(x1, y1, x2, y2, r), smooth=True, fill=TRACK, outline=EDGE, width=2)
    frac = max(0.0, min(1.0, frac))
    if frac <= 0:
        return
    ri = r - 3
    xe = max(x1 + 3 + 2 * ri, x1 + 3 + (x2 - x1 - 6) * frac)
    cv.create_polygon(rounded_poly(x1 + 3, y1 + 3, xe, y2 - 3, ri), smooth=True, fill=col, outline="")
    cv.create_line(x1 + 3 + ri, y1 + 5, xe - ri, y1 + 5, fill=shade(col, 1.35), width=2, capstyle="round")


def draw_hud():
    cv = hud_cv
    if not alive(cv):
        return
    cv.delete("all")
    w, h = max(300, cv.winfo_width()), 104
    cv.create_polygon(rounded_poly(2, 2, w - 2, h - 2, 16), smooth=True, fill=CARD_BG, outline=EDGE, width=2)
    lv = pip_level()
    cv.create_oval(14, 27, 70, 83, fill="#b8860b", outline="")                      # badge rim
    cv.create_oval(14, 22, 70, 78, fill=GOLD, outline="#fff1a8", width=2)
    cv.create_text(42, 38, text="LV", font=F(8, True), fill="#7a5a00")
    cv.create_text(42, 58, text=str(lv), font=F(18, True), fill="#3b2a00")
    x1, x2 = 86, w - 16
    nxt = min((c_ for c_ in COSMETICS if c_["level"] > lv), key=lambda c_: c_["level"], default=None)
    prev = max([c_["level"] for c_ in COSMETICS if c_["level"] <= lv] or [1])
    if nxt:
        frac, hint = (lv - prev) / max(1, nxt["level"] - prev), f"{nxt['name']} at lv {nxt['level']}"
    else:
        frac, hint = 1.0, "everything unlocked"
    cv.create_text(x1, 16, text="unlock progress", anchor="w", font=F(8, True), fill=MUTED)
    cv.create_text(x2, 16, text=hint, anchor="e", font=F(8, True), fill=GOLD)
    _bar(cv, x1, 25, x2, 39, frac, VIOLET)
    stg = get_stage()
    cv.create_text(x1, 52, text="pip's patience", anchor="w", font=F(8, True), fill=MUTED)
    cv.create_text(x2, 52, text="paused: on a quest" if quest_calm() else STAGE_NAME[stg], anchor="e",
                   font=F(8, True), fill=PATIENCE_COL[stg])
    _bar(cv, x1, 61, x2, 75, patience_frac(), PATIENCE_COL[stg])
    cur, _best = streaks()
    n = int(day_stats()["quests"])
    txt, col = cam_status()
    cv.create_text(x1, 92, text=f"streak {cur}d   today {n} quest{'s' if n != 1 else ''}", anchor="w",
                   font=F(8, True), fill=MUTED)
    cv.create_oval(x2 - 8, 88, x2, 96, fill=col, outline="")
    cv.create_text(x2 - 14, 92, text=txt, anchor="e", font=F(8, True), fill=MUTED)


def draw_nameplate():
    """The little game name tag under Pip on the desktop: level + patience bar."""
    x1, x2, y1, y2 = W / 2 - 80, W / 2 + 80, H - 30, H - 6
    mid = (y1 + y2) / 2
    c.create_polygon(rounded_poly(x1, y1, x2, y2, 12), smooth=True, fill=CARD_BG, outline=EDGE, width=2)
    c.create_text(x1 + 12, mid, text=f"LV {pip_level()}", anchor="w", fill=GOLD, font=F(9, True))
    c.create_text(x1 + 52, mid, text=NAME.upper(), anchor="w", fill=INK, font=F(9, True))
    bx1, bx2 = x2 - 56, x2 - 12
    c.create_rectangle(bx1, mid - 4, bx2, mid + 4, fill=TRACK, outline="")
    f = patience_frac()
    if f > 0:
        c.create_rectangle(bx1, mid - 4, bx1 + (bx2 - bx1) * f, mid + 4, fill=PATIENCE_COL[get_stage()], outline="")


def show_levelup(level, items=()):
    """Big arcade-style LEVEL UP banner with confetti. Never takes keyboard focus."""
    try:
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-transparentcolor", KEY)
        win.configure(bg=KEY)
        cw, ch = 560, 250
        win.geometry(f"{cw}x{ch}+{(win.winfo_screenwidth() - cw) // 2}+{int(win.winfo_screenheight() * 0.1)}")
        cv = tk.Canvas(win, width=cw, height=ch, bg=KEY, highlightthickness=0)
        cv.pack()
    except tk.TclError:
        return
    cols = ["#ffd34d", "#ff6fa5", "#5ccf9b", "#6ec6ff", "#c8a8ff"]
    bits = [[cw / 2, 100, random.uniform(-7, 7), random.uniform(-11, -3), random.choice(cols),
             random.uniform(4, 8)] for _ in range(60)]
    lines = [f"Pip is now level {level}"] + [f"new: {it['name']}" for it in items]
    t0 = time.time()

    def frame():
        if not alive(win):
            return
        el = time.time() - t0
        if el > 3.4:
            win.destroy()
            return
        cv.delete("all")
        pop = min(1.0, el / 0.3)
        s = 0.5 + 0.5 * pop + (0.03 * math.sin(el * 9) if el > 0.3 else 0)
        cx, cy = cw / 2, 92
        bw, bh = 200 * s, 42 * s
        cv.create_polygon(rounded_poly(cx - bw, cy - bh + 8, cx + bw, cy + bh + 8, 22 * s), smooth=True,
                          fill="#8a5a00", outline="")
        cv.create_polygon(rounded_poly(cx - bw, cy - bh, cx + bw, cy + bh, 22 * s), smooth=True, fill=GOLD,
                          outline="#fff1a8", width=3)
        cv.create_text(cx, cy, text="LEVEL UP!", font=F(max(8, int(30 * s)), True), fill="#3b2a00")
        if el > 0.3:
            for k, ln in enumerate(lines):
                pw, ytop = (len(ln) * 8 + 32) / 2.0, cy + bh + 24 + k * 34
                cv.create_polygon(rounded_poly(cx - pw, ytop - 14, cx + pw, ytop + 14, 14), smooth=True,
                                  fill=CARD_BG, outline=GOLD, width=2)
                cv.create_text(cx, ytop, text=ln, font=F(11, True), fill=INK)
        for b in bits:
            b[0] += b[2]
            b[1] += b[3]
            b[3] += 0.55
            if 0 < b[0] < cw and b[1] < ch:
                cv.create_rectangle(b[0] - b[5], b[1] - b[5], b[0] + b[5], b[1] + b[5], fill=b[4], outline="")
        win.after(33, frame)
    frame()


cam_test_win = None


def open_cam_test():
    """Shows what Pip's camera check sees (face box + status). Frames stay in memory and are never saved."""
    global cam_test_win
    if alive(cam_test_win):
        cam_test_win.lift()
        return
    cam_test_win = win = tk.Toplevel(root)
    win.title("camera check")
    win.geometry("540x620+420+20")
    win.configure(bg=BG)
    tk.Label(win, text="camera check", font=F(22, True), bg=BG, fg=INK).pack(pady=(16, 2))
    info = tk.Label(win, text="", font=F(10, True), bg=BG, fg=VIOLET, wraplength=480, justify="center")
    info.pack(pady=4)
    view = tk.Label(win, bg="black")
    view.pack(pady=8)
    tk.Label(win, text="a green box means pip can see your face. frames stay in memory and are never saved.",
             font=F(9), bg=BG, fg=MUTED, wraplength=460).pack()
    presence["want_preview"] = True

    def close():
        presence["want_preview"] = False
        presence["preview"] = None
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", close)

    def refresh():
        if not alive(win):
            presence["want_preview"] = False
            return
        txt, _col = cam_status()
        rate = presence["blink_rate"]
        info.config(text=f"{txt}   |   blinks per minute: {('%.0f' % rate) if rate is not None else 'measuring...'}"
                         f"   |   posture: {'nudge pending' if presence['posture_flag'] else 'ok'}")
        fr = presence.get("preview")
        if fr is not None:
            ok, buf = cv2.imencode(".png", cv2.flip(fr, 1))
            if ok:
                img = tk.PhotoImage(data=base64.b64encode(buf.tobytes()))
                view.config(image=img)
                view.img = img
        win.after(150, refresh)
    refresh()


def update_quest_label():
    try:
        if alive(level_label):
            n = quests_done
            level_label.config(text=f"LEVEL {n + 1}  \u2022  {n} quest{'s' if n != 1 else ''} done")
        if alive(quest_label):
            if quest is None:
                quest_label.config(text="NO ACTIVE QUEST  \u2022  tap 'new quest' to start one", fg=MUTED)
            else:
                needed = MIN_AWAY * quest["act"].get("away", 1)
                quest_label.config(text=f"QUEST: {quest['act']['title']}\ntime away {quest['away_max']:.0f}s of "
                                        f"{needed:.0f}s needed  \u2022  {away_mode()}", fg="#4b2fa8")
        draw_hud()
    except Exception:
        pass


# ---------- Camera proof ----------
def frame_to_jpeg_bytes(frame, max_side=1000):
    h, w = frame.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes() if ok else None


def verify_image(img_bytes, target, outdoor=False):
    if img_bytes is None:
        return {"match": False, "is_screen": False, "indoor_fail": False,
                "reason": "I could not read the camera frame."}
    prompt = (
        "Look at the single main object in this photo and classify it.\n"
        "Choose exactly ONE label from this list: " + ", ".join(LABELS) + ".\n"
        "Pick the label that best describes what the object really is. "
        "Also say where the photo was taken: 'outdoors' if you can see sky, trees, growing plants, bare ground, "
        "pavement or a street in the background, or 'indoors' if you see walls, a ceiling, a desk, a monitor, "
        "furniture or room lighting.\n"
        'Reply ONLY with JSON: {"main_object": "<what it is, 1 to 4 words>", "label": "<one label from the list>", '
        '"setting": "<outdoors or indoors>"}'
    )
    try:
        r = ollama.chat(model=VERIFY_MODEL,
                        messages=[{"role": "user", "content": prompt, "images": [img_bytes]}],
                        options={"temperature": 0})
        txt = r["message"]["content"]
        d = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
        seen = str(d.get("main_object", "something odd"))
        label = str(d.get("label", "")).strip().lower()
        setting = str(d.get("setting", "")).strip().lower()
        indoor_fail = False          # no longer rejects photos for 'looking indoors'
        reason = f"I see: {seen}"
        if indoor_fail:
            reason += ". this looks like it was taken indoors, not outside"
        return {"match": label == target, "is_screen": label in SCREEN_LABELS, "label": label,
                "setting": setting, "indoor_fail": indoor_fail, "reason": reason}
    except Exception:
        return {"match": False, "is_screen": False, "indoor_fail": False,
                "reason": "I could not understand what I saw."}


def open_camera():
    for use_dshow in (False, True):
        cam = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW) if use_dshow else cv2.VideoCapture(CAM_INDEX)
        if cam.isOpened():
            ok, _ = cam.read()
            if ok:
                return cam
        cam.release()
    return None


def open_proof():
    global proof_win
    if alive(proof_win):
        proof_win.lift()
        return
    act = quest["act"]
    proof_win = win = tk.Toplevel(root)
    win.title("show pip what you found")
    win.geometry("560x600+120+30")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    win.after(400, lambda: alive(win) and win.attributes("-topmost", False))
    tk.Label(win, text=f"hold up {act['item']}", font=F(16, True), bg=BG, fg=INK).pack(pady=(16, 2))
    proof["status"] = tk.Label(win, text="starting camera...", fg="#b36b00", bg=BG, font=F(10))
    proof["status"].pack()
    proof["label"] = tk.Label(win, bg="black")
    proof["label"].pack(pady=8)
    proof["btn"] = PillButton(win, "Capture", capture_proof, height=44, width=180)
    proof["btn"].pack(pady=8)
    win.protocol("WM_DELETE_WINDOW", close_proof)
    proof["frame"] = None
    proof["w"] = 480
    presence["pause"] = True           # the background camera watcher lets go of the camera meanwhile
    start_proof_camera()


def start_proof_camera():
    if not alive(proof_win):
        return
    if presence["has_cam"]:            # wait for the background watcher to release the camera
        proof_win.after(300, start_proof_camera)
        return
    cam = open_camera()
    if cam is None:
        proof["status"].config(text="No camera found. Open Iriun on your phone and laptop. Retrying...")
        proof_win.after(3000, start_proof_camera)
        return
    proof["cam"] = cam
    proof["status"].config(text="")
    update_proof_preview()


def update_proof_preview():
    if not alive(proof_win) or proof["cam"] is None:
        return
    ok, frame = proof["cam"].read()
    if ok:
        proof["frame"] = frame
        h, w = frame.shape[:2]
        pw = proof["w"]
        view = cv2.flip(cv2.resize(frame, (pw, int(pw * h / w))), 1)
        ok2, buf = cv2.imencode(".png", view)
        if ok2:
            img = tk.PhotoImage(data=base64.b64encode(buf.tobytes()))
            proof["label"].config(image=img)
            proof["photo"] = img
    proof_win.after(66, update_proof_preview)


def close_proof():
    global proof_win
    presence["pause"] = False          # background camera watcher may use the camera again
    if proof["cam"] is not None:
        proof["cam"].release()
        proof["cam"] = None
    if alive(proof_win):
        proof_win.destroy()
    proof_win = None


def capture_proof():
    if proof["frame"] is None:
        proof["status"].config(text="The camera isn't ready yet.")
        return
    frame = proof["frame"].copy()
    path = os.path.join(CAPTURE_DIR, time.strftime("%Y%m%d_%H%M%S") + ".jpg")
    cv2.imwrite(path, frame)
    img_bytes = frame_to_jpeg_bytes(frame)
    act = quest["act"]
    outdoor = act.get("where") == "out"
    proof["btn"].config(state="disabled")
    proof["status"].config(text="pip is inspecting your find... (a few seconds)")

    def work():
        if outdoor and is_duplicate_photo(frame):
            result = {"match": False, "is_screen": False, "indoor_fail": False,
                      "reason": "this looks just like a photo you already used. find a new one"}
        else:
            result = verify_image(img_bytes, act["label"], outdoor)
        accepted = (result.get("match") is True and not result.get("is_screen")
                    and not result.get("indoor_fail"))
        log_attempt(path, act, accepted, result)

        def done():
            if accepted and outdoor:
                remember_photo(frame)
            finish_proof(accepted, result, act)
        ui_call(done)
    threading.Thread(target=work, daemon=True).start()


def finish_proof(accepted, result, act):
    reason = result.get("reason", "")
    if accepted:
        complete_quest(act)
    elif alive(proof_win):
        proof["btn"].config(state="normal")
        proof["status"].config(text=f"Rejected: {reason}")
        chat_append("System", f"Rejected: {reason}")
        pip_reply(f"(stage direction: the photo check failed. {reason}. Scold them cutely in one sentence and "
                  "tell them to try again.)")


# ---------- Pip's big windows ----------
def animate_big(cv, win, cx, by, s, mood_fn, halo=None):
    """Animate Pip on any canvas. Only Pip's own items are redrawn, so backgrounds stay put."""
    if not alive(win):
        return
    cv.delete("pip")
    before = set(cv.find_all())
    if halo:
        cv.create_oval(cx - 100 * s, by - 196 * s, cx + 100 * s, by + 8 * s, fill=halo, outline="")
    draw_pip(cv, cx, by, s, mood_fn(), time.time())
    for i in set(cv.find_all()) - before:
        cv.addtag_withtag("pip", i)
    win.after(60, lambda: animate_big(cv, win, cx, by, s, mood_fn, halo))


def make_avatar(parent, size, mood_fn, bg, halo=None):
    cv = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0)
    animate_big(cv, cv, size / 2, size - 3, size / 232, mood_fn, halo)
    return cv


def gradient_header(parent, w, h, c1=None, c2=None):
    c1, c2 = c1 or HEAD1, c2 or HEAD2
    cv = tk.Canvas(parent, width=w, height=h, bg=c1, highlightthickness=0)
    cv._img = gradient_image(w, h, c1, c2)
    cv.create_image(0, 0, image=cv._img, anchor="nw")
    for _ in range(max(10, w * h // 3500)):          # tiny starfield
        x, y, r = random.randint(4, w - 4), random.randint(4, h - 4), random.choice((1, 1, 2))
        cv.create_oval(x - r, y - r, x + r, y + r, fill=random.choice(("#ffffff", LAV, "#ffe27a")), outline="")
    return cv


def show_onboarding():
    win = tk.Toplevel(root)
    win.title("meet pip")
    win.geometry("540x780+180+6")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    cv = gradient_header(win, 540, 240)
    cv.pack()
    animate_big(cv, cv, 270, 232, 0.92, lambda: "happy", halo=HALO)
    tk.Label(win, text="hi!! i'm pip.", font=F(24, True), bg=BG, fg=INK).pack(pady=(12, 0))
    tk.Label(win, text="i'm tiny now, but i grow every time you go outside.\nwhat should i call you?",
             font=F(11), bg=BG, fg=MUTED, justify="center").pack(pady=(2, 8))
    box, name_entry = styled_entry(win, font=F(14), width=22)
    box.pack(padx=100, fill="x")
    tk.Label(win, text="what do you like doing away from the screen?", font=F(11, True), bg=BG,
             fg=INK).pack(pady=(16, 6))
    chosen = {}
    grid = tk.Frame(win, bg=BG)
    grid.pack()

    def toggle(tag, btn):
        chosen[tag] = not chosen.get(tag, False)
        if chosen[tag]:
            btn.config(bg=VIOLET, fg="white")
        else:
            btn.config(bg=LILAC, fg=VIOLET)
    for n, (tag, label) in enumerate(LIKES):
        b = PillButton(grid, label, None, bg=LILAC, fg=VIOLET, height=38, width=210, font=F(10, True))
        b._cmd = lambda t=tag, bb=b: toggle(t, bb)
        b._keep = True
        b.grid(row=n // 2, column=n % 2, padx=5, pady=4)

    def save():
        name = name_entry.get().strip()
        if not name:
            box.config(highlightbackground=DANGER)
            return
        data["profile"] = {"name": name, "likes": [t for t, v in chosen.items() if v]}
        save_data()
        win.destroy()
        show_greeting()
    PillButton(win, "let's go", save, height=48, width=220, font=F(13, True)).pack(pady=20)
    name_entry.focus_force()


def breathe(win, canvas, label, hide=(), restore=None):
    """Guided breathing. The other buttons are hidden while it runs and come back after."""
    if canvas.winfo_ismapped():
        return                                   # already running
    for w in hide:
        w.pack_forget()
    start = time.time()
    state = {"done": False}
    canvas.pack(after=label)

    def finish(msg):
        if state["done"]:
            return
        state["done"] = True
        canvas.delete("all")
        canvas.pack_forget()
        label.config(text=msg)
        if restore:
            restore()
    canvas.bind("<Button-1>", lambda e: finish("okay, we can stop here. that was good."))

    def step():
        if not alive(win) or state["done"]:
            return
        el = time.time() - start
        canvas.delete("all")
        if el >= 24:
            finish("nice, that's three. feel any better?")
            return
        ph = (el % 8) / 8
        inhale = ph < 0.5
        frac = ph * 2 if inhale else 1 - (ph - 0.5) * 2
        r = 18 + 38 * frac
        canvas.create_oval(70 - r, 70 - r, 70 + r, 70 + r, fill=LAV, outline="")
        label.config(text="breathe in..." if inhale else "breathe out...")
        win.after(60, step)
    step()


def show_greeting():
    win = tk.Toplevel(root)
    win.title("pip")
    win.geometry("540x760+180+6")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    win.after(500, lambda: alive(win) and win.attributes("-topmost", False))
    late = day_part() == "late night"
    cv = gradient_header(win, 540, 250) if not late else \
        gradient_header(win, 540, 250, "#3a2a5c", "#6b4a8c")
    cv.pack()
    animate_big(cv, cv, 270, 242, 0.95, lambda: "meh" if late else "happy", halo=HALO if not late else "#7a5aa0")
    tk.Label(win, text=f"hi, {profile_name()}!", font=F(24, True), bg=BG, fg=INK).pack(pady=(12, 0))
    tk.Label(win, text=greet_text(), font=F(11), bg=BG, fg=INK, wraplength=470, justify="center").pack(
        pady=8, padx=20)
    bl = tk.Label(win, text="", font=F(11, True), bg=BG, fg=VIOLET)
    bl.pack()
    bc = tk.Canvas(win, width=140, height=140, bg=BG, highlightthickness=0)
    grid = tk.Frame(win, bg=BG)
    grid.pack(pady=10)
    n_open = len(open_tasks())
    todo_label = f"my day ({n_open} open)" if n_open else "my day (to-do)"
    talk_label = "tell pip about my day" if late else "talk to pip"
    btns = [
        ("3 slow breaths", LILAC, VIOLET, lambda: breathe(win, bc, bl, hide=(grid, start_btn), restore=restore)),
        ("pick an activity", VIOLET, "white", lambda: choose_activity()),
        (todo_label, MINT, ON_ACCENT, lambda: open_todo()),
        (talk_label, PINK, ON_ACCENT, lambda: (win.destroy(), open_chat(greet=True))),
    ]
    for n, (text, bg, fg, cmd) in enumerate(btns):
        PillButton(grid, text, cmd, bg=bg, fg=fg, height=44, width=232).grid(row=n // 2, column=n % 2, padx=5, pady=5)
    start_btn = PillButton(win, "start my day", win.destroy, bg=BG, fg=VIOLET, outline=VIOLET, height=40, width=200)
    start_btn.pack(pady=8)

    def restore():
        grid.pack(pady=10)
        start_btn.pack(pady=8)


def choose_activity():
    win = tk.Toplevel(root)
    win.title("pick something to do")
    win.geometry("420x360+240+60")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    tk.Label(win, text="where to?", font=F(18, True), bg=BG, fg=INK).pack(pady=(24, 14))
    where_buttons(win, lambda w: (win.destroy(), start_random(w)))


def close_warning():
    global warn_win
    if alive(warn_win):
        warn_win.destroy()
    warn_win = None


def show_warning():
    global warn_win, warn_label
    if alive(warn_win):
        return
    warn_win = win = tk.Toplevel(root)
    win.title("pip is losing it")
    win.geometry("500x470+300+120")
    win.configure(bg=DANGER_BG)
    win.attributes("-topmost", True)
    make_avatar(win, 130, lambda: "fuming", DANGER_BG, halo="#5a1a28").pack(pady=(14, 0))
    tk.Label(win, text="pip is fuming", font=F(22, True), bg=DANGER_BG, fg=DANGER).pack()
    warn_label = tk.Label(win, text="", font=F(12), bg=DANGER_BG, fg="#ffe9ec", wraplength=420)
    warn_label.pack(pady=10)
    PillButton(win, "pick an activity", lambda: (close_warning(), choose_activity()), bg=DANGER, height=44,
               width=300).pack(pady=4)
    PillButton(win, "i'm busy, let me explain", lambda: (close_warning(), explain_busy()), bg=DANGER_BG,
               fg=DANGER, outline=DANGER, height=44, width=300).pack(pady=4)
    PillButton(win, "dismiss", close_warning, bg=DANGER_BG, fg=MUTED, height=32, width=120,
               font=F(9, True)).pack(pady=6)
    update_warning()


def update_warning():
    if alive(warn_win):
        left = max(0, 2 * LEVEL_AT + grace + LOCK_WARN - active)
        m, s = divmod(int(left), 60)
        warn_label.config(text=f"{profile_name()}, you've been on screen way too long. "
                               f"i'm locking this screen in {m}:{s:02d} unless you go do something.")


def explain_busy():
    open_chat(greet=False)
    pip_reply("(stage direction: the user says they are busy and can't leave the screen right now. Be understanding, "
              "and ask them when they will be free.)")


# ---------- The lock: stays up until the quest is proven (camera / questions happen inside it) ----------
def lock_clear():
    if alive(lock_body):
        for w in lock_body.winfo_children():
            w.destroy()
    tk.Frame(lock_body, width=520, height=1, bg=PLUM).pack()      # keeps a sensible width


def lock_screen():
    global locked, lock_win, lock_body, lock_msg
    if locked:
        return
    locked = True
    close_warning()
    close_toast()
    lock_win = win = tk.Toplevel(root)
    win.configure(bg=PLUM)
    win.attributes("-fullscreen", True)
    win.attributes("-topmost", True)
    win.protocol("WM_DELETE_WINDOW", lambda: None)
    if ALLOW_ESCAPE:
        win.bind("<Control-Shift-Q>", lambda e: unlock_screen())
    win.focus_force()
    cv = tk.Canvas(win, width=210, height=170, bg=PLUM, highlightthickness=0)
    cv.pack(pady=(24, 0))
    animate_big(cv, cv, 105, 163, 0.72, lambda: "fuming" if quest is None else "happy", halo="#4a2152")
    tk.Label(win, text="pip locked your screen", font=F(24, True), bg=PLUM, fg="white").pack()
    lock_msg = tk.Label(win, text="", font=F(13), bg=PLUM, fg="#ffd6ea", wraplength=760, justify="center")
    lock_msg.pack(pady=(4, 10))
    lock_body = tk.Frame(win, bg=PLUM)
    lock_body.pack()
    if ALLOW_ESCAPE:
        tk.Label(win, text="emergency exit: Ctrl+Shift+Q", font=F(8), bg=PLUM, fg="#7d5a86").pack(
            side="bottom", pady=6)
    if quest is None:
        lock_show_picker()
    else:
        lock_show_quest()
    keep_lock_on_top()


def keep_lock_on_top():
    if not alive(lock_win):
        return
    try:
        lock_win.lift()
        lock_win.attributes("-topmost", True)
        if lock_win.focus_displayof() is None:
            lock_win.focus_force()
    except tk.TclError:
        pass
    lock_win.after(250, keep_lock_on_top)


def lock_show_picker():
    lock_clear()
    lock_msg.config(text=f"{profile_name()}, pick one. the screen stays locked until you've done it.")
    where_buttons(lock_body, start_random)


def lock_show_quest():
    lock_clear()
    lock_msg.config(text=f"go do it: {quest['act']['title']}. the screen stays locked until you're back and prove it.")
    PillButton(lock_body, "I'm back", lock_im_back, bg=PINK, fg=ON_ACCENT, height=52, width=260,
               font=F(15, True)).pack(pady=16)


def lock_im_back():
    act = quest["act"]
    needed = MIN_AWAY * act.get("away", 1)
    away = quest["away_max"]
    if away < needed:
        lock_msg.config(text=f"you were only away for {away:.0f}s. pip wants {needed:.0f}s ({away_mode()}). "
                             "go do it for real.")
        return
    if act["proof"] == "item":
        lock_show_camera()
    else:
        lock_show_debrief()
        ask_debrief(act)


def lock_show_camera():
    global proof_win
    lock_clear()
    lock_msg.config(text=f"hold up {quest['act']['item']} to the camera")
    proof_win = holder = tk.Frame(lock_body, bg=PLUM)
    holder.pack()
    proof["status"] = tk.Label(holder, text="starting camera...", fg="#ffcc66", bg=PLUM, font=F(10))
    proof["status"].pack()
    proof["label"] = tk.Label(holder, bg="black")
    proof["label"].pack(pady=6)
    row = tk.Frame(holder, bg=PLUM)
    row.pack(pady=6)
    proof["btn"] = PillButton(row, "Capture", capture_proof, bg=PINK, fg=ON_ACCENT, height=44, width=170)
    proof["btn"].pack(side="left", padx=6)
    PillButton(row, "back", lambda: (close_proof(), lock_show_quest()), bg=PLUM, fg="#ffd6ea", outline="#ffd6ea",
               height=44, width=100).pack(side="left", padx=6)
    proof["frame"] = None
    proof["w"] = 360
    presence["pause"] = True           # the background camera watcher lets go of the camera meanwhile
    start_proof_camera()


def lock_show_debrief():
    global lock_status, lock_mic
    lock_clear()
    lock_msg.config(text="pip is about to ask you something...")
    lock_status = tk.Label(lock_body, text="", fg="#ffcc66", bg=PLUM, font=F(10))
    lock_status.pack()
    box, entry = styled_entry(lock_body, font=F(14), width=46)
    box.pack(pady=6, fill="x")

    def send(event=None):
        text = entry.get().strip()
        if not text:
            return
        if busy["on"]:
            set_status("hold on, pip is still talking")
            return
        entry.delete(0, "end")
        chat_append("You", text)
        handle_user_text(text)
    entry.bind("<Return>", send)
    row = tk.Frame(lock_body, bg=PLUM)
    row.pack(pady=6)
    PillButton(row, "Send", send, bg=PINK, fg=ON_ACCENT, height=42, width=130).pack(side="left", padx=6)
    lock_mic = PillButton(row, MIC_IDLE, start_listening, bg=PLUM, fg="#ffd6ea", outline="#ffd6ea", height=42,
                          width=130)
    lock_mic.pack(side="left", padx=6)
    entry.focus_force()


def unlock_screen():
    global locked, lock_win, active, grace, grants_used, warned
    was_locked = locked
    if was_locked:
        close_proof()
    if alive(lock_win):
        lock_win.destroy()
    lock_win = None
    if was_locked:
        locked = False
        reset_timers()


# ---------- Journal ----------
def refresh_journal():
    if not alive(journal_list):
        return
    journal_list.clear()
    if not data["diary"]:
        tk.Label(journal_list.inner, text="nothing here yet. finish a quest and i'll write about it.",
                 font=F(10), bg=BG, fg=MUTED, wraplength=380).pack(pady=40)
    colors = {a["id"]: a["color"] for a in ACTIVITIES}
    colors["reflection"] = "#b9a5e8"
    colors["todo"] = "#9be7c4"
    for e in reversed(data["diary"]):
        card = tk.Frame(journal_list.inner, bg=CARD_BG, highlightthickness=1, highlightbackground=EDGE)
        card.pack(fill="x", padx=16, pady=6)
        tk.Frame(card, bg=colors.get(e["id"], LAV), width=9).pack(side="left", fill="y")
        body = tk.Frame(card, bg=CARD_BG)
        body.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        tk.Label(body, text=e["activity"], font=F(11, True), bg=CARD_BG, fg=INK, anchor="w",
                 wraplength=380, justify="left").pack(fill="x")
        tk.Label(body, text=f"{e['time']}  \u2022  level {e.get('level', '?')}", font=F(8), bg=CARD_BG,
                 fg=MUTED, anchor="w").pack(fill="x")
        tk.Label(body, text=e.get("text") or "(writing...)", font=(FONT, 10, "italic"), bg=CARD_BG, fg=INK,
                 anchor="w", wraplength=380, justify="left").pack(fill="x", pady=(6, 2))
        if e.get("highlight"):
            tk.Label(body, text=f"you said: {e['highlight']}", font=F(9), bg=LILAC, fg=VIOLET, anchor="w",
                     wraplength=380, justify="left", padx=8, pady=3).pack(anchor="w", pady=(4, 0))


def open_journal():
    global journal_win, journal_list
    if alive(journal_win):
        journal_win.lift()
        refresh_journal()
        return
    journal_win = win = tk.Toplevel(root)
    win.title(f"{NAME}'s journal")
    win.geometry("500x680+520+20")
    win.configure(bg=BG)
    tk.Label(win, text=f"{NAME}'s journal", font=F(22, True), bg=BG, fg=INK).pack(pady=(18, 0))
    tk.Label(win, text="every quest, in pip's own words", font=F(10), bg=BG, fg=MUTED).pack(pady=(0, 8))
    journal_list = ScrollFrame(win, BG)
    journal_list.pack(fill="both", expand=True, pady=(0, 10))
    refresh_journal()


# ---------- Pip appearance customization ----------
THEMES = {
    "Lavender": {"body": "#4a4690", "body_hi": "#6e69c9", "bg": "#150f2b", "chat_bg": "#1b1436", "card": "#251b4a",
                 "edge": "#3f3180", "track": "#0e0920", "ink": "#f4efff", "muted": "#a99dd6", "violet": "#9277ff",
                 "lilac": "#33275f", "pink": "#ff6fa5", "lav": "#c8a8ff", "lav_dk": "#8e6fd1", "halo": "#2f2262",
                 "head1": "#3a2476", "head2": "#1b1436", "bub_pip": "#33276a", "bub_you": "#ff6fa5",
                 "on_accent": "#1d1236"},
    "Pink": {"body": "#c0508a", "body_hi": "#e47cae", "bg": "#240f1c", "chat_bg": "#2c1423", "card": "#3a1b2f",
             "edge": "#6b2f55", "track": "#170811", "ink": "#fff0f6", "muted": "#d6a3bd", "violet": "#ff5fa0",
             "lilac": "#4a2039", "pink": "#ff8fb1", "lav": "#ffc2dc", "lav_dk": "#d96c9c", "halo": "#4d2040",
             "head1": "#7a2b57", "head2": "#2c1423", "bub_pip": "#4a2039", "bub_you": "#ff8fb1",
             "on_accent": "#2a0f1f"},
    "Blue": {"body": "#3868a8", "body_hi": "#5f94d6", "bg": "#0b1626", "chat_bg": "#0f1d33", "card": "#14284a",
             "edge": "#274a80", "track": "#07101d", "ink": "#eaf3ff", "muted": "#8fb0d8", "violet": "#4d9bff",
             "lilac": "#1c3560", "pink": "#6ec6ff", "lav": "#a8d0ff", "lav_dk": "#548bd0", "halo": "#183563",
             "head1": "#1f4a8a", "head2": "#0f1d33", "bub_pip": "#1c3560", "bub_you": "#6ec6ff",
             "on_accent": "#081a30"},
    "Mint": {"body": "#2f7d68", "body_hi": "#5cb99b", "bg": "#0a1a15", "chat_bg": "#0e221b", "card": "#133328",
             "edge": "#24604b", "track": "#06110d", "ink": "#eafff5", "muted": "#8fc4af", "violet": "#34c78f",
             "lilac": "#1a4435", "pink": "#7fe8be", "lav": "#a9e5cf", "lav_dk": "#4aab88", "halo": "#164b3a",
             "head1": "#1f6b50", "head2": "#0e221b", "bub_pip": "#1a4435", "bub_you": "#7fe8be",
             "on_accent": "#06241a"},
    "Daylight": {"body": "#3d3b73", "body_hi": "#57539c", "bg": "#fff6fb", "chat_bg": "#fbf7ff", "card": "#ffffff",
                 "edge": "#eadff8", "track": "#e7defa", "ink": "#2d2640", "muted": "#8a7fa0", "violet": "#7c5cd6",
                 "lilac": "#efe6ff", "pink": "#ff8fb1", "lav": "#c8a8ff", "lav_dk": "#8e6fd1", "halo": "#fff4fa",
                 "head1": "#ffd9ec", "head2": "#e5dcff", "bub_pip": "#ece3ff", "bub_you": "#ffdcea",
                 "on_accent": "#2d2640"},
}


def apply_theme(name, refresh=True):
    """Apply a saved palette to Pip, the chat, and future windows."""
    global THEME_NAME, BODY, BODY_HI, BG, CHAT_BG, INK, MUTED, VIOLET, LILAC, PINK, LAV, LAV_DK
    global CARD_BG, EDGE, TRACK, HALO, HEAD1, HEAD2, BUB_PIP, BUB_YOU, ON_ACCENT
    theme = THEMES.get(name, THEMES["Lavender"])
    THEME_NAME = name if name in THEMES else "Lavender"
    BODY, BODY_HI = theme["body"], theme["body_hi"]
    BG, CHAT_BG = theme["bg"], theme["chat_bg"]
    CARD_BG, EDGE, TRACK, HALO = theme["card"], theme["edge"], theme["track"], theme["halo"]
    HEAD1, HEAD2 = theme["head1"], theme["head2"]
    BUB_PIP, BUB_YOU, ON_ACCENT = theme["bub_pip"], theme["bub_you"], theme["on_accent"]
    INK, MUTED = theme["ink"], theme["muted"]
    VIOLET, LILAC, PINK = theme["violet"], theme["lilac"], theme["pink"]
    LAV, LAV_DK = theme["lav"], theme["lav_dk"]
    data["theme"] = THEME_NAME
    save_data()

    # The desktop pet is redrawn on every animation tick using the active palette.
    try:
        pet.configure(bg=KEY)
        c.configure(bg=KEY)
    except (NameError, tk.TclError):
        pass

    # Rebuild the chat so every widget uses the selected colors immediately.
    if refresh and alive(chat_win):
        try:
            chat_win.destroy()
        except tk.TclError:
            pass
        root.after(80, lambda: open_chat(greet=False))


def open_customization():
    win = tk.Toplevel(root)
    win.title("Customize Pip")
    win.geometry("360x440+220+100")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    win.after(350, lambda: alive(win) and win.attributes("-topmost", False))
    tk.Label(win, text="make pip yours", font=F(20, True), bg=BG, fg=INK).pack(pady=(20, 4))
    tk.Label(win, text="choose a color for pip and the app", font=F(10), bg=BG, fg=MUTED).pack(pady=(0, 16))
    choices = tk.Frame(win, bg=BG)
    choices.pack(fill="x", padx=24)
    for name, palette in THEMES.items():
        row = tk.Frame(choices, bg=BG)
        row.pack(fill="x", pady=4)
        swatch = tk.Canvas(row, width=28, height=28, bg=BG, highlightthickness=0)
        swatch.create_oval(3, 3, 25, 25, fill=palette["body_hi"], outline=palette["body"])
        swatch.pack(side="left", padx=(0, 10))
        selected = "  \u2713" if name == THEME_NAME else ""
        PillButton(row, name + selected, lambda n=name, w=win: (w.destroy(), apply_theme(n)),
                   bg=palette["lilac"], fg=palette["violet"], height=34, width=230,
                   font=F(10, True)).pack(side="left", fill="x", expand=True)
    tk.Label(win, text="your choice is saved automatically", font=F(9), bg=BG, fg=MUTED).pack(pady=14)


# ---------- Chat window ----------
def _focus_chat():
    try:
        chat_win.focus_force()
        chat_entry.focus_force()
    except tk.TclError:
        pass


def ensure_chat():
    if not alive(chat_win):
        open_chat(greet=False)


def greeting_direction():
    n = profile_name()
    if day_part() == "late night" and pending["kind"] is None:
        pending["kind"] = "reflect"
        return (f"(stage direction: {n} just clicked on you and it is late at night. Greet them gently by name and "
                "ask: what went right today, and what went wrong?)")
    s = (f"(stage direction: {n} just clicked on you. Greet them by name in character, fit the time of day, and "
         "ask how they're doing or invite them to start a walk or pick an activity.")
    op = open_tasks()
    if op:
        s += f" Also ask, casually, whether they have done this task yet: '{op[0]['text']}'."
    return s + ")"


def open_chat(greet=True):
    global chat_win, chat_view, chat_entry, mic_button, status_label, quest_label, level_label
    global todo_nudge, hud_cv
    todo_nudge = False
    if alive(chat_win):
        chat_win.deiconify()
        chat_win.lift()
        _focus_chat()
        return
    chat_win = win = tk.Toplevel(root)
    win.title(f"chat with {NAME}")
    win.geometry("480x850+60+10")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    win.after(400, lambda: alive(win) and win.attributes("-topmost", False))
    head = tk.Frame(win, bg=LILAC)
    head.pack(fill="x")
    make_avatar(head, 84, get_mood, LILAC, halo=HALO).pack(side="left", padx=(14, 8), pady=8)
    info = tk.Frame(head, bg=LILAC)
    info.pack(side="left", fill="x", expand=True)
    tk.Label(info, text=NAME, font=F(20, True), bg=LILAC, fg=INK, anchor="w").pack(fill="x")
    level_label = tk.Label(info, text="", font=F(10, True), bg=LILAC, fg=VIOLET, anchor="w")
    level_label.pack(fill="x")
    header_actions = tk.Frame(head, bg=LILAC)
    header_actions.pack(side="right", padx=(4, 10), pady=8)
    for n, (label, cmd, bgc, fgc) in enumerate((("journal", open_journal, VIOLET, "white"),
                                                 ("stats", open_stats, VIOLET, "white"),
                                                 ("customize", open_customization, CARD_BG, VIOLET),
                                                 ("wardrobe", open_wardrobe, CARD_BG, VIOLET))):
        PillButton(header_actions, label, cmd, bg=bgc, fg=fgc, height=30, pad=10,
                   font=F(8, True)).grid(row=n // 2, column=n % 2, padx=2, pady=2)
    hud_cv = tk.Canvas(win, height=104, bg=BG, highlightthickness=0)
    hud_cv.pack(fill="x", padx=12, pady=(8, 0))
    hud_cv.bind("<Configure>", lambda e: draw_hud())
    quest_label = tk.Label(win, text="", font=F(9, True), bg=CARD_BG, fg="#4b2fa8", wraplength=420, justify="left",
                           anchor="w", padx=12, pady=7, highlightthickness=2, highlightbackground=EDGE)
    quest_label.pack(fill="x", padx=12, pady=(6, 0))
    # bottom bars are packed first so they always stay visible
    tk.Checkbutton(win, text="voice on", variable=voice_var, bg=BG, fg=MUTED, font=F(9),
                   activebackground=BG, selectcolor=CARD_BG).pack(side="bottom", pady=(0, 6))
    bar = tk.Frame(win, bg=BG)
    bar.pack(side="bottom", fill="x", padx=12, pady=(0, 6))
    box, chat_entry = styled_entry(bar, width=14)
    box.pack(side="left", fill="x", expand=True)
    chat_entry.bind("<Return>", send_message)
    PillButton(bar, "Send", send_message, height=40, width=70, pad=10).pack(side="left", padx=(8, 0))
    mic_button = PillButton(bar, MIC_IDLE, start_listening, bg=PINK, fg=ON_ACCENT, height=40, width=96, pad=10)
    mic_button.pack(side="left", padx=(6, 0))
    chips = tk.Frame(win, bg=BG)
    chips.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
    for text, cmd in (("new quest", choose_activity), ("I'm back", im_back), ("my day", open_todo)):
        PillButton(chips, text, cmd, bg=LILAC, fg=VIOLET, height=32, pad=12, font=F(9, True)).pack(
            side="left", padx=3, expand=True)
    status_label = tk.Label(win, text="", font=(FONT, 9, "italic"), bg=BG, fg="#b36b00")
    status_label.pack(side="bottom")
    chat_view = ScrollFrame(win, CHAT_BG)
    chat_view.pack(fill="both", expand=True, padx=10, pady=8)
    update_quest_label()
    win.after(150, _focus_chat)
    if greet and not history:
        pip_reply(greeting_direction(), fact=pending["kind"] != "reflect")


# ---------- The penguin (silent: it uses gestures) ----------
def get_mood():
    if time.time() < joy_until:
        return "joy"
    if quest_calm():
        return "happy"          # you agreed to a quest: Pip calms down
    st = get_stage()
    if st >= 3: return "fuming"      # red, steaming, both hands up
    if st == 2: return "agony"       # raised hand, shaking, tears
    if st == 1: return "grumpy"      # fast blinking and shivering bursts
    return "meh" if active >= 0.5 * (LEVEL_AT + grace) else "happy"


def draw_pip(cv, cx, by, s, mood, t, look=(0.0, 0.0)):
    burst = (t % 6) < 1.5
    if mood == "fuming":
        shake = random.uniform(-3, 3)
    elif mood in ("grumpy", "agony") and burst:
        shake = random.uniform(-2, 2)
    else:
        shake = 0
    if mood in ("joy", "fuming"):
        bob = -abs(math.sin(t * 7)) * 8
    elif mood in ("happy", "meh"):
        bob = math.sin(t * 2) * 2
    else:
        bob = 0
    lx, ly = look
    fx, fy = lx * 4, ly * 3                       # the face turns a little toward the cursor
    body, hi = (RED, RED_HI) if mood == "fuming" else (BODY, BODY_HI)

    def X(x): return cx + shake + x * s
    def Y(y): return by + bob + y * s
    def oval(x1, y1, x2, y2, **kw): cv.create_oval(X(x1), Y(y1), X(x2), Y(y2), **kw)
    def poly(pts, **kw): cv.create_polygon([v for p in pts for v in (X(p[0]), Y(p[1]))], **kw)
    def line(x1, y1, x2, y2, **kw): cv.create_line(X(x1), Y(y1), X(x2), Y(y2), **kw)

    def star(x, y, r, fill):
        pts = []
        for i in range(8):
            ang = math.pi / 4 * i - math.pi / 2
            rad = r if i % 2 == 0 else r * 0.3
            pts.append((x + rad * math.cos(ang), y + rad * math.sin(ang)))
        poly(pts, fill=fill, outline="")

    # sparkles when Pip is in a good mood
    if mood in ("happy", "meh", "joy"):
        spots = [(-102, -150, "#ffe27a"), (104, -128, "#ff9fd0"), (86, -196, "#a8f0ff")]
        if mood == "joy":
            spots += [(-92, -196, "#ff9fd0"), (110, -170, "#ffe27a"), (-110, -110, "#a8f0ff")]
        for i, (sx, sy, col) in enumerate(spots):
            star(sx, sy, 7 + 3 * math.sin(t * 3 + i * 2), col)

    # chunky sneakers
    for sg in (-1, 1):
        oval(sg * 21 - 17, -8, sg * 21 + 17, 10, fill=PINK, outline="")
        oval(sg * 21 - 15, -16, sg * 21 + 15, 4, fill="white", outline="")
        line(sg * 21 - 8, -6, sg * 21 + 8, -6, fill=PINK, width=2)

    # soft ground shadow gives Pip a little more depth
    oval(-48, -9, 48, 4, fill="#b8a8c9", outline="", stipple="gray50")

    # unlocked cosmetic: hero cape (drawn behind the body)
    if worn("back") == "cape":
        poly([(-46, -140), (46, -140), (90, -26), (62, -12), (22, -22), (0, -12), (-22, -22), (-62, -12),
              (-90, -26)], fill="#e0445a", outline="#8f2236", width=2)

    # body with a darker lower edge, soft highlight and glossy shine for a rounded 3D-style look
    oval(-62, -172, 62, -8, fill=shade(body, 0.72), outline="")
    oval(-59, -176, 59, -10, fill=body, outline="")
    oval(-52, -163, -14, -105, fill=hi, outline="")
    oval(-47, -163, -31, -142, fill="#ffffff", outline="", stipple="gray50")
    oval(-40, -120, 40, -14, fill="#e8ddce", outline="")
    oval(-38, -124, 37, -17, fill=BELLY, outline="")
    oval(18, -111, 31, -57, fill="#ffffff", outline="", stipple="gray75")

    # unlocked cosmetic: cozy scarf
    if worn("neck") == "scarf":
        pts = [(-56, -98), (-30, -86), (0, -82), (30, -86), (56, -98)]
        cv.create_line(*[v for p in pts for v in (X(p[0]), Y(p[1]))], smooth=True, width=max(3, int(14 * s)),
                       fill="#ff6f91", capstyle="round")
        pts2 = [(px, py - 3) for px, py in pts]
        cv.create_line(*[v for p in pts2 for v in (X(p[0]), Y(p[1]))], smooth=True, width=max(1, int(3 * s)),
                       fill="#ffb3c6", capstyle="round")
        poly([(20, -86), (44, -80), (50, -44), (28, -40)], fill="#e04a74", outline="")

    # flippers: gestures live here
    sway = math.sin(t * 2) * 3 if mood in ("happy", "meh") else 0
    wl = math.sin(t * 7) * 8
    wr = math.sin(t * 7 + math.pi) * 8
    if mood in ("fuming", "joy"):
        poly([(-56, -122), (-82 + wl, -174), (-96 + wl, -158), (-62, -100)], fill=body, outline="")
    else:
        poly([(-56, -115), (-88 - sway, -78), (-76 - sway, -54), (-52, -92)], fill=body, outline="")
    if mood in ("fuming", "joy"):
        poly([(56, -122), (82 + wr, -174), (96 + wr, -158), (62, -100)], fill=body, outline="")
    elif mood == "agony":
        w = math.sin(t * 6) * 8
        poly([(56, -122), (82 + w, -174), (96 + w, -158), (62, -100)], fill=body, outline="")
    else:
        poly([(56, -115), (88 + sway, -78), (76 + sway, -54), (52, -92)], fill=body, outline="")

    # steam when fuming
    if mood == "fuming":
        for i in range(3):
            ph = (t * 1.3 + i / 3) % 1
            px = -30 + 30 * i + math.sin(t * 3 + i) * 4
            py = -182 - ph * 46
            r = 6 + ph * 8
            oval(px - r, py - r, px + r, py + r, fill="#f4f4f4", outline="", stipple="gray50")

    # oversized headphones
    cv.create_arc(X(-54), Y(-176), X(54), Y(-116), start=0, extent=180, style="arc",
                  outline=LAV, width=max(2, int(8 * s)))
    for sg in (-1, 1):
        oval(sg * 55 - 13, -166, sg * 55 + 13, -124, fill=LAV, outline=LAV_DK, width=2)
        oval(sg * 55 - 7, -156, sg * 55 + 7, -134, fill=LAV_DK, outline="")

    # unlocked cosmetics for the head: party hat or golden crown
    head_item = worn("head")
    if head_item == "partyhat":
        poly([(-24, -168), (24, -168), (6, -232)], fill="#ffd966", outline="#e0b43a", width=2)
        line(-14, -190, 18, -190, fill="#ff8fb1", width=3)
        line(-5, -208, 13, -208, fill="#ff8fb1", width=3)
        oval(-2, -241, 14, -225, fill="#ff8fb1", outline="")
    elif head_item == "crown":
        poly([(-30, -166), (-30, -204), (-15, -186), (0, -210), (15, -186), (30, -204), (30, -166)],
             fill="#ffd34d", outline="#c99a10", width=2)
        oval(-4, -207, 4, -199, fill="#5ab8ff", outline="")
        oval(-35, -209, -26, -200, fill="#ff5a7a", outline="")
        oval(26, -209, 35, -200, fill="#ff5a7a", outline="")

    # eyes (pupils follow the cursor)
    if mood == "grumpy" and burst:
        blinking = int(t * 8) % 2 == 0
    else:
        blinking = mood in ("happy", "meh") and (t % 4.0) < 0.15
    for ex in (-20, 20):
        sg = 1 if ex < 0 else -1                     # points toward the center of the face
        exf = ex + fx
        inner, outer = exf + 13 * sg, exf - 13 * sg
        if mood == "joy":
            cv.create_arc(X(exf - 9), Y(-144 + fy), X(exf + 9), Y(-126 + fy), start=0, extent=180,
                          style="arc", outline="white", width=3)
            continue
        if blinking:
            line(exf - 9, -136 + fy, exf + 9, -136 + fy, fill="white", width=3)
            continue
        oval(exf - 12, -150 + fy, exf + 12, -124 + fy, fill="white", outline="")
        oval(exf - 8 + lx * 3, -147 + fy + ly * 3, exf + 8 + lx * 3, -127 + fy + ly * 3, fill="#16162b", outline="")
        oval(exf - 5 + lx * 3, -145 + fy + ly * 3, exf - 1 + lx * 3, -141 + fy + ly * 3, fill="white", outline="")
        oval(exf + 2 + lx * 3, -137 + fy + ly * 3, exf + 5 + lx * 3, -134 + fy + ly * 3, fill="white", outline="")
        if mood in ("grumpy", "fuming"):
            poly([(outer, -154 + fy), (inner, -154 + fy), (inner, -138 + fy), (outer, -147 + fy)],
                 fill=body, outline="")
            line(outer, -158 + fy, inner, -151 + fy, fill="#ffe8e8" if mood == "fuming" else "#e8dcff",
                 width=4 if mood == "fuming" else 3)
        elif mood == "agony":
            line(outer, -152 + fy, inner, -160 + fy, fill="#e8dcff", width=3)
            drip = (t * 24) % 16
            line(exf, -124 + fy, exf, -112 + fy + drip, fill="#8fd3ff", width=4)
            oval(exf - 4, -112 + fy + drip, exf + 4, -104 + fy + drip, fill="#8fd3ff", outline="")

    # blush, beak, smile
    cheek = "#ff5a5a" if mood == "fuming" else BLUSH
    oval(-50 + fx, -124 + fy, -32 + fx, -111 + fy, fill=cheek, outline="")
    oval(32 + fx, -124 + fy, 50 + fx, -111 + fy, fill=cheek, outline="")
    poly([(-13 + fx, -122 + fy), (13 + fx, -122 + fy), (fx, -100 + fy)], fill=PEACH, outline="")
    if mood in ("happy", "joy"):
        cv.create_arc(X(-8 + fx), Y(-106 + fy), X(8 + fx), Y(-90 + fy), start=200, extent=140,
                      style="arc", outline="#c25a3a", width=2)


def animate():
    t = time.time()
    try:
        px, py = pet.winfo_pointerxy()
        dx = px - (pet.winfo_rootx() + W / 2)
        dy = py - (pet.winfo_rooty() + H * 0.6)
        dist = math.hypot(dx, dy) or 1.0
        k = min(1.0, dist / 250)
        look = (dx / dist * k, dy / dist * k)
    except tk.TclError:
        look = (0.0, 0.0)
    c.delete("all")
    s = min(0.9, 0.42 + 0.06 * quests_done)          # teeny tiny at first, bigger with every quest
    draw_pip(c, W / 2, H - FOOT, s, get_mood(), t, look)
    draw_nameplate()
    badge = None                                     # a silent "look at me" badge above Pip's head
    if get_stage() >= 2 and not locked:
        badge = ("!", DANGER)
    elif todo_nudge:
        badge = ("?", VIOLET)
    if badge:
        bx, byy = W / 2 + 66 * s, H - FOOT - 190 * s
        r = 11 + 2 * math.sin(t * 6)
        c.create_oval(bx - r, byy - r, bx + r, byy + r, fill=badge[1], outline="white", width=2)
        c.create_text(bx, byy, text=badge[0], fill="white", font=F(11, True))
    root.after(60, animate)


last_tick = [time.time()]


def tick():
    try:
        _tick()
    except Exception as exc:
        print("Pip timer error:", exc)
    finally:
        root.after(1000, tick)       # always reschedule: one error must never freeze the timer again


def track_away(q, idle, dt, live):
    """Total seconds really spent away from the screen during this quest (kept in q["away_max"] by the caller).
    Counts only while there is no keyboard/mouse input for 3s AND the camera has not seen a face for 3s."""
    seen_recently = live and time.time() - presence["last_seen"] < 3
    if idle >= 3 and not seen_recently:
        q["total"] = q.get("total", 0.0) + dt
    return q.get("total", 0.0)


def _tick():
    global active, warned, last_weather, todo_timer, todo_nudge
    now = time.time()
    dt = max(0.0, min(now - last_tick[0], 5.0))      # real elapsed time, so a busy UI can't slow the clock
    last_tick[0] = now
    idle = get_idle_seconds()
    away_now = effective_away(idle)       # camera has the final say when it can see you
    live = cam_live()
    if quest is not None:
        quest["away_max"] = max(quest["away_max"], track_away(quest, idle, dt, live))
    presence["blind"] = bool(live and idle < 3 and now - max(presence["last_seen"], presence["cam_since"]) > 120)
    st = day_stats()
    if live and now - presence["last_seen"] < 3:
        st["face_s"] += dt
    nb = presence["blinks"]
    if nb > blink_seen[0]:
        st["blink_n"] += nb - blink_seen[0]
    blink_seen[0] = nb
    if away_now < IDLE_RESET:
        on_break["on"], on_break["len"] = False, 0
        if not locked:
            if not quest_calm():          # the clock waits while you are out on a quest
                active += dt
            st["screen"] += dt
            check_reminders(dt)
    else:                                 # a real break (watching a video without touching the mouse is not one)
        if not on_break["on"]:
            on_break["on"] = True
            if active >= 0.25 * LEVEL_AT:
                st["breaks"] += 1
            st["away"] += IDLE_RESET
        on_break["len"] += dt
        if on_break["len"] <= 1800:       # cap so a PC left on overnight doesn't inflate "away"
            st["away"] += dt
        reset_timers()                    # a real break resets everything
    stage = get_stage()
    if stage >= 3 and not warned and not locked:
        warned = True
        show_warning()
    if stage >= 4 and not locked:
        lock_screen()
    if open_tasks() and not locked:                              # Pip checks in about your tasks
        todo_timer += dt
        if todo_timer >= TODO_NAG:
            todo_nudge, todo_timer = True, 0
    update_warning()
    if time.time() - last_weather > 1800:
        last_weather = time.time()
        threading.Thread(target=fetch_weather, daemon=True).start()
    update_quest_label()
    tick_count[0] += 1
    if tick_count[0] % 30 == 0:
        prune_stats()
        save_data()


tick_count = [0]


# ---------- Real lock: block Win key / Alt+Tab / Alt+Esc / Alt+F4 / Ctrl+Esc while locked ----------
if os.name == "nt":
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wt.DWORD]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    def _kb_proc(nCode, wParam, lParam):
        if nCode >= 0 and locked:
            k = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            alt = bool(k.flags & 0x20)
            ctrl = bool(user32.GetAsyncKeyState(0x11) & 0x8000)
            if k.vkCode in (0x5B, 0x5C):                         # left/right Windows key
                return 1
            if alt and k.vkCode in (0x09, 0x1B, 0x73):           # Alt+Tab, Alt+Esc, Alt+F4
                return 1
            if ctrl and k.vkCode == 0x1B:                        # Ctrl+Esc (Start menu)
                return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    _kb_cb = HOOKPROC(_kb_proc)      # keep a reference or it gets garbage collected

    def _kb_thread():
        user32.SetWindowsHookExW(13, _kb_cb, kernel32.GetModuleHandleW(None), 0)
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


# Apply the user's saved color theme before creating the windows.
apply_theme(THEME_NAME, refresh=False)

# ---------- Window setup ----------
# A hidden main window owns everything. The penguin is its own see-through window, so the chat
# and other windows can take keyboard focus normally.
root = tk.Tk()
init_fonts()
root.withdraw()
pet = tk.Toplevel(root)
pet.title(NAME)
pet.overrideredirect(True)                   # no title bar
pet.attributes("-topmost", True)
pet.attributes("-transparentcolor", KEY)     # KEY-colored pixels are see-through
pet.configure(bg=KEY)
pet.protocol("WM_DELETE_WINDOW", quit_app)
sw, sh = pet.winfo_screenwidth(), pet.winfo_screenheight()
pet.geometry(f"{W}x{H}+{sw - W - 20}+{sh - H - 60}")
c = tk.Canvas(pet, width=W, height=H, bg=KEY, highlightthickness=0)
c.pack()
voice_var = tk.BooleanVar(master=root, value=True)
cam_var = tk.BooleanVar(master=root, value=cam_state["on"])

# ---------- Thread-safe UI calls: worker threads never touch Tkinter directly ----------
ui_queue = queue.Queue()


def ui_call(fn, delay_ms=0):
    """Call from any thread. The main thread runs fn after delay_ms."""
    ui_queue.put((int(delay_ms), fn))


def ui_pump():
    try:
        while True:
            delay, fn = ui_queue.get_nowait()
            if delay > 0:
                root.after(delay, lambda f=fn: _safe(f))
            else:
                _safe(fn)
    except queue.Empty:
        pass
    root.after(25, ui_pump)


def _safe(fn):
    try:
        fn()
    except Exception as exc:
        print("Pip UI error:", exc)


# click = open chat (Pip speaks), drag = move, right-click = menu
drag = {"x": 0, "y": 0, "wx": 0, "wy": 0, "moved": False}


def press(e):
    drag.update(x=e.x_root, y=e.y_root, wx=pet.winfo_x(), wy=pet.winfo_y(), moved=False)


def motion(e):
    dx, dy = e.x_root - drag["x"], e.y_root - drag["y"]
    if abs(dx) + abs(dy) > 4:
        drag["moved"] = True
    if drag["moved"]:
        pet.geometry(f"+{drag['wx'] + dx}+{drag['wy'] + dy}")


def release(e):
    global todo_nudge
    if drag["moved"]:
        return
    todo_nudge = False
    close_toast()
    if alive(chat_win):
        start_listening()      # chat already open: clicking Pip means "I'm going to talk"
    else:
        open_chat()


def set_active(x):
    global active
    active = int(x)


def test_grow():
    global quests_done, joy_until
    quests_done += 1
    joy_until = time.time() + 10
    save_data()
    show_levelup(pip_level(), grant_unlocks())


def reset_pet():
    global active, grace, grants_used, warned
    active, grace, grants_used, warned = 0, 0, 0, False
    close_warning()


def reset_growth():
    global quests_done
    quests_done = 0
    data["cosmetics_seen"] = []
    data["wardrobe"] = {}
    save_data()


def test_todo_nudge():
    global todo_nudge
    todo_nudge = True


def startup():
    threading.Thread(target=warm_up, daemon=True).start()
    threading.Thread(target=presence_loop, daemon=True).start()
    grant_unlocks()
    if os.name == "nt":
        threading.Thread(target=_kb_thread, daemon=True).start()
    if not data["profile"].get("name"):
        show_onboarding()
    else:
        show_greeting()


c.bind("<ButtonPress-1>", press)
c.bind("<B1-Motion>", motion)
c.bind("<ButtonRelease-1>", release)
menu = tk.Menu(pet, tearoff=0)
menu.add_command(label="Talk to Pip", command=open_chat)
menu.add_command(label="My day (to-do)", command=open_todo)
menu.add_command(label="Pip's journal", command=open_journal)
menu.add_command(label="Stats dashboard", command=open_stats)
menu.add_command(label="Wardrobe", command=open_wardrobe)
menu.add_checkbutton(label="Camera monitoring (away / blink / posture)", variable=cam_var, command=toggle_cam)
menu.add_command(label="Camera check (see what pip sees)", command=open_cam_test)
menu.add_command(label="Recalibrate posture (sit up straight first)", command=lambda: presence.update(recalibrate=True))
menu.add_checkbutton(label="Voice (only when I click Pip)", variable=voice_var)
menu.add_separator()
menu.add_command(label="Test: raised hand (30 min)", command=lambda: set_active(LEVEL_AT + grace))
menu.add_command(label="Test: fuming + warning (60 min)", command=lambda: set_active(2 * LEVEL_AT + grace))
menu.add_command(label="Test: lock now", command=lambda: set_active(2 * LEVEL_AT + grace + LOCK_WARN))
menu.add_command(label="Test: task check-in badge", command=test_todo_nudge)
menu.add_command(label="Test: calm down", command=reset_pet)
menu.add_command(label="Test: grow one level", command=test_grow)
menu.add_command(label="Test: eye-rest reminder", command=eye_rest)
menu.add_command(label="Test: posture reminder",
                 command=lambda: posture_reminder("test: sit up tall and relax your shoulders."))
menu.add_command(label="Test: blink reminder", command=lambda: blink_reminder(5))
menu.add_command(label="Reset growth to tiny", command=reset_growth)
menu.add_command(label="Show welcome screen", command=show_greeting)
menu.add_separator()
menu.add_command(label="Quit", command=quit_app)
c.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

animate()
tick()
ui_pump()
root.after(400, startup)
root.mainloop()