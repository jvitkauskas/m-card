# SPDX-License-Identifier: CC0-1.0
"""A 1:1 paper template of m-card.kicad_pcb (A4, 600 dpi, print at 100 % / "actual size"): a cut-out with the parts, a
plain spare, the board among the FM-1's parts as the photo puts them (not to cut), scale bars, and a measurement sheet.

  python3 make_template.py   # -> docs/template-1to1.pdf
"""
import os

import pcbnew
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DPI = 600
K = DPI / 25.4                                   # px per mm
W, H = round(210 * K), round(297 * K)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LEFT, RIGHT, BOT, TOP = 84.5, 114.5, 51.5, 76.7  # as make_board.py

# the FM-1's parts round the board, from the photo (+-1 mm; MEASUREMENTS.md's frame)
FM1 = [("left jack", 80.6, 87.6, 77.5, 92.0), ("right jack", 93.2, 100.1, 77.5, 92.0), ("USB", 104.5, 114.0, 84.0, 92.0),
       ("10 V cap", 78.0, 83.7, 59.8, 69.9), ("16 V caps", 65.5, 78.0, 45.3, 57.3), ("speaker plug J13", 85.6, 91.3, 40.0, 51.0)]

board = pcbnew.LoadBoard(os.path.join(HERE, "m-card.kicad_pcb"))
img = Image.new("L", (W, H), 255)
d = ImageDraw.Draw(img)


def font(mm, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, round(mm * K))


def text(x, y, s, mm=3.0, bold=False, anchor="la"):
    d.text((x * K, y * K), s, fill=0, font=font(mm, bold), anchor=anchor)


def drawing(ox, oy, parts=True, context=False):
    """The board with its top-left corner at (ox, oy) mm on the page, the FM-1's back view (parts up)."""
    P = lambda u, v: ((ox + u - LEFT) * K, (oy + TOP - v) * K)
    if context:
        for name, u0, u1, v0, v1 in FM1:
            d.rectangle([P(u0, v1), P(u1, v0)], fill=215, outline=120, width=3)
            text(ox + (u0 + u1) / 2 - LEFT, oy + TOP - (v0 + v1) / 2, name, 1.6, anchor="mm")
        d.line([P(90, TOP), P(90, 92)], fill=0, width=3)
        text(ox + 90.6 - LEFT, oy + TOP - 91, "jacks' gap, 90", 1.6)
    if parts:
        for fp in board.GetFootprints():
            fp.BuildCourtyardCaches()
            cy = fp.GetCourtyard(pcbnew.F_CrtYd)
            for i in range(cy.OutlineCount()):
                o = cy.Outline(i)
                pts = [P(pcbnew.ToMM(o.CPoint(j).x) - 100, 200 - pcbnew.ToMM(o.CPoint(j).y)) for j in range(o.PointCount())]
                d.line(pts + pts[:1], fill=110, width=3)
            for p in fp.Pads():
                bb = p.GetBoundingBox()
                d.rectangle([P(pcbnew.ToMM(bb.GetLeft()) - 100, 200 - pcbnew.ToMM(bb.GetTop())),
                             P(pcbnew.ToMM(bb.GetRight()) - 100, 200 - pcbnew.ToMM(bb.GetBottom()))], fill=150)
            c = fp.GetPosition()
            text(ox + pcbnew.ToMM(c.x) - 100 - LEFT, oy + TOP - (200 - pcbnew.ToMM(c.y)), fp.GetReference(),
                 1.4 if fp.GetReference()[0] in "RCU" else 2.2, bold=fp.GetReference()[0] == "J", anchor="mm")
        # the locked card in the hinged socket (its end over the contacts' tails) and the LCD cable's line
        d.rectangle([P(101.3, 67.65), P(112.3, 56.65)], outline=0, width=2)
        text(ox + 106.8 - LEFT, oy + TOP - 61.5, "card", 1.4, anchor="mm")
        d.line([P(90, TOP), P(90, TOP - 2.0)], fill=0, width=4)
    d.rectangle([P(LEFT, TOP), P(RIGHT, BOT)], outline=0, width=6)   # the cut line (0.25 mm, cut on its middle)


text(15, 14, "m-card: 1:1 template", 6, bold=True)
text(15, 22, "Print at 100 % (\"actual size\", no fit to page). Check the bars: each must measure exactly 50 mm.", 3)
text(15, 27, "Shown as the FM-1's back with its cover off (parts up). Cut on the middle of the thick line.", 3)

# scale bars, both directions (printers can stretch one axis)
y0 = 36
d.line([(15 * K, y0 * K), (65 * K, y0 * K)], fill=0, width=5)
for i in range(51):
    h = 3 if i % 10 == 0 else 2 if i % 5 == 0 else 1.2
    d.line([((15 + i) * K, y0 * K), ((15 + i) * K, (y0 - h) * K)], fill=0, width=3)
text(70, y0 - 3, "50 mm across", 3)
x0 = 195
d.line([(x0 * K, 36 * K), (x0 * K, 86 * K)], fill=0, width=5)
for i in range(51):
    h = 3 if i % 10 == 0 else 2 if i % 5 == 0 else 1.2
    d.line([(x0 * K, (36 + i) * K), ((x0 - h) * K, (36 + i) * K)], fill=0, width=3)
text(x0 - 4, 88, "50 mm down", 3, anchor="ra")

text(15, 46, "A: cut out, lay in the FM-1", 3.5, bold=True)
drawing(15, 52)
text(15, 81, "left edge 84.5 mm from the FM-1's left edge; bottom edge 51.5 mm up", 2.2)
text(15, 84.5, "the tick on the top edge: J3's middle, at the jacks' gap (90)", 2.2)

text(85, 46, "B: spare (plain)", 3.5, bold=True)
drawing(100, 52, parts=False)

text(15, 98, "C: where it should sit (from the photo, +-1 mm; don't cut)", 3.5, bold=True)
drawing(15 + LEFT - 65.5, 104 + 92 - TOP, context=True)

rows = [
    "The 10 V capacitor's right side, from the FM-1's left edge (expected 83.7; the board's edge 84.5)",
    "The 10 V capacitor's top, from the FM-1's bottom edge (expected 69.9)",
    "The left jack's right side / the right jack's left side (expected 87.6 / 93.2: the gap's middle 90)",
    "The jacks' lower end, from the bottom edge (expected 76.8; the board's top 76.7)",
    "The speaker plug's top, from the bottom edge (expected 51.0; the board's bottom 51.5)",
    "Room above the socket for its lid to open (about 14 mm up, hinged at the bottom edge)?",
    "Template A in place: clear of the 10 V cap, J13 and the jacks? The LCD cable reaches J3's tick?",
]
y = 178
text(15, y, "Measure (mm, with your 1 mm ruler to the half mm)", 3.5, bold=True)
for i, r in enumerate(rows):
    y += 13
    text(15, y, f"{i + 1}. {r}", 2.5)
    d.line([(20 * K, (y + 8) * K), (80 * K, (y + 8) * K)], fill=0, width=3)
text(15, 280, "make_template.py from m-card.kicad_pcb (CC0-1.0)", 2)

img.save(os.path.join(HERE, "docs", "template-1to1.pdf"), resolution=DPI)
print("saved docs/template-1to1.pdf")
