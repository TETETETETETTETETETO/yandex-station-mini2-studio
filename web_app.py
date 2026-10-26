"""
Alice Display Controller - Web Service
Interactive Web UI & REST API for Yandex Station Mini 2 LED Matrix & Individual RGB Ring
"""

import os
import sys
import time
import json
import queue
import threading
import subprocess
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder="templates", static_folder="static")

DEFAULT_ADB_TARGET = "192.168.3.6:5555"
DEFAULT_ADB_BIN = r"C:\Users\sguse\Desktop\platform-tools\adb.exe"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATTERNS_DIR = os.path.join(SCRIPT_DIR, "clock_patterns")
DICT_PATH = os.path.join(SCRIPT_DIR, "zstd.dict")

# 7-Segment Font Table
FONT = {
    '0': ['A', 'B', 'C', 'D', 'E', 'F'],
    '1': ['B', 'C'],
    '2': ['A', 'B', 'D', 'E', 'G'],
    '3': ['A', 'B', 'C', 'D', 'G'],
    '4': ['B', 'C', 'F', 'G'],
    '5': ['A', 'C', 'D', 'F', 'G'],
    '6': ['A', 'C', 'D', 'E', 'F', 'G'],
    '7': ['A', 'B', 'C'],
    '8': ['A', 'B', 'C', 'D', 'E', 'F', 'G'],
    '9': ['A', 'B', 'C', 'D', 'F', 'G'],
    ' ': [],
    '-': ['G'],
    '_': ['D'],
    '=': ['D', 'G'],
    'A': ['A', 'B', 'C', 'E', 'F', 'G'],
    'B': ['C', 'D', 'E', 'F', 'G'],
    'C': ['A', 'D', 'E', 'F'],
    'D': ['B', 'C', 'D', 'E', 'G'],
    'E': ['A', 'D', 'E', 'F', 'G'],
    'F': ['A', 'E', 'F', 'G'],
    'G': ['A', 'C', 'D', 'E', 'F'],
    'H': ['B', 'C', 'E', 'F', 'G'],
    'I': ['B', 'C'],
    'J': ['B', 'C', 'D', 'E'],
    'L': ['D', 'E', 'F'],
    'N': ['C', 'E', 'G'],
    'O': ['A', 'B', 'C', 'D', 'E', 'F'],
    'P': ['A', 'B', 'E', 'F', 'G'],
    'R': ['E', 'G'],
    'S': ['A', 'C', 'D', 'F', 'G'],
    'T': ['D', 'E', 'F', 'G'],
    'U': ['B', 'C', 'D', 'E', 'F'],
    'Y': ['B', 'C', 'D', 'F', 'G'],
    'Z': ['A', 'B', 'D', 'E', 'G'],
    '[': ['A', 'D', 'E', 'F'],
    ']': ['A', 'B', 'C', 'D'],
    '°': ['A', 'B', 'F', 'G'],
}

ALL_SEGMENTS = []
for d in (1, 2, 3, 4):
    for s in ('A', 'B', 'C', 'D', 'E', 'F', 'G'):
        ALL_SEGMENTS.append(f"{s}{d}")
ALL_SEGMENTS.extend(["PLUS1", "PLUS2", "PLUS3", "PLUS4", "MINUS", "DEGREE"])

CHANNEL_MAP = [
    # Digit 1
    "clockG1", "clockA1", "clockB1", "clockC1", "clockD1", "clockE1", "clockF1",
    # Digit 2
    "clockG2", "clockA2", "clockB2", "clockC2", "clockD2", "clockE2", "clockF2",
    # Symbols
    "clockMINUS", "clockPLUS1", "clockPLUS2", "clockPLUS3", "clockPLUS4", "", "",
    # Digit 3
    "clockG3", "clockA3", "clockB3", "clockC3", "clockD3", "clockE3", "clockF3",
    # Digit 4 + Degree
    "clockG4", "clockA4", "clockB4", "clockDEGREE", "clockC4", "clockD4",
]


class AdbBridge:
    def __init__(self, target=DEFAULT_ADB_TARGET, adb_bin=DEFAULT_ADB_BIN):
        self.target = target
        self.adb_bin = adb_bin
        self.proc = None
        self.cmd_queue = queue.Queue(maxsize=300)
        self.lock = threading.Lock()
        self.connected = False
        self._ensure_proc()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _ensure_proc(self):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                try:
                    subprocess.run([self.adb_bin, "connect", self.target],
                                   capture_output=True, timeout=4)
                    self.proc = subprocess.Popen(
                        [self.adb_bin, "-s", self.target, "shell"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        bufsize=1
                    )
                    self.connected = True
                    print("[ADB] Shell pipe connected.")
                except Exception as e:
                    print(f"[ADB] Connection error: {e}")
                    self.connected = False
                    self.proc = None

    def _worker_loop(self):
        while True:
            try:
                cmd = self.cmd_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            self._ensure_proc()
            if self.proc and self.proc.stdin:
                try:
                    self.proc.stdin.write(cmd + "\n")
                    self.proc.stdin.flush()
                except Exception as e:
                    print(f"[ADB] Write error: {e}")
                    self.proc = None
                    self.connected = False
            self.cmd_queue.task_done()

    def execute_raw(self, shell_cmd):
        try:
            self.cmd_queue.put_nowait(shell_cmd)
        except queue.Full:
            pass

    def execute_batch(self, commands):
        if commands:
            self.execute_raw(" ; ".join(commands))

    def clear_pending(self):
        while not self.cmd_queue.empty():
            try:
                self.cmd_queue.get_nowait()
                self.cmd_queue.task_done()
            except queue.Empty:
                break


class DisplayManager:
    def __init__(self, bridge):
        self.bridge = bridge
        self.current_state = {seg: 0 for seg in ALL_SEGMENTS}
        self.brightness = 150
        
        # 6 individual RGB LEDs for top ring (index 0..5 corresponds to ring 1..6)
        self.ring_leds = [{"r": 0, "g": 0, "b": 0} for _ in range(6)]
        
        # Lock mode: when True, Alice daemon is kept frozen to prevent clock overwrite!
        self.screen_locked = True
        self.daemon_frozen = True
        
        self.anim_thread = None
        self.ring_anim_thread = None
        self.stop_anim_flag = threading.Event()
        self.stop_ring_anim_flag = threading.Event()
        
        # Auto-freeze daemon right at start so user drawings are never overwritten!
        self.ensure_daemon_lock()
        
        # Background watchdog to keep daemon frozen and screen content retained
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self.watchdog_thread.start()

    def ensure_daemon_lock(self):
        """Freezes maind to prevent it from ever overwriting the screen with time."""
        if self.screen_locked:
            self.daemon_frozen = True
            self.bridge.execute_raw("killall -STOP maind")

    def _watchdog_loop(self):
        """Ensures that while in custom drawing mode, the station clock never overwrites."""
        while True:
            time.sleep(15.0)
            if self.screen_locked:
                # Re-assert STOP signal periodically
                self.bridge.execute_raw("killall -STOP maind")

    def set_mode(self, mode):
        """'custom' (clock frozen) or 'alice' (clock active)"""
        if mode == "custom":
            self.screen_locked = True
            self.daemon_frozen = True
            self.bridge.execute_raw("killall -STOP maind")
        else:
            self.screen_locked = False
            self.daemon_frozen = False
            self.stop_animation()
            self.bridge.execute_raw("killall -CONT maind")

    def set_brightness(self, val):
        self.brightness = max(0, min(255, int(val)))

    def set_single_segment(self, seg_name, val):
        self.ensure_daemon_lock()
        val = int(val)
        if seg_name in self.current_state:
            self.current_state[seg_name] = val
        self.bridge.execute_raw(f"echo {val} > /sys/class/leds/mini2:white:clock{seg_name}/brightness")

    def toggle_segment(self, seg_name):
        self.ensure_daemon_lock()
        self.stop_animation()
        current = self.current_state.get(seg_name, 0)
        new_val = 0 if current > 0 else self.brightness
        self.set_single_segment(seg_name, new_val)
        return new_val

    def clear(self):
        self.ensure_daemon_lock()
        self.stop_animation()
        self.bridge.clear_pending()
        for s in self.current_state:
            self.current_state[s] = 0
        self.bridge.execute_raw("for l in /sys/class/leds/mini2:white:clock*; do echo 0 > $l/brightness; done")

    def all_on(self):
        self.ensure_daemon_lock()
        self.stop_animation()
        self.bridge.clear_pending()
        for s in self.current_state:
            self.current_state[s] = self.brightness
        self.bridge.execute_raw(f"for l in /sys/class/leds/mini2:white:clock*; do echo {self.brightness} > $l/brightness; done")

    def show_text(self, text, colon=False, degree=False):
        self.ensure_daemon_lock()
        self.stop_animation()
        self.bridge.clear_pending()
        text_clean = ""
        has_colon = colon
        has_degree = degree

        for ch in text:
            if ch == ':':
                has_colon = True
            elif ch in ('°', '*'):
                has_degree = True
            else:
                text_clean += ch

        chars = list(text_clean.rjust(4))[-4:]
        new_state = {s: 0 for s in ALL_SEGMENTS}

        for idx, char in enumerate(chars, start=1):
            segs = FONT.get(char.upper(), [])
            for seg in segs:
                new_state[f"{seg}{idx}"] = self.brightness

        if has_colon:
            new_state["PLUS1"] = self.brightness
            new_state["PLUS2"] = self.brightness
        if has_degree:
            new_state["DEGREE"] = self.brightness

        cmds = ["for l in /sys/class/leds/mini2:white:clock*; do echo 0 > $l/brightness; done"]
        for s, val in new_state.items():
            if val > 0:
                cmds.append(f"echo {val} > /sys/class/leds/mini2:white:clock{s}/brightness")

        self.current_state = new_state
        self.bridge.execute_batch(cmds)

    def start_scroll(self, text, speed=0.25):
        self.ensure_daemon_lock()
        self.stop_animation()
        self.stop_anim_flag.clear()

        def _runner():
            padded = "    " + text + "    "
            while not self.stop_anim_flag.is_set():
                for i in range(len(padded) - 3):
                    if self.stop_anim_flag.is_set():
                        break
                    window = padded[i:i+4]
                    self._show_text_internal(window)
                    time.sleep(speed)
                time.sleep(0.5)

        self.anim_thread = threading.Thread(target=_runner, daemon=True)
        self.anim_thread.start()

    def _show_text_internal(self, text):
        chars = list(text.rjust(4))[-4:]
        new_state = {s: 0 for s in ALL_SEGMENTS}
        for idx, char in enumerate(chars, start=1):
            segs = FONT.get(char.upper(), [])
            for seg in segs:
                new_state[f"{seg}{idx}"] = self.brightness

        cmds = ["for l in /sys/class/leds/mini2:white:clock*; do echo 0 > $l/brightness; done"]
        for s, val in new_state.items():
            if val > 0:
                cmds.append(f"echo {val} > /sys/class/leds/mini2:white:clock{s}/brightness")
        self.current_state = new_state
        self.bridge.execute_batch(cmds)

    def stop_animation(self):
        self.stop_anim_flag.set()
        if self.anim_thread and self.anim_thread.is_alive():
            self.anim_thread.join(timeout=0.2)
        self.anim_thread = None
        self.bridge.clear_pending()

    # --- Individual RGB Ring Controls ---

    def set_ring_led(self, led_idx, r, g, b):
        """Set a single LED (1..6) on the top ring."""
        self.stop_ring_animation()
        idx = int(led_idx) - 1
        if 0 <= idx < 6:
            r, g, b = int(r), int(g), int(b)
            self.ring_leds[idx] = {"r": r, "g": g, "b": b}
            num = idx + 1
            cmds = [
                f"echo {r} > /sys/class/leds/mini2:red:ring{num}/brightness",
                f"echo {g} > /sys/class/leds/mini2:green:ring{num}/brightness",
                f"echo {b} > /sys/class/leds/mini2:blue:ring{num}/brightness",
            ]
            self.bridge.execute_batch(cmds)

    def set_all_ring_leds(self, leds_list):
        """Set all 6 LEDs with a list of [{'r':..,'g':..,'b':..}, ...]"""
        self.stop_ring_animation()
        cmds = []
        for idx, item in enumerate(leds_list[:6]):
            r = int(item.get("r", 0))
            g = int(item.get("g", 0))
            b = int(item.get("b", 0))
            self.ring_leds[idx] = {"r": r, "g": g, "b": b}
            num = idx + 1
            cmds.extend([
                f"echo {r} > /sys/class/leds/mini2:red:ring{num}/brightness",
                f"echo {g} > /sys/class/leds/mini2:green:ring{num}/brightness",
                f"echo {b} > /sys/class/leds/mini2:blue:ring{num}/brightness",
            ])
        self.bridge.execute_batch(cmds)

    def apply_ring_gradient(self, preset_name):
        """Built-in gradients for 6 LEDs."""
        self.stop_ring_animation()
        presets = {
            "rainbow": [
                {"r": 255, "g": 0, "b": 0},      # Red
                {"r": 255, "g": 180, "b": 0},    # Yellow
                {"r": 0, "g": 255, "b": 0},      # Green
                {"r": 0, "g": 255, "b": 255},    # Cyan
                {"r": 0, "g": 0, "b": 255},      # Blue
                {"r": 220, "g": 0, "b": 255},    # Purple
            ],
            "sunset": [
                {"r": 180, "g": 0, "b": 220},    # Deep Violet
                {"r": 255, "g": 20, "b": 140},   # Magenta
                {"r": 255, "g": 60, "b": 20},    # Red-Orange
                {"r": 255, "g": 140, "b": 0},    # Orange
                {"r": 255, "g": 220, "b": 0},    # Yellow-Gold
                {"r": 255, "g": 70, "b": 100},   # Pink
            ],
            "cyberpunk": [
                {"r": 0, "g": 255, "b": 255},    # Neon Cyan
                {"r": 0, "g": 160, "b": 255},    # Sky Blue
                {"r": 80, "g": 0, "b": 255},     # Deep Blue
                {"r": 200, "g": 0, "b": 255},    # Purple
                {"r": 255, "g": 0, "b": 180},    # Hot Pink
                {"r": 0, "g": 255, "b": 200},    # Mint
            ],
            "aurora": [
                {"r": 0, "g": 255, "b": 100},
                {"r": 0, "g": 255, "b": 220},
                {"r": 0, "g": 180, "b": 255},
                {"r": 0, "g": 255, "b": 160},
                {"r": 40, "g": 255, "b": 100},
                {"r": 0, "g": 200, "b": 255},
            ],
            "fire": [
                {"r": 255, "g": 20, "b": 0},
                {"r": 255, "g": 70, "b": 0},
                {"r": 255, "g": 150, "b": 0},
                {"r": 255, "g": 220, "b": 0},
                {"r": 255, "g": 100, "b": 0},
                {"r": 200, "g": 10, "b": 0},
            ]
        }
        grad = presets.get(preset_name, presets["rainbow"])
        self.set_all_ring_leds(grad)
        return grad

    def start_ring_animation(self, mode="spin", speed=0.15):
        """Spin, pulse or comet animations for the RGB ring."""
        self.stop_ring_animation()
        self.stop_ring_anim_flag.clear()

        def _ring_runner():
            if mode == "spin":
                current_palette = [dict(c) for c in self.ring_leds]
                # If all leds are black, start with rainbow
                if all(c["r"] == 0 and c["g"] == 0 and c["b"] == 0 for c in current_palette):
                    current_palette = self.apply_ring_gradient("rainbow")
                while not self.stop_ring_anim_flag.is_set():
                    # Rotate array by 1
                    current_palette = [current_palette[-1]] + current_palette[:-1]
                    cmds = []
                    for idx, c in enumerate(current_palette):
                        num = idx + 1
                        cmds.extend([
                            f"echo {c['r']} > /sys/class/leds/mini2:red:ring{num}/brightness",
                            f"echo {c['g']} > /sys/class/leds/mini2:green:ring{num}/brightness",
                            f"echo {c['b']} > /sys/class/leds/mini2:blue:ring{num}/brightness",
                        ])
                    self.ring_leds = [dict(c) for c in current_palette]
                    self.bridge.execute_batch(cmds)
                    time.sleep(speed)

            elif mode == "comet":
                pos = 0
                while not self.stop_ring_anim_flag.is_set():
                    cmds = []
                    for idx in range(6):
                        dist = (idx - pos) % 6
                        # comet tail falloff: head=255, tail=120, 40, 0
                        factor = [1.0, 0.45, 0.15, 0.0, 0.0, 0.0][dist]
                        r = int(0 * factor)
                        g = int(255 * factor)
                        b = int(255 * factor)
                        self.ring_leds[idx] = {"r": r, "g": g, "b": b}
                        num = idx + 1
                        cmds.extend([
                            f"echo {r} > /sys/class/leds/mini2:red:ring{num}/brightness",
                            f"echo {g} > /sys/class/leds/mini2:green:ring{num}/brightness",
                            f"echo {b} > /sys/class/leds/mini2:blue:ring{num}/brightness",
                        ])
                    pos = (pos + 1) % 6
                    self.bridge.execute_batch(cmds)
                    time.sleep(speed)

            elif mode == "pulse":
                base_palette = [dict(c) for c in self.ring_leds]
                if all(c["r"] == 0 and c["g"] == 0 and c["b"] == 0 for c in base_palette):
                    base_palette = self.apply_ring_gradient("cyberpunk")
                step = 0
                while not self.stop_ring_anim_flag.is_set():
                    import math
                    brightness_mult = (math.sin(step) + 1.0) / 2.0 * 0.85 + 0.15
                    step += 0.2
                    cmds = []
                    for idx, c in enumerate(base_palette):
                        num = idx + 1
                        r = int(c["r"] * brightness_mult)
                        g = int(c["g"] * brightness_mult)
                        b = int(c["b"] * brightness_mult)
                        self.ring_leds[idx] = {"r": r, "g": g, "b": b}
                        cmds.extend([
                            f"echo {r} > /sys/class/leds/mini2:red:ring{num}/brightness",
                            f"echo {g} > /sys/class/leds/mini2:green:ring{num}/brightness",
                            f"echo {b} > /sys/class/leds/mini2:blue:ring{num}/brightness",
                        ])
                    self.bridge.execute_batch(cmds)
                    time.sleep(speed)

        self.ring_anim_thread = threading.Thread(target=_ring_runner, daemon=True)
        self.ring_anim_thread.start()

    def stop_ring_animation(self):
        self.stop_ring_anim_flag.set()
        if self.ring_anim_thread and self.ring_anim_thread.is_alive():
            self.ring_anim_thread.join(timeout=0.2)
        self.ring_anim_thread = None

    def play_pattern(self, name, loops=1):
        self.ensure_daemon_lock()
        self.stop_animation()
        self.stop_anim_flag.clear()

        raw_path = os.path.join(PATTERNS_DIR, name)
        if not os.path.exists(raw_path):
            raw_path = os.path.join(PATTERNS_DIR, name + ".binscled")
        if not os.path.exists(raw_path):
            raw_path = os.path.join(PATTERNS_DIR, name + ".binscled.zst")

        if not os.path.exists(raw_path):
            return False, f"Pattern not found: {name}"

        data = None
        if raw_path.endswith(".zst"):
            import zstandard as zstd
            with open(DICT_PATH, "rb") as df:
                dctx = zstd.ZstdDecompressor(dict_data=zstd.ZstdCompressionDict(df.read()))
            with open(raw_path, "rb") as f:
                data = dctx.decompress(f.read(), max_output_size=10*1024*1024)
        else:
            with open(raw_path, "rb") as f:
                data = f.read()

        num_frames = len(data) // 35

        def _play_runner():
            prev_frame = [0] * 34
            for _ in range(loops):
                for i in range(num_frames):
                    if self.stop_anim_flag.is_set():
                        return
                    frame = data[i*35:(i+1)*35]
                    duration = max(30, int(frame[34] or 20))
                    cmds = []
                    frame_state = dict(self.current_state)
                    for ch, val in enumerate(frame[:34]):
                        if val != prev_frame[ch]:
                            prev_frame[ch] = val
                            if ch < len(CHANNEL_MAP) and CHANNEL_MAP[ch]:
                                s_name = CHANNEL_MAP[ch].replace("clock", "")
                                frame_state[s_name] = val
                                cmds.append(f"echo {val} > /sys/class/leds/mini2:white:clock{s_name}/brightness")
                    self.current_state = frame_state
                    if cmds:
                        self.bridge.execute_batch(cmds)
                    time.sleep(duration / 1000.0)

        self.anim_thread = threading.Thread(target=_play_runner, daemon=True)
        self.anim_thread.start()
        return True, f"Started playback of {num_frames} frames"


bridge = AdbBridge()
disp = DisplayManager(bridge)


# --- API Routes ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    return jsonify({
        "connected": bridge.connected,
        "target": bridge.target,
        "brightness": disp.brightness,
        "screen_locked": disp.screen_locked,
        "daemon_frozen": disp.daemon_frozen,
        "segments": disp.current_state,
        "ring_leds": disp.ring_leds,
        "ring_animating": disp.ring_anim_thread is not None and disp.ring_anim_thread.is_alive()
    })

@app.route("/api/mode", methods=["POST"])
def api_mode():
    data = request.json or {}
    mode = data.get("mode", "custom")
    disp.set_mode(mode)
    return jsonify({"status": "ok", "mode": mode, "screen_locked": disp.screen_locked})

@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    data = request.json or {}
    seg = data.get("segment")
    if not seg or seg not in ALL_SEGMENTS:
        return jsonify({"error": "Invalid segment"}), 400
    new_val = disp.toggle_segment(seg)
    return jsonify({"segment": seg, "value": new_val})

@app.route("/api/segment", methods=["POST"])
def api_segment():
    data = request.json or {}
    seg = data.get("segment")
    val = data.get("value", disp.brightness)
    if not seg or seg not in ALL_SEGMENTS:
        return jsonify({"error": "Invalid segment"}), 400
    disp.set_single_segment(seg, val)
    return jsonify({"segment": seg, "value": val})

@app.route("/api/brightness", methods=["POST"])
def api_brightness():
    data = request.json or {}
    val = data.get("value", 150)
    disp.set_brightness(val)
    return jsonify({"brightness": disp.brightness})

@app.route("/api/text", methods=["POST"])
def api_text():
    data = request.json or {}
    text = str(data.get("text", ""))
    colon = bool(data.get("colon", False))
    degree = bool(data.get("degree", False))
    disp.show_text(text, colon=colon, degree=degree)
    return jsonify({"status": "ok", "text": text, "state": disp.current_state})

@app.route("/api/scroll", methods=["POST"])
def api_scroll():
    data = request.json or {}
    text = str(data.get("text", ""))
    speed = float(data.get("speed", 0.25))
    disp.start_scroll(text, speed=speed)
    return jsonify({"status": "scrolling", "text": text})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    disp.stop_animation()
    return jsonify({"status": "stopped"})

@app.route("/api/clear", methods=["POST"])
def api_clear():
    disp.clear()
    return jsonify({"status": "cleared", "state": disp.current_state})

@app.route("/api/all", methods=["POST"])
def api_all():
    disp.all_on()
    return jsonify({"status": "all_on", "state": disp.current_state})

# --- RGB Ring Endpoints ---

@app.route("/api/ring/led", methods=["POST"])
def api_ring_led():
    data = request.json or {}
    led = data.get("led", 1)
    r = data.get("r", 0)
    g = data.get("g", 0)
    b = data.get("b", 0)
    disp.set_ring_led(led, r, g, b)
    return jsonify({"status": "ok", "ring_leds": disp.ring_leds})

@app.route("/api/ring/all_leds", methods=["POST"])
def api_ring_all_leds():
    data = request.json or {}
    leds = data.get("leds", [])
    disp.set_all_ring_leds(leds)
    return jsonify({"status": "ok", "ring_leds": disp.ring_leds})

@app.route("/api/ring/gradient", methods=["POST"])
def api_ring_gradient():
    data = request.json or {}
    name = data.get("name", "rainbow")
    grad = disp.apply_ring_gradient(name)
    return jsonify({"status": "ok", "gradient": name, "ring_leds": grad})

@app.route("/api/ring/animate", methods=["POST"])
def api_ring_animate():
    data = request.json or {}
    mode = data.get("mode", "spin")
    speed = float(data.get("speed", 0.15))
    disp.start_ring_animation(mode=mode, speed=speed)
    return jsonify({"status": "ok", "mode": mode})

@app.route("/api/ring/stop", methods=["POST"])
def api_ring_stop():
    disp.stop_ring_animation()
    return jsonify({"status": "stopped"})

@app.route("/api/patterns")
def api_patterns():
    files = []
    if os.path.exists(PATTERNS_DIR):
        for f in os.listdir(PATTERNS_DIR):
            base = f.replace(".binscled.zst", "").replace(".binscled", "")
            if base not in files:
                files.append(base)
    return jsonify({"patterns": sorted(files)})

@app.route("/api/play_pattern", methods=["POST"])
def api_play_pattern():
    data = request.json or {}
    name = data.get("name", "")
    loops = int(data.get("loops", 1))
    success, msg = disp.play_pattern(name, loops=loops)
    if not success:
        return jsonify({"error": msg}), 400
    return jsonify({"status": "playing", "message": msg})


if __name__ == "__main__":
    port = 8080
    print(f"[*] Starting Alice Display Controller Web Server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
