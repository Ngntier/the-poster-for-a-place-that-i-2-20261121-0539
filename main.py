#!/usr/bin/env python3
"""EMBERFALL — a travel poster for a place that does not exist.

Pure-stdlib Python 3.13. Draws a 1024x1024 travel poster for EMBERFALL,
a volcanic island where rivers of molten light run down a black volcano
into a glowing bay at dusk, and writes it to /output/entry.png.

Deterministic: no clock, no unseeded randomness, no network. Two runs
produce byte-identical output.
"""

import os
import struct
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------- palette
SKY_TOP = (27, 20, 64)        # deep indigo
SKY_MID = (75, 42, 107)       # violet
SKY_LOW = (168, 62, 92)       # magenta-rose
HORIZON = (242, 140, 60)      # warm orange at the horizon
SUN_CORE = (255, 217, 138)    # pale gold sun
SUN_HALO = (255, 158, 79)     # orange halo
VOLCANO = (26, 15, 36)        # near-black purple silhouette
VOLCANO_RIM = (96, 44, 74)    # faint lit rim on the volcano edge
LAVA = (255, 106, 0)          # molten orange
LAVA_HOT = (255, 194, 61)     # hottest lava yellow
SEA_TOP = (46, 28, 74)        # dark violet sea at the horizon
SEA_BOT = (16, 10, 32)        # darker sea below
SAND = (14, 10, 24)           # black sand beach
FOAM = (232, 216, 200)        # pale foam line
TEXT_MAIN = (255, 233, 184)   # cream gold letters
TEXT_OUTLINE = (42, 14, 30)   # dark outline so the name stays legible
FRAME_GOLD = (212, 164, 74)   # thin gold poster frame
CLOUD = (58, 32, 84)          # dusk cloud, darker than the sky

# 5x7 bitmap font, only the letters EMBERFALL needs.
GLYPHS = {
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
}


class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)

    def _off(self, x, y):
        return (y * self.w + x) * 3

    def set(self, x, y, rgb):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = self._off(x, y)
            self.buf[o:o + 3] = bytes(rgb)

    def blend(self, x, y, rgb, alpha):
        """Alpha-blend one pixel (alpha 0..1)."""
        if not (0 <= x < self.w and 0 <= y < self.h) or alpha <= 0:
            return
        o = self._off(x, y)
        if alpha >= 1:
            self.buf[o:o + 3] = bytes(rgb)
            return
        b = self.buf
        b[o] = int(b[o] + (rgb[0] - b[o]) * alpha)
        b[o + 1] = int(b[o + 1] + (rgb[1] - b[o + 1]) * alpha)
        b[o + 2] = int(b[o + 2] + (rgb[2] - b[o + 2]) * alpha)

    def hspan(self, x0, x1, y, rgb):
        """Fill a horizontal run of pixels, clipped."""
        if y < 0 or y >= self.h:
            return
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        if x1 < x0:
            return
        o = self._off(x0, y)
        n = x1 - x0 + 1
        self.buf[o:o + n * 3] = bytes(rgb) * n

    def blend_hspan(self, x0, x1, y, rgb, alpha):
        if y < 0 or y >= self.h or alpha <= 0:
            return
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        if x1 < x0:
            return
        if alpha >= 1:
            self.hspan(x0, x1, y, rgb)
            return
        for x in range(x0, x1 + 1):
            self.blend(x, y, rgb, alpha)

    def fill_rect(self, x0, y0, x1, y1, rgb):
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            self.hspan(x0, x1, y, rgb)

    def vgrad(self, y0, y1, top, bot):
        """Vertical gradient between two colours, row by row."""
        span = max(1, y1 - y0)
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            t = (y - y0) / span
            rgb = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
            self.hspan(0, self.w - 1, y, rgb)

    def circle(self, cx, cy, r, rgb, alpha=1.0, soft=0):
        """Filled circle; soft>0 feather the edge over that many pixels."""
        for y in range(cy - r - soft, cy + r + soft + 1):
            dy = y - cy
            if abs(dy) > r + soft:
                continue
            half = int((max(0, r * r - dy * dy)) ** 0.5)
            if soft == 0:
                self.blend_hspan(cx - half, cx + half, y, rgb, alpha)
            else:
                # solid core, feathered rim
                core = max(0, r - soft)
                if abs(dy) <= core:
                    ch = int((max(0, core * core - dy * dy)) ** 0.5)
                    self.blend_hspan(cx - ch, cx + ch, y, rgb, alpha)
                    # feather ring
                    for side in (-1, 1):
                        for k in range(1, soft + 1):
                            x = cx + side * (ch + k)
                            a = alpha * (1 - k / (soft + 1))
                            self.blend(x, y, rgb, a)
                else:
                    edge = 1 - (abs(dy) - core) / soft
                    self.blend_hspan(cx - half, cx + half, y, rgb, alpha * edge * 0.6)

    def ellipse(self, cx, cy, rx, ry, rgb, alpha=1.0):
        for y in range(cy - ry, cy + ry + 1):
            dy = (y - cy) / ry
            if abs(dy) > 1:
                continue
            half = int(rx * (1 - dy * dy) ** 0.5)
            self.blend_hspan(cx - half, cx + half, y, rgb, alpha)

    def polygon(self, pts, rgb):
        """Scanline fill of a simple polygon."""
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    t = (y - y0) / (y1 - y0)
                    xs.append(x0 + t * (x1 - x0))
            if len(xs) >= 2:
                xs.sort()
                self.hspan(int(xs[0]), int(xs[-1]), y, rgb)

    def quad(self, pts, rgb, alpha=1.0):
        """Filled quadrilateral (used for tapered lava rivers)."""
        pts = [(int(px), int(py)) for px, py in pts]
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    t = (y - y0) / (y1 - y0)
                    xs.append(x0 + t * (x1 - x0))
            if len(xs) >= 2:
                xs.sort()
                self.blend_hspan(int(xs[0]), int(xs[-1]), y, rgb, alpha)

    def text(self, s, x0, y0, scale, rgb, outline=None, outline_w=3):
        """Draw text with the 5x7 font, scaled; optional dark outline."""
        if outline is not None:
            for dx in range(-outline_w, outline_w + 1):
                for dy in range(-outline_w, outline_w + 1):
                    if dx == 0 and dy == 0:
                        continue
                    self._text_raw(s, x0 + dx, y0 + dy, scale, outline)
        self._text_raw(s, x0, y0, scale, rgb)

    def _text_raw(self, s, x0, y0, scale, rgb):
        pitch = 6 * scale
        for gi, ch in enumerate(s):
            glyph = GLYPHS[ch]
            gx = x0 + gi * pitch
            for row in range(7):
                bits = glyph[row]
                for col in range(5):
                    if bits[col] == "1":
                        self.fill_rect(gx + col * scale, y0 + row * scale,
                                       gx + (col + 1) * scale - 1,
                                       y0 + (row + 1) * scale - 1, rgb)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_river_path(cv, waypoints, w0, w1):
    """A lava stream through hand-set waypoints: short quads between
    densely interpolated points, widening toward the bottom. Deterministic."""
    pts = []
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        for k in range(12):
            t = k / 12.0
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    pts.append(waypoints[-1])
    total = len(pts) - 1
    for i in range(total):
        t = i / total
        px, py = pts[i]
        cx, cy = pts[i + 1]
        pw = (w0 + (w1 - w0) * t) / 2.0
        w = (w0 + (w1 - w0) * (i + 1) / total) / 2.0
        cv.quad([(px - pw, py), (px + pw, py),
                 (cx + w, cy), (cx - w, cy)], LAVA, alpha=0.95)
        cv.quad([(px - pw * 0.45, py), (px + pw * 0.45, py),
                 (cx + w * 0.45, cy), (cx - w * 0.45, cy)],
                LAVA_HOT, alpha=1.0)
    # glowing pool where the river meets the sea
    ex, ey = waypoints[-1]
    cv.ellipse(int(ex), int(ey) + 2, int(w1) + 8, 6, LAVA, alpha=0.9)
    cv.ellipse(int(ex), int(ey) + 2, int(w1) // 2 + 3, 3, LAVA_HOT,
               alpha=1.0)


def draw_poster(cv):
    # --- sky: deep indigo -> violet -> rose -> orange at the horizon ---
    cv.vgrad(0, 260, SKY_TOP, SKY_MID)
    cv.vgrad(260, 480, SKY_MID, SKY_LOW)
    cv.vgrad(480, 620, SKY_LOW, HORIZON)

    # --- stars in the upper sky (fixed positions, deterministic) ---
    seed = 1234567
    for _ in range(46):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        sx = 20 + seed % 984
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        sy = 16 + seed % 120
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        a = 0.25 + (seed % 50) / 100.0
        cv.blend(sx, sy, (255, 240, 210), a)
        if seed % 3 == 0:
            cv.blend(sx + 1, sy, (255, 240, 210), a * 0.6)

    # --- sun: halo, then core, low over the horizon ---
    cv.circle(655, 505, 118, SUN_HALO, alpha=0.28, soft=34)
    cv.circle(655, 505, 84, SUN_HALO, alpha=0.45, soft=18)
    cv.circle(655, 505, 62, SUN_CORE, alpha=1.0, soft=6)

    # --- dusk clouds: thin dark streaks with a warm-lit underside ---
    for (cx, cy, rx, ry) in ((150, 292, 128, 10), (818, 272, 148, 11),
                             (880, 330, 96, 8), (96, 350, 88, 7)):
        cv.ellipse(cx, cy, rx, ry, CLOUD, alpha=0.55)
        cv.ellipse(cx, cy + ry - 2, rx - 8, 2, (214, 96, 74), alpha=0.5)

    # --- birds: four small silhouettes ---
    for (bx, by, s) in ((500, 196, 12), (566, 176, 9), (618, 228, 11),
                        (452, 252, 8)):
        cv.polygon([(bx - s, by), (bx, by - s // 2), (bx + s, by)],
                   (24, 12, 32))
        cv.polygon([(bx - s, by + 1), (bx, by + 1 - s // 2),
                    (bx + s, by + 1)], (24, 12, 32))

    # --- distant headland on the right ---
    cv.polygon([(770, 620), (858, 556), (940, 588), (1024, 566),
                (1024, 620)], (38, 22, 52))

    # --- the volcano: one great dark landmark, left of centre ---
    # a truncated cone with CONCAVE slopes: steep near the crater,
    # flaring flat toward the base, so it reads as a volcano, not a pyramid
    cv.polygon([(8, 620), (60, 580), (130, 530), (205, 470),
                (270, 410), (320, 350), (348, 312), (345, 300),
                (375, 300), (376, 314), (395, 345), (430, 395),
                (480, 450), (545, 505), (620, 560), (700, 600),
                (762, 620)], VOLCANO)
    # crater: a flat glowing notch at the top, not a point
    cv.ellipse(360, 300, 22, 7, LAVA, alpha=0.95)
    cv.ellipse(360, 300, 11, 4, LAVA_HOT, alpha=1.0)
    # a thin wisp of smoke rising from the crater, drifting right
    cv.ellipse(366, 282, 16, 6, (122, 96, 140), alpha=0.55)
    cv.ellipse(382, 268, 20, 7, (122, 96, 140), alpha=0.42)
    cv.ellipse(402, 256, 24, 8, (122, 96, 140), alpha=0.3)

    # --- lava rivers: meandering S-curves from crater to bay ---
    # hand-set waypoints so each river bends like a real flow, not a rail
    draw_river_path(cv, [(358, 306), (332, 360), (300, 420), (286, 482),
                         (300, 542), (272, 618)], 7, 15)
    draw_river_path(cv, [(364, 306), (398, 368), (428, 428), (420, 498),
                         (452, 558), (486, 618)], 6, 13)

    # --- sea: dark violet, lighter at the horizon ---
    cv.vgrad(620, 905, SEA_TOP, SEA_BOT)
    # sun reflection: a shimmering column of gold dashes under the sun
    seed = 987654
    for row in range(636, 900, 13):
        t = (row - 636) / 264.0
        width = int(150 - 90 * t)
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        jitter = (seed % 40) - 20
        cx = 655 + jitter
        a = 0.75 * (1 - t * 0.7)
        cv.blend_hspan(cx - width // 2, cx + width // 2, row,
                       (255, 166, 80), a)
        cv.blend_hspan(cx - width // 4, cx + width // 4, row + 4,
                       (255, 205, 120), a * 0.7)
    # lava glow reflected in the bay
    for (lx, lw) in ((272, 56), (486, 50)):
        for k, row in enumerate(range(628, 700, 9)):
            a = 0.5 * (1 - k / 8.0)
            cv.blend_hspan(lx - lw // 2, lx + lw // 2, row, LAVA, a)
    # faint wave lines across the sea so it is not one flat slab
    seed = 424242
    for row in range(660, 890, 26):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = 40 + seed % 120
        while x < 980:
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            ln = 30 + seed % 70
            cv.blend_hspan(x, min(1003, x + ln), row, (96, 66, 128), 0.35)
            x += ln + 60 + seed % 120

    # --- black-sand beach in the foreground ---
    cv.fill_rect(0, 905, W - 1, H - 1, SAND)
    # foam line where the sea meets the sand
    seed = 555111
    x = 0
    while x < W:
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        ln = 14 + seed % 40
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        yy = 903 + seed % 5
        cv.blend_hspan(x, min(W - 1, x + ln), yy, FOAM, 0.75)
        x += ln + 8 + seed % 22
    # embers scattered on the sand below the lava rivers
    seed = 777001
    for _ in range(26):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        ex = 180 + seed % 420
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        ey = 920 + seed % 84
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        a = 0.35 + (seed % 50) / 100.0
        cv.blend(ex, ey, LAVA_HOT if seed % 3 == 0 else LAVA, a)
        if seed % 4 == 0:
            cv.blend(ex + 1, ey, LAVA, a * 0.6)

    # --- the name, big and legible across the upper sky ---
    name = "EMBERFALL"
    scale = 16
    tw = len(name) * 5 * scale + (len(name) - 1) * scale
    x0 = (W - tw) // 2
    cv.text(name, x0, 108, scale, TEXT_MAIN, outline=TEXT_OUTLINE,
            outline_w=3)
    # thin gold rule under the name
    cv.fill_rect(x0 + 40, 236, x0 + tw - 40, 239, FRAME_GOLD)

    # --- thin gold poster frame ---
    cv.fill_rect(16, 16, W - 17, 19, FRAME_GOLD)
    cv.fill_rect(16, H - 20, W - 17, H - 17, FRAME_GOLD)
    cv.fill_rect(16, 16, 19, H - 17, FRAME_GOLD)
    cv.fill_rect(W - 20, 16, W - 17, H - 17, FRAME_GOLD)


def write_png(path, cv):
    """Encode the canvas as a PNG (filter 0, zlib level 9)."""
    w, h = cv.w, cv.h
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += cv.buf[y * w * 3:(y + 1) * w * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    cv = Canvas(W, H)
    draw_poster(cv)
    out = os.environ.get("POSTER_OUT", "/output/entry.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    size = write_png(out, cv)
    print(f"wrote {out} {W}x{H} {size} bytes")


if __name__ == "__main__":
    main()
