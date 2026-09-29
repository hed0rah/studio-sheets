"""studio-sheets: a studio's signal flow and a session sheet, as a printable PDF.

    python build.py studio.json            writes studio.pdf and studio-session.pdf beside it
    python build.py studio.json --png      also renders page PNGs for checking

Everything comes from the JSON: devices on a dot grid, ports on their edges, cables between
ports, and the session sheet's fields and tables. Coordinates are grid units, one per dot
(5 mm by default), from the bottom-left of the map area, so devices land on the dots you
will later draw on. See SKILL.md for the schema. Needs reportlab; --png needs pymupdf.
"""
import json
import math
import os
import sys

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
MM = 72 / 25.4
MARGIN = 30
WARNINGS = []


# ------------------------------------------------------------------ fonts
def register_fonts():
    """IBM Plex Mono and Source Serif 4 when they can be found, the PDF core fonts when not"""
    want = {"Mono": "IBMPlexMono-Regular.ttf", "Mono-Bold": "IBMPlexMono-Bold.ttf",
            "Mono-Italic": "IBMPlexMono-Italic.ttf", "Serif-Semibold": "SourceSerif4-Semibold.ttf"}
    dirs = [os.path.join(HERE, "fonts")]
    for d in dirs:
        if all(os.path.exists(os.path.join(d, f)) for f in want.values()):
            for name, f in want.items():
                pdfmetrics.registerFont(TTFont(name, os.path.join(d, f)))
            return {k: k for k in want}
    return {"Mono": "Courier", "Mono-Bold": "Courier-Bold", "Mono-Italic": "Courier-Oblique",
            "Serif-Semibold": "Times-Bold"}


F = register_fonts()


# each palette comes from a constraint, not a mood. The white-paper ones print on a mono laser
# (the accent only ever repeats a number or a word); the coloured-paper ones fill the page and
# are for screens and colour printers
PALETTES = {
    # ink and rally orange: the default
    "rally": dict(paper="#FFFFFF", ink="#1A1814", faint="#6B655A", rule="#B9B4AA", tint="#F1EFEA",
                  accent="#FF4D00", dots_map="#C4C1BA", dots_notes="#8F8F8F"),
    # ink and a teal deep enough to read as text on white
    "teal": dict(paper="#FFFFFF", ink="#16181C", faint="#5E6570", rule="#B3BAC2", tint="#EDF1F2",
                 accent="#00857A", dots_map="#BFC6CC", dots_notes="#8C959E"),
    # two riso inks: Riso Blue carries everything, fluorescent pink is the accent
    "riso": dict(paper="#FFFFFF", ink="#0078BF", faint="#4F93C4", rule="#A9CBE3", tint="#E6F0F8",
                 accent="#FF48B0", dots_map="#B7D3E8", dots_notes="#7FAED3"),
    # black ink on lavender stock with a blue second colour, after a riso-printed design journal
    "violet": dict(paper="#C8B8F2", ink="#17122B", faint="#4A3F73", rule="#6F5FB0", tint="#B6A3EC",
                   accent="#1F2FD1", dots_map="#9C8BD6", dots_notes="#7564B8", fills=True),
    # cyanotype: pale lines on Prussian blue, amber for the accent
    "blueprint": dict(paper="#123A6B", ink="#EEF3F9", faint="#A8BDD8", rule="#7394C0", tint="#1C4A80",
                      accent="#FFB000", dots_map="#3D6394", dots_notes="#5C82B3", fills=True),
}


class Theme:
    def __init__(self, palette="rally", accent=None):
        if palette not in PALETTES:
            raise SystemExit(f"no palette '{palette}': choose one of {', '.join(PALETTES)}")
        p = PALETTES[palette]
        for k in ("paper", "ink", "faint", "rule", "tint", "accent"):
            setattr(self, k, HexColor(p[k]))
        if accent:
            self.accent = HexColor(accent)
        self.dots_map, self.dots_notes = p["dots_map"], p["dots_notes"]
        self.fills = p.get("fills", False)


# ------------------------------------------------------------------ primitives
class Sheet:
    def __init__(self, c, spec, W, H):
        self.c, self.spec, self.W, self.H = c, spec, W, H
        self.T = Theme(spec.get("palette", "rally"), spec.get("accent"))
        self.pitch = spec.get("grid_mm", 5) * MM

    def text(self, x, y, s, size=7, font="Mono", color=None, anchor="l"):
        c = self.c
        c.setFont(F[font], size)
        c.setFillColor(color or self.T.ink)
        {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[anchor](x, y, s)

    def width(self, s, size=7, font="Mono"):
        return pdfmetrics.stringWidth(s, F[font], size)

    def arrow(self, x, y, ang, size=4, color=None):
        c = self.c
        c.setStrokeColor(color or self.T.ink)
        for da in (0.5, -0.5):
            a = ang + math.pi - da
            c.line(x, y, x + size * math.cos(a), y + size * math.sin(a))

    def wire(self, pts, dashed=False, arrow=True, width=0.9):
        c = self.c
        c.setStrokeColor(self.T.ink)
        c.setLineWidth(width)
        if dashed:
            c.setDash(2.6, 2)
        p = c.beginPath()
        p.moveTo(*pts[0])
        for q in pts[1:]:
            p.lineTo(*q)
        c.drawPath(p, stroke=1, fill=0)
        c.setDash()
        if arrow:
            (x0, y0), (x1, y1) = pts[-2], pts[-1]
            self.arrow(x1, y1, math.atan2(y1 - y0, x1 - x0))

    def badge(self, x, y, n, r=6.2):
        self.c.setFillColor(self.T.accent)
        self.c.circle(x, y, r, stroke=0, fill=1)
        self.text(x, y - 2.4, str(n), 7, "Mono-Bold", self.T.paper, "c")

    def dot_grid(self, x, y, w, h, weight=1.2, color=None):
        """dots on a true millimetre pitch; returns the origin of the first dot"""
        px = self.pitch
        nx, ny = int(w // px), int(h // px)
        ox, oy = x + (w - nx * px) / 2, y + (h - ny * px) / 2
        self.c.setFillColor(HexColor(color or self.T.dots_notes))
        r = 0.3 * weight * MM
        for i in range(nx + 1):
            for j in range(ny + 1):
                self.c.circle(ox + i * px, oy + j * px, r, stroke=0, fill=1)
        return ox, oy, nx, ny

    def blank(self, x, y, w, hint=None):
        self.c.setStrokeColor(self.T.rule)
        self.c.setLineWidth(0.5)
        self.c.line(x, y - 2, x + w, y - 2)
        if hint:
            self.text(x + 1, y, hint, 5.6, "Mono-Italic", self.T.rule)

    def ticks(self, x, y, options, size=6.2, gap=7):
        for o in options:
            self.c.setStrokeColor(self.T.ink)
            self.c.setLineWidth(0.6)
            self.c.rect(x, y - 1.5, 5.5, 5.5, stroke=1, fill=0)
            self.text(x + 8, y - 0.5, o, size)
            x += 8 + self.width(o, size) + gap
        return x

    def ticks_width(self, options, size=6.2, gap=7):
        return sum(8 + self.width(o, size) + gap for o in options)

    def dial(self, cx, cy, r=5, marks=None):
        c = self.c
        c.setStrokeColor(self.T.ink)
        c.setLineWidth(0.6)
        c.circle(cx, cy, r, stroke=1, fill=0)
        for k in range(11):
            a = math.radians(225 - 27 * k)
            c.line(cx + r * math.cos(a), cy + r * math.sin(a), cx + (r + 2) * math.cos(a), cy + (r + 2) * math.sin(a))
        if marks:
            self.text(cx - r - 6, cy - r - 1, marks[0], 5.2, color=self.T.faint)
            self.text(cx + r + 2, cy - r - 1, marks[1], 5.2, color=self.T.faint)

    def section(self, x, y, w, title):
        self.text(x, y, title, 7.6, "Mono-Bold")
        self.c.setStrokeColor(self.T.ink)
        self.c.setLineWidth(0.6)
        self.c.line(x, y - 4, x + w, y - 4)

    def background(self):
        """a coloured paper fills the page; white paper stays unprinted"""
        if self.T.fills:
            self.c.setFillColor(self.T.paper)
            self.c.rect(0, 0, self.W, self.H, stroke=0, fill=1)

    def header(self, tab, title, sub, pno, pages):
        c, W, H, s = self.c, self.W, self.H, self.spec
        self.background()
        tw = self.width(tab, 8, "Mono-Bold") + 16
        c.setFillColor(self.T.ink)
        c.rect(MARGIN, H - 44, tw, 22, stroke=0, fill=1)
        self.text(MARGIN + 8, H - 37, tab, 8, "Mono-Bold", self.T.paper)
        self.text(MARGIN + tw + 12, H - 36, title, 15, "Serif-Semibold")
        self.text(MARGIN + tw + 12, H - 46, sub, 7, "Mono", self.T.faint)
        doc = " · ".join(x for x in (s.get("doc"), s.get("rev")) if x)
        if doc:
            self.text(W - MARGIN, H - 32, doc, 7, "Mono", self.T.faint, "r")
        self.text(W - MARGIN, H - 42, f"PAGE {pno}/{pages}", 7, "Mono-Bold", anchor="r")
        c.setStrokeColor(self.T.ink)
        c.setLineWidth(0.6)
        c.line(MARGIN, H - 52, W - MARGIN, H - 52)

    def footer(self, left, right=""):
        self.c.setStrokeColor(self.T.ink)
        self.c.setLineWidth(0.5)
        self.c.line(MARGIN, 22, self.W - MARGIN, 22)
        self.text(MARGIN, 12, left, 6.3, "Mono-Italic", self.T.faint)
        if right:
            self.text(self.W - MARGIN, 12, right, 6.3, "Mono-Italic", self.T.faint, "r")


# ------------------------------------------------------------------ the map
class Map:
    def __init__(self, sh):
        self.sh = sh
        W, H = sh.W, sh.H
        self.ox, self.oy, self.nx, self.ny = sh.dot_grid(MARGIN, 30, W - 2 * MARGIN, H - 92,
                                                         weight=0.85, color=sh.T.dots_map)
        self.devices = {d["id"]: d for d in sh.spec.get("devices", [])}

    def g(self, gx, gy):
        return self.ox + gx * self.sh.pitch, self.oy + gy * self.sh.pitch

    def rect(self, d):
        x, y = self.g(*d["at"])
        return x, y, d["size"][0] * self.sh.pitch, d["size"][1] * self.sh.pitch

    def port_xy(self, ref):
        """'device.port' -> (x, y, side)"""
        dev_id, _, port_id = ref.partition(".")
        d = self.devices.get(dev_id)
        if d is None:
            raise SystemExit(f"cable refers to unknown device '{dev_id}' in '{ref}'")
        p = next((p for p in d.get("ports", []) if p["id"] == port_id), None)
        if p is None:
            raise SystemExit(f"device '{dev_id}' has no port '{port_id}'")
        x, y, w, h = self.rect(d)
        off = p["pos"] * self.sh.pitch
        return {"left": (x, y + h - off), "right": (x + w, y + h - off),
                "top": (x + off, y + h), "bottom": (x + off, y)}[p["side"]] + (p["side"],)

    def hits_title(self, d, label, px, py, side):
        """does a port label's box overlap the box's title (and subtitle) text?"""
        sh = self.sh
        x, y, w, h = self.rect(d)
        name, sub = d.get("name", d["id"]), d.get("sub")
        # the title's text as rectangles: (x0, x1, y0, y1)
        if d.get("hub"):
            rects = [(x, x + w, y + h - 16, y + h)]
        else:
            rects = [(x + 5, x + 5 + sh.width(name, 7.5, "Mono-Bold"), y + h - 11, y + h - 3)]
            if sub:
                rects.append((x + 5, x + 5 + sh.width(sub, 6.2), y + h - 20, y + h - 13))
        lw = sh.width(label, 6.3)
        lx0, lx1, ly = {"left": (px + 6, px + 6 + lw, py - 2.2), "right": (px - 6 - lw, px - 6, py - 2.2),
                        "top": (px - lw / 2, px + lw / 2, py - 11),
                        "bottom": (px - lw / 2, px + lw / 2, py + 6)}[side]
        return any(lx0 < r[1] and r[0] < lx1 and ly - 1 < r[3] and r[2] < ly + 6 for r in rects)

    def draw_device(self, d):
        sh, T = self.sh, self.sh.T
        x, y, w, h = self.rect(d)
        c = sh.c
        c.setStrokeColor(T.ink)
        c.setLineWidth(1.4 if d.get("hub") else 1.0)
        c.setFillColor(T.tint if d.get("muted") else T.paper)
        c.rect(x, y, w, h, stroke=1, fill=1)
        name, sub = d.get("name", d["id"]), d.get("sub")
        if d.get("hub"):
            c.setFillColor(T.accent)
            c.rect(x, y + h - 16, w, 16, stroke=0, fill=1)
            sh.text(x + 6, y + h - 11.5, name, 8.5, "Mono-Bold", T.paper)
            if sub:
                sh.text(x + w - 6, y + h - 11.5, sub, 6.5, "Mono", T.paper, "r")
        else:
            sh.text(x + 5, y + h - 10, name, 7.5, "Mono-Bold")
            if sub:
                sh.text(x + 5, y + h - 18.5, sub, 6.2, "Mono", T.faint)
        if sh.width(name, 8.5 if d.get("hub") else 7.5, "Mono-Bold") > w - 10:
            WARNINGS.append(f"'{d['id']}': the name is wider than the box; widen size[0]")
        # notes sit on the floor of the box, above any bottom-edge port labels
        floor = 18 if any(p["side"] == "bottom" for p in d.get("ports", [])) else 6
        for i, line in enumerate(reversed(d.get("notes", []))):
            sh.text(x + 6, y + floor + i * 9, line, 6.0, color=T.faint)
        for p in d.get("ports", []):
            px, py, side = self.port_xy(f"{d['id']}.{p['id']}")
            c.setFillColor(T.paper)
            c.setStrokeColor(T.ink)
            c.setLineWidth(0.8)
            c.rect(px - 2.5, py - 2.5, 5, 5, stroke=1, fill=1)
            label, col = p.get("label", p["id"]), T.faint if p.get("unused") else T.ink
            if label and self.hits_title(d, label, px, py, side):
                WARNINGS.append(f"'{d['id']}.{p['id']}': the port label runs into the title; "
                                "move the port (pos) or leave its label empty and label the cable")
            if side == "left":
                sh.text(px + 6, py - 2.2, label, 6.3, color=col)
            elif side == "right":
                sh.text(px - 6, py - 2.2, label, 6.3, color=col, anchor="r")
            elif side == "top":
                sh.text(px, py - 11, label, 6.3, color=col, anchor="c")
            else:
                sh.text(px, py + 6, label, 6.3, color=col, anchor="c")
        if "badge" in d:
            sh.badge(x + w - 8, y + h + 8, d["badge"])

    def route(self, cab):
        (x0, y0, s0), (x1, y1, s1) = self.port_xy(cab["from"]), self.port_xy(cab["to"])
        out = {"left": (-3, 0), "right": (3, 0), "top": (0, 3), "bottom": (0, -3)}
        a = (x0 + out[s0][0], y0 + out[s0][1])
        b = (x1 + out[s1][0], y1 + out[s1][1])
        if "via" in cab:
            return [a] + [self.g(*v) for v in cab["via"]] + [b]
        horiz0, horiz1 = s0 in ("left", "right"), s1 in ("left", "right")
        if abs(a[1] - b[1]) < 0.5 or abs(a[0] - b[0]) < 0.5:
            return [a, b]
        if horiz0 and horiz1:
            mx = self.ox + round(((a[0] + b[0]) / 2 - self.ox) / self.sh.pitch) * self.sh.pitch
            return [a, (mx, a[1]), (mx, b[1]), b]
        if horiz0:
            return [a, (b[0], a[1]), b]
        if horiz1:
            return [a, (a[0], b[1]), b]
        my = self.oy + round(((a[1] + b[1]) / 2 - self.oy) / self.sh.pitch) * self.sh.pitch
        return [a, (a[0], my), (b[0], my), b]

    def draw_cable(self, cab):
        sh = self.sh
        pts = self.route(cab)
        sh.wire(pts, dashed=cab.get("kind") == "cv", arrow=not cab.get("both", False))
        if cab.get("both"):
            (x0, y0), (x1, y1) = pts[1], pts[0]
            sh.arrow(x1, y1, math.atan2(y1 - y0, x1 - x0))
        # label at the midpoint of the longest segment, never at a corner
        segs = list(zip(pts, pts[1:]))
        (p, q) = max(segs, key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        vertical = abs(p[0] - q[0]) < 0.5
        if cab.get("label"):
            if vertical:
                sh.c.saveState()
                # beside the wire, not on it: the glyphs rise towards -x once rotated
                sh.c.translate(mx + 9, my - sh.width(cab["label"], 5.8) / 2)
                sh.c.rotate(90)
                sh.text(0, 0, cab["label"], 5.8, color=sh.T.faint)
                sh.c.restoreState()
            else:
                sh.text(mx, my + 3, cab["label"], 5.8, color=sh.T.faint, anchor="c")
        if "badge" in cab:
            sh.badge(mx + (10 if vertical else 0), my + (0 if vertical else 12), cab["badge"])

    def draw_insert(self, ins):
        sh, T = self.sh, self.sh.T
        x, y, side = self.port_xy(ins["at"])
        w = ins.get("w", 10) * sh.pitch
        if side == "right":
            sh.wire([(x + 3, y), (x + 16, y)])
            bx = x + 18
        elif side == "left":
            sh.wire([(x - 3, y), (x - 16, y)])
            bx = x - 18 - w
        elif side == "bottom":
            sh.wire([(x, y - 3), (x, y - 16)])
            bx, y = x - w / 2, y - 24
        else:
            sh.wire([(x, y + 3), (x, y + 16)])
            bx, y = x - w / 2, y + 24
        c = sh.c
        c.setFillColor(T.paper)
        c.setStrokeColor(T.ink)
        c.setLineWidth(0.6)
        c.setDash(2, 1.6)
        c.rect(bx, y - 6, w, 12, stroke=1, fill=1)
        c.setDash()
        sh.text(bx + 3, y - 2.3, "+", 7, "Mono-Bold", T.faint)

    def legend(self):
        sh, T = self.sh, self.sh.T
        lx, ly = MARGIN, sh.H - 72
        sh.wire([(lx, ly), (lx + 26, ly)])
        sh.text(lx + 32, ly - 2.2, "audio", 6.5)
        sh.wire([(lx + 64, ly), (lx + 90, ly)], dashed=True)
        sh.text(lx + 96, ly - 2.2, "CV, gate, clock", 6.5)
        y2 = ly - 16
        if sh.spec.get("cards"):
            sh.badge(lx + 4, y2, 1)
            sh.text(lx + 14, y2 - 2.3, "card on the cards page", 6.5)
            y2 -= 16
        sh.c.setFillColor(T.tint)
        sh.c.rect(lx, y2 - 5, 10, 9, stroke=0, fill=1)
        sh.text(lx + 16, y2 - 2.3, "parked or unconfirmed", 6.5)
        y2 -= 16
        sh.c.setDash(2, 1.6)
        sh.c.setStrokeColor(T.ink)
        sh.c.setLineWidth(0.6)
        sh.c.rect(lx, y2 - 6, 26, 12, stroke=1, fill=0)
        sh.c.setDash()
        sh.text(lx + 32, y2 - 2.3, "write in what you patch there", 6.5)
        mm = sh.spec.get("grid_mm", 5)
        sh.text(lx, y2 - 18, f"the dots are {mm:g} mm: draw new gear and cables on them", 6.5, color=T.faint)

    def check_overlaps(self):
        ds = list(self.devices.values())
        for i, a in enumerate(ds):
            ax, ay = a["at"]
            aw, ah = a["size"]
            if ax < 0 or ay < 0 or ax + aw > self.nx or ay + ah > self.ny:
                WARNINGS.append(f"'{a['id']}' runs off the grid ({self.nx} x {self.ny} dots on this paper)")
            for b in ds[i + 1:]:
                bx, by = b["at"]
                bw, bh = b["size"]
                if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                    WARNINGS.append(f"'{a['id']}' and '{b['id']}' overlap")

    def draw(self):
        self.check_overlaps()
        for d in self.devices.values():
            self.draw_device(d)
        for cab in self.sh.spec.get("cables", []):
            self.draw_cable(cab)
        for ins in self.sh.spec.get("inserts", []):
            self.draw_insert(ins)
        self.legend()


# ------------------------------------------------------------------ the session sheet
def page_session(sh, pno, pages):
    spec, T = sh.spec, sh.T
    ss = spec.get("session", {})
    W, H = sh.W, sh.H
    sh.header("STUDIO / SESSION", "Session sheet", "fill in by hand: what is switched, what is patched, what changed",
              pno, pages)
    # the session line: fields in a row, wrapping when the page runs out
    x, y = MARGIN, H - 70
    for f in ss.get("fields", [{"label": "DATE", "w": 62}, {"label": "PROJECT", "w": 140}, {"label": "BPM", "w": 30}]):
        lw = sh.width(f["label"], 6.4, "Mono-Bold") + 6
        need = lw + (sh.ticks_width(f["ticks"]) if "ticks" in f else 24 if "dial" in f else f.get("w", 60)) + 12
        if x + need > W - MARGIN:
            x, y = MARGIN, y - 16
        sh.text(x, y, f["label"], 6.4, "Mono-Bold")
        if "ticks" in f:
            sh.ticks(x + lw, y, f["ticks"])
        elif "dial" in f:
            sh.dial(x + lw + 8, y + 2, 5, f["dial"] or None)
        else:
            sh.blank(x + lw, y, f.get("w", 60), f.get("hint"))
        x += need
    top = y - 22

    # left column: the tables, then clock and MIDI
    lx, lw_ = MARGIN, ss.get("left_width", 440)
    y = top
    for tab in ss.get("tables", []):
        sh.section(lx, y, lw_, tab["title"])
        y -= 14
        cols, cx = [], lx + 30
        for col in tab["columns"]:
            if col["type"] == "ticks":
                cw = sh.ticks_width(col["options"], 5.8, 3)
            elif col["type"] == "dial":
                cw = 34
            else:
                cw = col.get("w", 80) + 8
            cols.append((cx, cw, col))
            sh.text(cx, y, col["name"], 5.8, "Mono-Bold", T.faint)
            cx += cw
        if cx > lx + lw_ + 1:
            WARNINGS.append(f"session table '{tab['title']}' is {cx - lx:.0f} pt wide, over the {lw_} pt column")
        for r, row in enumerate(tab["rows"]):
            y -= 20
            sh.text(lx + 2, y, str(row), 8 if len(str(row)) < 3 else 7, "Mono-Bold")
            for cx, cw, col in cols:
                if col["type"] == "ticks":
                    sh.ticks(cx, y, col["options"], 5.8, 3)
                elif col["type"] == "dial":
                    sh.dial(cx + 10, y + 2, 5, col.get("marks"))
                else:
                    hints = col.get("hints", [])
                    sh.blank(cx, y, col.get("w", 80), hints[r] if r < len(hints) else None)
        y -= 24
    clock = ss.get("clock")
    if clock:
        sh.section(lx, y, lw_, "MIDI AND CLOCK")
        y -= 15
        sh.text(lx, y, "CLOCK MASTER", 6.2, "Mono-Bold")
        sh.ticks(lx + 62, y, clock.get("options", ["DAW", "none"]))
        for i in range(clock.get("slots", 8)):
            if i % 4 == 0:
                y -= 17
            x = lx + (i % 4) * (lw_ / 4)
            sh.blank(x, y, lw_ / 4 - 52, "device" if i == 0 else None)
            sh.text(x + lw_ / 4 - 48, y, "ch", 5.8, color=T.faint)
            sh.blank(x + lw_ / 4 - 38, y, 26)
        y -= 10

    # right column: each listed device's ports, hinted from the map's cables, then changes
    rx = lx + lw_ + 30
    rw = W - MARGIN - rx
    py = top
    devices = {d["id"]: d for d in spec.get("devices", [])}
    names = {d["id"]: d.get("name", d["id"]) for d in spec.get("devices", [])}
    for dev_id in ss.get("port_lists", []):
        d = devices[dev_id]
        sh.section(rx, py, rw, f"{d.get('name', dev_id)}: WHAT IS ON EACH PORT")
        py -= 15
        for i, p in enumerate(d.get("ports", [])):
            here = f"{dev_id}.{p['id']}"
            other = [c["to"] if c["from"] == here else c["from"] for c in spec.get("cables", [])
                     if here in (c["from"], c["to"])]
            hint = ", ".join(names[o.split(".")[0]] for o in other) or ("free" if p.get("unused") else None)
            col = i % 2
            x = rx + col * (rw / 2)
            if col == 0 and i:
                py -= 15
            short = p.get("short", p.get("label", p["id"]))
            sh.text(x, py, short, 6.2, "Mono-Bold")
            sh.blank(x + 44, py, rw / 2 - 52, hint)
        py -= 24
    n = ss.get("changes", 6)
    if n:
        sh.section(rx, py, rw, "PATCH AND SWITCH CHANGES")
        py -= 13
        for x, h in ((rx, "FROM"), (rx + 88, "TO"), (rx + 176, "WHY / WHAT IT DID")):
            sh.text(x, py, h, 5.8, "Mono-Bold", T.faint)
        for _ in range(n):
            py -= 15
            sh.blank(rx, py, 80)
            sh.blank(rx + 88, py, 80)
            sh.blank(rx + 176, py, rw - 176)
        py -= 10

    gy = min(y, py) - 14
    if gy < 90:
        WARNINGS.append("the session sheet leaves under an inch for notes; trim a table or rows")
    sh.section(MARGIN, gy, W - 2 * MARGIN, "NOTES, SKETCHES, LEVELS")
    sh.dot_grid(MARGIN, 30, W - 2 * MARGIN, gy - 36)
    mm = spec.get("grid_mm", 5)
    sh.footer(f"{spec.get('doc', 'studio')} · session sheet · {mm:g} mm dot grid, true size at 100% print scale",
              "print at 100%, not fit to page, or the dots stop being millimetres")


# ------------------------------------------------------------------ the cards
def wrap(sh, s, size, width, font="Mono"):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if sh.width(t, size, font) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def page_cards(sh, pno, pages):
    cards = sh.spec.get("cards", [])
    sh.header("STUDIO / CARDS", sh.spec.get("cards_title", "Rules and tricks"),
              "the numbers match the badges on the map", pno, pages)
    ncol = 3
    gap = 14
    cw = (sh.W - 2 * MARGIN - gap * (ncol - 1)) / ncol
    ys = [sh.H - 70] * ncol
    for i, card in enumerate(cards, 1):
        col = ys.index(max(ys))
        x, y = MARGIN + col * (cw + gap), ys[col]
        body = []
        for para in card.get("lines", []):
            body += wrap(sh, para, 6.8, cw - 20) + [""]
        h = 20 + 8.6 * len(body)
        if y - h < 30:
            WARNINGS.append(f"card {i} '{card['title']}' runs off the page; shorten the cards")
        sh.c.setStrokeColor(sh.T.ink)
        sh.c.setLineWidth(0.6)
        sh.c.rect(x, y - h, cw, h, stroke=1, fill=0)
        sh.badge(x + 10, y - 10, card.get("n", i))
        sh.text(x + 22, y - 12.4, card["title"], 7.6, "Mono-Bold")
        ty = y - 26
        for line in body:
            if line:
                sh.text(x + 10, ty, line, 6.8)
            ty -= 8.6
        ys[col] = y - h - 10
    sh.footer(f"{sh.spec.get('doc', 'studio')} · cards")


# ------------------------------------------------------------------ main
def build(spec_path, png=False, palette=None):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    if palette:
        spec["palette"] = palette
        spec.pop("accent", None)
    size = A4 if spec.get("paper", "letter").lower() == "a4" else letter
    W, H = landscape(size)
    base = os.path.splitext(spec_path)[0]

    def page(sh, kind, pno, n):
        if kind == "map":
            sh.header("STUDIO / SIGNAL FLOW", spec.get("title", "Studio signal flow"), spec.get("subtitle", ""), pno, n)
            Map(sh).draw()
            sh.footer(f"{spec.get('doc', 'studio')} · signal flow", spec.get("footer_note", ""))
        elif kind == "session":
            page_session(sh, pno, n)
        else:
            page_cards(sh, pno, n)

    out = base + ".pdf"
    c = canvas.Canvas(out, pagesize=(W, H))
    c.setTitle(spec.get("title", "Studio signal flow"))
    order = ["map", "cards", "session"] if spec.get("cards") else ["map", "session"]
    for i, kind in enumerate(order, 1):
        page(Sheet(c, spec, W, H), kind, i, len(order))
        c.showPage()
    c.save()
    print("wrote", out)
    one = base + "-session.pdf"
    c = canvas.Canvas(one, pagesize=(W, H))
    c.setTitle("Session sheet")
    page(Sheet(c, spec, W, H), "session", 1, 1)
    c.showPage()
    c.save()
    print("wrote", one)
    for w in dict.fromkeys(WARNINGS):
        print("warning:", w)
    if png:
        import fitz
        d = fitz.open(out)
        for i, p in enumerate(d, 1):
            path = f"{base}_p{i}.png"
            p.get_pixmap(dpi=110).save(path)
            print("wrote", path)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    pal = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--palette=")), None)
    build(args[0], png="--png" in sys.argv, palette=pal)
