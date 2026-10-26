"""
Yandex Station Mini 2 LED Controller & Animation Player
Direct control of 7-segment clock display and RGB top ring via sysfs or ADB.
"""

import os
import sys
import time
import argparse
import subprocess
import zstandard as zstd

DEFAULT_ADB_TARGET = "192.168.3.6:5555"
DEFAULT_ADB_BIN = r"C:\Users\sguse\Desktop\platform-tools\adb.exe"

# 7-Segment Font Table for Digits and Letters
# Segments:
#       A
#     +---+
#   F |   | B
#     +-G-+
#   E |   | C
#     +---+
#       D
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
    'B': ['C', 'D', 'E', 'F', 'G'],       # lowercase 'b'
    'C': ['A', 'D', 'E', 'F'],
    'D': ['B', 'C', 'D', 'E', 'G'],       # lowercase 'd'
    'E': ['A', 'D', 'E', 'F', 'G'],
    'F': ['A', 'E', 'F', 'G'],
    'G': ['A', 'C', 'D', 'E', 'F'],
    'H': ['B', 'C', 'E', 'F', 'G'],
    'I': ['B', 'C'],
    'J': ['B', 'C', 'D', 'E'],
    'L': ['D', 'E', 'F'],
    'N': ['C', 'E', 'G'],                 # lowercase 'n'
    'O': ['A', 'B', 'C', 'D', 'E', 'F'],
    'P': ['A', 'B', 'E', 'F', 'G'],
    'R': ['E', 'G'],                     # lowercase 'r'
    'S': ['A', 'C', 'D', 'F', 'G'],       # same as 5
    'T': ['D', 'E', 'F', 'G'],           # lowercase 't'
    'U': ['B', 'C', 'D', 'E', 'F'],
    'Y': ['B', 'C', 'D', 'F', 'G'],
    'Z': ['A', 'B', 'D', 'E', 'G'],       # same as 2
    '[': ['A', 'D', 'E', 'F'],
    ']': ['A', 'B', 'C', 'D'],
    '°': ['A', 'B', 'F', 'G'],            # small degree symbol in digit
}

# Mapping of binscled frame channels (0..33) to sysfs LED names
CHANNEL_MAP = [
    # Position 0: Digit 1 (stride 7)
    "clockG1", "clockA1", "clockB1", "clockC1", "clockD1", "clockE1", "clockF1",
    # Position 1: Digit 2 (stride 7)
    "clockG2", "clockA2", "clockB2", "clockC2", "clockD2", "clockE2", "clockF2",
    # Position 2: Symbols (stride 7)
    "clockMINUS", "clockPLUS1", "clockPLUS2", "clockPLUS3", "clockPLUS4", "", "",
    # Position 3: Digit 3 (stride 7)
    "clockG3", "clockA3", "clockB3", "clockC3", "clockD3", "clockE3", "clockF3",
    # Position 4: Digit 4 + Degree (stride 6)
    "clockG4", "clockA4", "clockB4", "clockDEGREE", "clockC4", "clockD4",
]


class StationLedClient:
    def __init__(self, target=DEFAULT_ADB_TARGET, adb_bin=DEFAULT_ADB_BIN):
        self.target = target
        self.adb_bin = adb_bin
        self.is_local = os.path.exists("/sys/class/leds/mini2:white:clockA1")

    def run_cmd(self, shell_cmd):
        if self.is_local:
            subprocess.run(["/bin/sh", "-c", shell_cmd], check=True)
        else:
            cmd = [self.adb_bin, "-s", self.target, "shell", shell_cmd]
            subprocess.run(cmd, check=True)

    def clear(self):
        """Turn off all clock LEDs."""
        self.run_cmd("for l in /sys/class/leds/mini2:white:clock*; do echo 0 > $l/brightness; done")

    def set_raw(self, segment_dict):
        """
        Set arbitrary segments.
        Example: {'A1': 255, 'B1': 255, 'PLUS1': 100, 'DEGREE': 200}
        """
        cmds = []
        for name, val in segment_dict.items():
            if not name.startswith("clock"):
                name = "clock" + name
            cmds.append(f"echo {int(val)} > /sys/class/leds/mini2:white:{name}/brightness")
        if cmds:
            self.run_cmd(" ; ".join(cmds))

    def show_text(self, text, colon=False, degree=False, brightness=120, clear_first=True):
        """
        Display up to 4 characters on the display.
        Supports embedded ':' for colon and '°' or '*' for degree.
        """
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

        # Pad to 4 characters
        chars = list(text_clean.rjust(4))[-4:]

        cmds = []
        if clear_first:
            cmds.append("for l in /sys/class/leds/mini2:white:clock*; do echo 0 > $l/brightness; done")

        for idx, char in enumerate(chars, start=1):
            segs = FONT.get(char.upper(), [])
            for seg in segs:
                cmds.append(f"echo {brightness} > /sys/class/leds/mini2:white:clock{seg}{idx}/brightness")

        if has_colon:
            cmds.append(f"echo {brightness} > /sys/class/leds/mini2:white:clockPLUS1/brightness")
            cmds.append(f"echo {brightness} > /sys/class/leds/mini2:white:clockPLUS2/brightness")

        if has_degree:
            cmds.append(f"echo {brightness} > /sys/class/leds/mini2:white:clockDEGREE/brightness")

        self.run_cmd(" ; ".join(cmds))

    def scroll_text(self, text, speed=0.3, brightness=120):
        """Marquee scrolling text effect."""
        full_text = "    " + text + "    "
        print(f"[*] Scrolling: '{text}' (Ctrl+C to stop)")
        try:
            for i in range(len(full_text) - 3):
                window = full_text[i:i+4]
                self.show_text(window, brightness=brightness, clear_first=True)
                time.sleep(speed)
        except KeyboardInterrupt:
            self.clear()

    def set_top_ring(self, r=0, g=0, b=0):
        """Control top 6 RGB LEDs (0-255)."""
        cmds = []
        for i in range(1, 7):
            cmds.append(f"echo {r} > /sys/class/leds/mini2:red:ring{i}/brightness")
            cmds.append(f"echo {g} > /sys/class/leds/mini2:green:ring{i}/brightness")
            cmds.append(f"echo {b} > /sys/class/leds/mini2:blue:ring{i}/brightness")
        self.run_cmd(" ; ".join(cmds))

    def play_binscled(self, binscled_path, loops=1):
        """
        Play a raw or .zst animation file frame-by-frame.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if binscled_path.endswith(".zst"):
            dict_path = os.path.join(script_dir, "zstd.dict")
            with open(dict_path, "rb") as df:
                dctx = zstd.ZstdDecompressor(dict_data=zstd.ZstdCompressionDict(df.read()))
            with open(binscled_path, "rb") as f:
                raw_data = dctx.decompress(f.read(), max_output_size=10*1024*1024)
        else:
            with open(binscled_path, "rb") as f:
                raw_data = f.read()

        num_frames = len(raw_data) // 35
        print(f"[*] Playing animation: {os.path.basename(binscled_path)} ({num_frames} frames, {loops} loop(s))...")

        for _ in range(loops):
            for i in range(num_frames):
                frame = raw_data[i * 35:(i + 1) * 35]
                ch_bytes = frame[:34]
                duration_ms = frame[34] or 20

                cmds = []
                for ch_idx, val in enumerate(ch_bytes):
                    if ch_idx < len(CHANNEL_MAP) and CHANNEL_MAP[ch_idx]:
                        led_name = CHANNEL_MAP[ch_idx]
                        cmds.append(f"echo {val} > /sys/class/leds/mini2:white:{led_name}/brightness")

                if cmds:
                    self.run_cmd(" ; ".join(cmds))
                time.sleep(duration_ms / 1000.0)


def main():
    parser = argparse.ArgumentParser(description="Yandex Station Mini 2 LED Matrix Controller")
    parser.add_argument("--target", default=DEFAULT_ADB_TARGET, help="ADB target IP:PORT")
    parser.add_argument("--adb", default=DEFAULT_ADB_BIN, help="Path to adb.exe")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # text
    p_text = sub.add_parser("text", help="Display static text or numbers")
    p_text.add_argument("string", help="Text to show (e.g. 13:37, COOL, 24°)")
    p_text.add_argument("--brightness", type=int, default=150, help="Brightness 0-255")
    p_text.add_argument("--colon", action="store_true", help="Force colon ':'")
    p_text.add_argument("--degree", action="store_true", help="Force degree '°'")

    # scroll
    p_scroll = sub.add_parser("scroll", help="Scroll marquee text")
    p_scroll.add_argument("string", help="Text to scroll")
    p_scroll.add_argument("--speed", type=float, default=0.25, help="Seconds per step")
    p_scroll.add_argument("--brightness", type=int, default=150)

    # raw
    p_raw = sub.add_parser("raw", help="Set arbitrary segments by name")
    p_raw.add_argument("assignments", help="Comma-separated name=val (e.g. A1=255,B1=120,DEGREE=200)")

    # clear
    sub.add_parser("clear", help="Turn off all clock LEDs")

    # ring
    p_ring = sub.add_parser("ring", help="Control top RGB ring")
    p_ring.add_argument("--color", choices=["red", "green", "blue", "cyan", "magenta", "yellow", "white", "off"], default="white")
    p_ring.add_argument("--brightness", type=int, default=150)

    # play
    p_play = sub.add_parser("play", help="Play .binscled animation file")
    p_play.add_argument("file", help="Path or name of animation in clock_patterns")
    p_play.add_argument("--loops", type=int, default=1)

    args = parser.parse_args()
    client = StationLedClient(target=args.target, adb_bin=args.adb)

    if args.cmd == "clear":
        client.clear()
        print("[+] Display cleared.")

    elif args.cmd == "text":
        client.show_text(args.string, colon=args.colon, degree=args.degree, brightness=args.brightness)
        print(f"[+] Displayed: '{args.string}'")

    elif args.cmd == "scroll":
        client.scroll_text(args.string, speed=args.speed, brightness=args.brightness)

    elif args.cmd == "raw":
        segs = {}
        for pair in args.assignments.split(","):
            if "=" in pair:
                k, v = pair.strip().split("=")
                segs[k.strip()] = int(v.strip())
        client.set_raw(segs)
        print(f"[+] Updated {len(segs)} segment(s).")

    elif args.cmd == "ring":
        colors = {
            "red": (args.brightness, 0, 0),
            "green": (0, args.brightness, 0),
            "blue": (0, 0, args.brightness),
            "cyan": (0, args.brightness, args.brightness),
            "magenta": (args.brightness, 0, args.brightness),
            "yellow": (args.brightness, args.brightness, 0),
            "white": (args.brightness, args.brightness, args.brightness),
            "off": (0, 0, 0),
        }
        r, g, b = colors.get(args.color, (0, 0, 0))
        client.set_top_ring(r, g, b)
        print(f"[+] Top ring set to {args.color} (R={r}, G={g}, B={b}).")

    elif args.cmd == "play":
        fpath = args.file
        if not os.path.exists(fpath):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.join(script_dir, "clock_patterns", fpath)
            if os.path.exists(candidate):
                fpath = candidate
            elif os.path.exists(candidate + ".binscled"):
                fpath = candidate + ".binscled"
            elif os.path.exists(candidate + ".binscled.zst"):
                fpath = candidate + ".binscled.zst"
        if not os.path.exists(fpath):
            print(f"[-] Animation file not found: {args.file}")
            sys.exit(1)
        client.play_binscled(fpath, loops=args.loops)
        print("[+] Playback finished.")


if __name__ == "__main__":
    main()
