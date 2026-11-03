# SPDX-License-Identifier: CC0-1.0
"""An assembly drawing of m-card.kicad_pcb for hand soldering (A4, 300 dpi): the top side at 5:1 with every part's
reference and value, pin-1 marks, the parts list, an order to solder in and the checks before plugging it in.

  python3 make_assembly.py   # -> docs/assembly.pdf
"""
import os

import pcbnew
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DPI = 300
K = DPI / 25.4
W, H = round(210 * K), round(297 * K)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LEFT, RIGHT, BOT, TOP = 84.5, 114.5, 51.5, 76.7  # as make_board.py
S, OX, OY = 5.0, 30.0, 34.0                      # the drawing's scale, its top-left corner on the page (mm)

board = pcbnew.LoadBoard(os.path.join(HERE, "m-card.kicad_pcb"))
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
M = pcbnew.ToMM


def text(x, y, s, mm=3.0, bold=False, anchor="la", fill="black"):
    d.text((x * K, y * K), s, fill=fill, font=ImageFont.truetype(BOLD if bold else FONT, round(mm * K)), anchor=anchor)


def P(u, v):
    """Board (u, v) mm to page pixels."""
    return ((OX + (u - LEFT) * S) * K, (OY + (TOP - v) * S) * K)


def uv(p):
    return M(p.x) - 100, 200 - M(p.y)


text(15, 14, "m-card: assembly (top side, 5:1)", 6, bold=True)
text(15, 22, "Seen as on the FM-1's back with the cover off: the jacks above the top edge. Pads grey, pin 1 (on J2/J3 the cable's line 1) red.", 3)

d.rectangle([P(LEFT, TOP), P(RIGHT, BOT)], outline="black", width=6)
for fp in board.GetFootprints():
    ref = fp.GetReference()
    fp.BuildCourtyardCaches()
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    for i in range(cy.OutlineCount()):
        o = cy.Outline(i)
        pts = [P(*uv(o.CPoint(j))) for j in range(o.PointCount())]
        d.line(pts + pts[:1], fill=(120, 120, 120), width=3)
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        # (red: U1's and J1's pin 1, and on J2/J3 the contact for the cable's line 1, XUNPU's pin 10)
        first = p.GetNumber() == ("10" if ref in ("J2", "J3") else "1") and ref[0] in "UJ"
        d.rectangle([P(M(bb.GetLeft()) - 100, 200 - M(bb.GetTop())), P(M(bb.GetRight()) - 100, 200 - M(bb.GetBottom()))],
                    fill=(220, 60, 60) if first else (175, 175, 175))
    u, v = uv(fp.GetPosition())
    big = ref[0] == "J"
    x, y = OX + (u - LEFT) * S, OY + (TOP - v) * S
    text(x, y - (2.2 if big else 1.4), ref, 4.0 if big else 2.6, bold=True, anchor="mm")
    text(x, y + (2.4 if big else 1.6), fp.GetValue().split(" (")[0] if big else fp.GetValue(), 2.4 if big else 2.0,
         anchor="mm", fill=(40, 40, 160))
# the cables' line 1 (their printed "1") on J2 and J3: XUNPU contact 10, as the board's silkscreen marks it
for ref in ("J2", "J3"):
    p = [p for p in board.FindFootprintByReference(ref).Pads() if p.GetNumber() == "10"][0]
    u, v = uv(p.GetPosition())
    text(OX + (u - LEFT) * S, OY + (TOP - v) * S + 6.5, 'cable "1"', 2.2, anchor="mm", fill=(200, 40, 40))
text(OX + (90 - LEFT) * S, OY - 4.5, "jacks (the LCD's cable comes down between them)", 2.6,
     anchor="mm")
bottom = OY + (TOP - BOT) * S

notes = [
    "J3: LCD cable in from the top edge, its contacts UP (top-contact socket).",
    "J2: cable from J12 in from the top too, its contacts DOWN (bottom-contact socket).",
    "J1: hinged microSD socket, hinge along the bottom edge, its 8 contact tails toward the resistors.",
    "U1: pin 1 (red) top left; the dot on the part goes there. Resistors and capacitors have no polarity.",
    "Order: J2, J3 (0.5 mm pitch: flux, tack a tab, drag-solder, wick off bridges), then U1, J1, then the 0805s.",
    "Before the FM-1: no short 3V3 (J2 line 7) to GND (line 1); each J2 line beeps through to the same J3 line.",
]
y = bottom + 10
text(15, y, "Notes", 3.6, bold=True)
for n in notes:
    y += 6
    text(15, y, "- " + n, 2.6)

rows = {}
for fp in board.GetFootprints():
    key = (fp.GetValue().split(" (")[0], fp.GetFieldText("LCSC") if fp.HasField("LCSC") else "",
           fp.GetFPID().GetLibItemName().wx_str())
    rows.setdefault(key, []).append(fp.GetReference())
y += 12
text(15, y, "Parts", 3.6, bold=True)
y += 7
for x, h in ((15, "Refs"), (55, "Value"), (110, "LCSC"), (130, "Footprint")):
    text(x, y, h, 2.6, bold=True)
for (value, lcsc, foot), refs in sorted(rows.items(), key=lambda r: sorted(r[1])[0]):
    y += 5.5
    refs = sorted(refs, key=lambda r: (r[0], int(r[1:])))
    for x, s in ((15, ", ".join(refs)), (55, value), (110, lcsc), (130, foot.split("_Pad")[0].replace("_", " ")[:34])):
        text(x, y, s, 2.4)
text(15, 285, "make_assembly.py from m-card.kicad_pcb (CC0-1.0)", 2)

img.save(os.path.join(HERE, "docs", "assembly.pdf"), resolution=DPI)
print("saved docs/assembly.pdf")
