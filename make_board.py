# SPDX-License-Identifier: CC0-1.0
"""m-card: a 30 x 25.2 mm board under the M-VAVE FM-1's audio jacks that puts a microSD card on the LCD's SPI
bus, with no soldering to the FM-1. The LCD's cable (out of J12) plugs into J3; a short 10-pin cable from J12 plugs
into J2; all ten lines pass straight through, and the card taps four of them. The card stays inside the case (hinged
socket, no hot-swap parts); the board sits on double-sided tape over the FM-1's small parts.

Positions are in mm on the FM-1 board's back side: u from its left edge, v up from its bottom edge (KiCad: x = 100 + u,
y = 200 - v). Fit checked with a paper template on the FM-1 (2026-11-03).

  python3 make_board.py place   # parts, nets, outline -> m-card.kicad_pcb, m-card.dsn (for Freerouting)
  python3 make_board.py finish  # import m-card.ses, stitch and pour ground, save
  python3 make_board.py fab     # DRC, then fab/: Gerbers and drill (zipped), bom.csv and cpl.csv for JLC
  python3 make_board.py render  # docs/render-top.png, docs/render-bottom.png

Nets (microSD: 1 DAT2, 2 CS, 3 DI, 4 VDD, 5 CLK, 6 VSS, 7 DAT0/DO, 8 DAT1; J12's lines numbered as the FM-1's cable):
  2 MISO   -> R1 220 -> DAT0, R7 47k up
  3 LCD_CS -> U1 74LVC1G04 -> CARD_CS (the card is selected whenever the LCD is not), R4 47k down
  4 CLK    -> R5 470 -> SD_CLK
  5 MOSI   -> R6 470 -> SD_DI
  7 3V3    -> the card's VDD and U1; C1 10 uF by the socket, C2 100 nF by U1
  DAT1, DAT2: R3, R2 47k up; the card's CMD (DI): R8 47k up
"""
import csv
import json
import math
import os
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KLIB = "/usr/share/kicad/footprints"
MM = pcbnew.FromMM
PCB, DSN, SES = (os.path.join(HERE, f"m-card.{x}") for x in ("kicad_pcb", "dsn", "ses"))

# the outline: under the jacks (from 76.8 up), above the speaker plug J13 (up to about 51; measured 27.3 mm between
# them), right of the 10 V electrolytic (about 2 mm clear on the template)
LEFT, RIGHT, BOT, TOP = 84.5, 114.5, 51.5, 76.7
OUTLINE = [(LEFT, BOT), (RIGHT, BOT), (RIGHT, TOP), (LEFT, TOP)]


def T(u, v):
    return 100.0 + u, 200.0 - v


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def fpc10(board, name, row_y, tab_x, tab_y, tab_h, body_x, body_y0, body_y1):
    """A 10-contact 0.5 mm FPC socket from the maker's land pattern (XUNPU datasheets), its contacts' pads drawn 0.35 mm
    longer outward than the datasheet for an iron's tip. Footprint axes: contacts in a row along x at row_y (pin 1 at
    -x), the two holding tabs (11 at +x, 12 at -x) at tab_y, the body from body_y0 to body_y1."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("m-card", name))
    fp.SetAttributes(pcbnew.FP_SMD)

    def pad(num, x, y, w, h):
        p = pcbnew.PAD(fp)
        p.SetNumber(str(num))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetLayerSet(p.SMDMask())
        p.SetSize(V(w, h))
        p.SetPosition(V(x, y))
        fp.Add(p)

    for n in range(1, 11):
        pad(n, -2.25 + 0.5 * (n - 1), row_y - 0.175, 0.3, 1.6)
    pad(11, tab_x, tab_y, 2.0, tab_h)
    pad(12, -tab_x, tab_y, 2.0, tab_h)
    x0, x1 = -body_x, body_x
    y0, y1 = min(body_y0, row_y - 0.975), body_y1
    for layer, grow, width in ((pcbnew.F_Fab, 0.0, 0.1), (pcbnew.F_CrtYd, 0.25, 0.05)):
        s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_RECT)
        s.SetStart(V(x0 - grow, (y0 if layer == pcbnew.F_CrtYd else body_y0) - grow))
        s.SetEnd(V(x1 + grow, y1 + grow))
        s.SetLayer(layer)
        s.SetWidth(MM(width))
        fp.Add(s)
    fp.MoveAnchorPosition(V(0, -(body_y0 + body_y1) / 2))   # (the origin on the body's centre, for pick-and-place)
    return fp


def dm3cs(board):
    """Hirose DM3CS-SF, a hinged microSD socket, from Hirose's recommended mounting pattern (DM3 catalogue, p. 7).
    Footprint axes: x across with 0 on the card's centre line, y from the hinge end (0) to the contacts' end; the eight
    contacts' tails stick out of that end (iron-solderable), the four shell tabs (GND) on the sides and at the hinge
    end, a card-detect switch pad (10, unused) beside them. Hirose's "no conductive traces" areas are rule areas."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("m-card", "microSD_Hirose_DM3CS-SF_hinged"))
    fp.SetAttributes(pcbnew.FP_SMD)

    def pad(num, x, y, w, h):
        p = pcbnew.PAD(fp)
        p.SetNumber(str(num))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetLayerSet(p.SMDMask())
        p.SetSize(V(w, h))
        p.SetPosition(V(x, y))
        fp.Add(p)

    for n in range(1, 9):
        pad(n, 3.2 - 1.1 * (n - 1), 13.4, 0.7, 2.0)
    pad(9, -6.6, 12.9, 1.0, 2.6)
    pad(9, 6.75, 12.9, 1.5, 2.6)
    pad(9, -3.1, 0.7, 2.7, 1.4)
    pad(9, 1.85, 0.7, 2.7, 1.4)
    pad(10, 4.85, 0.6, 1.2, 1.2)
    for x0, y0, x1, y1 in ((-5.05, 2.9, 3.75, 5.4), (-6.9, 7.8, -6.3, 11.6), (6.7, 7.8, 7.3, 11.6)):
        z = pcbnew.ZONE(fp)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetLayer(pcbnew.F_Cu)
        o = z.Outline()
        o.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            o.Append(MM(x), MM(y))
        fp.Add(z)
    for layer, (x0, y0, x1, y1), width in ((pcbnew.F_Fab, (-6.7, 0.0, 7.1, 13.9), 0.1),
                                          (pcbnew.F_Fab, (-5.5, 4.45, 5.5, 15.45), 0.1),     # the card, locked
                                          (pcbnew.F_CrtYd, (-7.35, -0.25, 7.75, 15.7), 0.05)):
        s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_RECT)
        s.SetStart(V(x0, y0))
        s.SetEnd(V(x1, y1))
        s.SetLayer(layer)
        s.SetWidth(MM(width))
        fp.Add(s)
    # the silkscreen: the body's hinge end and sides (stopping short of the side tabs), a dot by pin 1
    for a, b in (((-6.95, -0.25), (7.35, -0.25)), ((-6.95, -0.25), (-6.95, 11.2)), ((7.35, -0.25), (7.35, 11.2))):
        s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*a))
        s.SetEnd(V(*b))
        s.SetLayer(pcbnew.F_SilkS)
        s.SetWidth(MM(0.15))
        fp.Add(s)
    s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_CIRCLE)
    s.SetCenter(V(3.2, 14.95))
    s.SetEnd(V(3.4, 14.95))
    s.SetFilled(True)
    s.SetLayer(pcbnew.F_SilkS)
    s.SetWidth(MM(0.1))
    fp.Add(s)
    fp.MoveAnchorPosition(V(-0.2, -6.95))         # (the origin on the body's centre, as pick-and-place expects)
    return fp


def build():
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(1.0))
    ds.m_CopperEdgeClearance = MM(0.5)           # (JLC allows 0.3; 0.5 keeps copper clear of their edge-cutting tolerance)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetTrackWidth(MM(0.2))
    nc.SetClearance(MM(0.2))
    nc.SetViaDiameter(MM(0.6))
    nc.SetViaDrill(MM(0.3))
    nets = {}

    def net(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(board, name)
            board.Add(nets[name])
        return nets[name]

    def put(fp, ref, value, u, v, rot, lcsc=""):
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPosition(V(*T(u, v)))
        fp.SetOrientationDegrees(rot)
        if lcsc:
            fp.SetField("LCSC", lcsc)
        for f in fp.GetFields():
            f.SetVisible(False)
        board.Add(fp)
        return fp

    def lib(group, name):
        fp = pcbnew.FootprintLoad(f"{KLIB}/{group}.pretty", name)
        fp.SetFPID(pcbnew.LIB_ID(group, name))
        return fp

    def connect(fp, num, name):
        hit = [p for p in fp.Pads() if p.GetNumber() == str(num)]
        assert hit, f"{fp.GetReference()} has no pad {num}"
        for p in hit:
            p.SetNet(net(name))

    # J3 (the LCD's cable, contacts up) right under the jacks' gap at 90, its opening against the jacks: the cable
    # comes down through the gap and reaches it with a little slack. J2 (the cable from J12, contacts down) under it.
    # Both turned (180), so the cable's line n lands on contact 11 - n.
    J3 = put(fpc10(board, "FPC_10P_0.5_XUNPU_FPC-0.5AS-10PWBH20", -1.16, 3.79, 1.16, 3.0, 5.35, -0.5, 4.1),
             "J3", "FPC 10P 0.5 top contact", 90.0, 74.1, 180, "C3446068")
    J2 = put(fpc10(board, "FPC_10P_0.5_XUNPU_FPC-05F-10PH20", -1.29, 3.94, 1.29, 2.5, 4.7, -0.5, 4.08),
             "J2", "FPC 10P 0.5 bottom contact", 90.0, 60.29, 180, "C2856798")
    AT = {n: 11 - n for n in range(1, 11)}
    # the card: a hinged socket, its hinge end at the bottom, its contacts' tails up toward the small parts (pin 1 at
    # 103.6, pin 8 at 111.3, the locked card's end at 67.65)
    J1 = put(dm3cs(board), "J1", "microSD hinged (Hirose DM3CS-SF)", 106.6, 59.15, 180, "C202111")
    # the small parts in two rows over the socket: 0805 and SOT-23-5 on hand-solder pads (1.25 mm tall at most), the
    # lower row clear of the card's end
    # (pin 1 up: the 3V3 row along the pull-ups' tops, the series resistors' card side down toward the socket)
    R = lambda ref, val, u, v, lcsc, rot=270: put(lib("Resistor_SMD", "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder"),
                                                  ref, val, u, v, rot, lcsc)
    C = lambda ref, val, u, v, lcsc: put(lib("Capacitor_SMD", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"),
                                         ref, val, u, v, 270, lcsc)     # (the ground pad down, toward the pour)
    R4 = R("R4", "47k", 96.6, 73.9, "C17713", 90)
    U1 = put(lib("Package_TO_SOT_SMD", "SOT-23-5_HandSoldering"), "U1", "74LVC1G04", 100.3, 73.9, 0, "C7827")
    C2 = C("C2", "100nF", 104.0, 73.9, "C49678")
    R2 = R("R2", "47k", 106.2, 73.9, "C17713")
    R3 = R("R3", "47k", 111.2, 73.9, "C17713")
    R7 = R("R7", "47k", 108.7, 73.9, "C17713")
    # (the series resistors over their pins: DI 3, CLK 5, DAT0 7)
    C1 = C("C1", "10uF", 102.3, 69.9, "C15850")
    R6 = R("R6", "470", 104.9, 69.9, "C17710")
    R5 = R("R5", "470", 107.5, 69.9, "C17710")
    R1 = R("R1", "220", 110.1, 69.9, "C17557")
    R8 = R("R8", "47k", 99.9, 69.9, "C17713")    # (CMD pulled up on the card side, as the SD spec asks)

    LINES = {1: "GND", 2: "MISO", 3: "LCD_CS", 4: "CLK", 5: "MOSI", 6: "LCD_6", 7: "3V3", 8: "LCD_8", 9: "LCD_9",
             10: "GND"}
    for n, name in LINES.items():
        connect(J2, AT[n], name)
        connect(J3, AT[n], name)
    for fp in (J2, J3):
        connect(fp, 11, "GND")
        connect(fp, 12, "GND")
    for num, name in ((1, "DAT2"), (2, "CARD_CS"), (3, "SD_DI"), (4, "3V3"), (5, "SD_CLK"), (6, "GND"), (7, "DAT0"),
                      (8, "DAT1"), (9, "GND")):
        connect(J1, num, name)                   # (10: the card-detect switch, unused)
    for num, name in ((2, "LCD_CS"), (3, "GND"), (4, "CARD_CS"), (5, "3V3")):
        connect(U1, num, name)
    for fp, a, b in ((R1, "MISO", "DAT0"), (R5, "CLK", "SD_CLK"), (R6, "MOSI", "SD_DI"), (R4, "LCD_CS", "GND"),
                     (R2, "3V3", "DAT2"), (R3, "3V3", "DAT1"), (R7, "3V3", "DAT0"), (R8, "3V3", "SD_DI"), (C1, "3V3", "GND"),
                     (C2, "3V3", "GND")):
        connect(fp, 1, a)
        connect(fp, 2, b)

    for a, b in zip(OUTLINE, OUTLINE[1:] + OUTLINE[:1]):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*T(*a)))
        s.SetEnd(V(*T(*b)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        board.Add(s)

    def rule_area(x0, y0, x1, y1, tracks=True):
        """A rule area on both copper layers (KiCad coordinates, mm) keeping vias, and tracks unless told not to, out."""
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(tracks)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowCopperPour(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetLayerSet(pcbnew.LSET.AllCuMask(2))
        o = z.Outline()
        o.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            o.Append(MM(x), MM(y))
        board.Add(z)

    # strips along the edges that keep tracks and vias out (Freerouting ignores the edge clearance; KiCad keeps the
    # pour back on its own)
    for u0, v0, u1, v1 in ((LEFT, BOT, RIGHT, BOT + 0.35), (LEFT, TOP - 0.35, RIGHT, TOP), (LEFT, BOT, LEFT + 0.35, TOP),
                           (RIGHT - 0.35, BOT, RIGHT, TOP)):
        rule_area(*T(u0, v1), *T(u1, v0))

    def label(s, u, v, size=1.0, layer=pcbnew.F_SilkS):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(V(*T(u, v)))
        t.SetLayer(layer)
        t.SetTextSize(V(size, size))
        t.SetTextThickness(MM(0.15))
        t.SetMirrored(layer == pcbnew.B_SilkS)
        board.Add(t)
        bb = t.GetBoundingBox()                  # (no vias under the text: they'd cut it)
        rule_area(*(pcbnew.ToMM(c) for c in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())), tracks=False)

    label("1", 86.9, 70.6)                      # the cable's line 1 (its printed "1") on each socket
    label("1", 86.9, 56.6)
    label("LCD cable", 90.0, 67.9)
    label("contacts up", 90.0, 66.3)
    label("J12 cable", 90.6, 54.5)
    label("contacts down", 90.6, 52.9)
    label("m-card", 99.0, 64.6, 1.4, pcbnew.B_SilkS)
    label("for FM-1  CC0-1.0", 99.0, 62.6, layer=pcbnew.B_SilkS)
    ds.SetAuxOrigin(V(*T(LEFT, BOT)))
    return board


def stitch(board, pitch=1.0, spacing=3.0):
    """GND vias joining the two pours wherever one fits clear of everything: not in a small part's courtyard, a rule
    area or under text, 0.25 mm clear of other copper, at least `spacing` apart."""
    gnd = board.FindNet("GND")
    r, gap = 0.3, 0.25
    keep = []
    for fp in board.GetFootprints():
        if fp.GetReference()[0] in "RCU":
            fp.BuildCourtyardCaches()
            keep.append(fp.GetCourtyard(pcbnew.F_CrtYd))
        for z in fp.Zones():
            keep.append(z.Outline())
    keep += [z.Outline() for z in board.Zones() if z.GetIsRuleArea()]
    copper = [(p, layer) for fp in board.GetFootprints() for p in fp.Pads() for layer in (pcbnew.F_Cu, pcbnew.B_Cu)
              if p.IsOnLayer(layer)]
    copper += [(t, layer) for t in board.GetTracks() for layer in (pcbnew.F_Cu, pcbnew.B_Cu) if t.IsOnLayer(layer)]
    shapes = [(item.GetEffectiveShape(layer), item.GetNetname() == "GND") for item, layer in copper]
    placed = []
    u = LEFT + 1.2
    while u < RIGHT - 1.0:
        v = BOT + 1.2
        while v < TOP - 1.0:
            x, y = T(u, v)
            pt = V(x, y)
            ok = all(math.hypot(x - a, y - b) >= spacing for a, b in placed)
            ok = ok and not any(k.Contains(pt) or k.Collide(pt, MM(r)) for k in keep)
            circle = pcbnew.SHAPE_CIRCLE(pt, MM(r))
            ok = ok and not any(sh.Collide(circle, MM(gap)) for sh, _ in shapes)
            if ok:
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(pt)
                via.SetWidth(MM(2 * r))
                via.SetDrill(MM(0.3))
                via.SetNet(gnd)
                board.Add(via)
                placed.append((x, y))
            v += pitch
        u += pitch
    return len(placed)


def pour(board):
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(board.FindNet("GND"))
        z.SetLocalClearance(MM(0.25))
        z.SetMinThickness(MM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        o = z.Outline()
        o.NewOutline()
        for u, v in OUTLINE:
            o.Append(*(MM(c) for c in T(u, v)))
        board.Add(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


# what JLC's parts library needs in cpl.csv, seen in its placement preview (mm on the board, degrees): its J2 and J3 have
# their origin between the contact row and the tabs, not at the body's centre; its SOT-23-5 has pin 1 at the other end
JLC_FIX = {"J2": (0.0, -1.79, 0.0), "J3": (0.0, -1.8, 0.0), "U1": (0.0, 0.0, 180.0)}


def fab():
    """A clean DRC (warnings that don't matter for the board allowed), then the files JLC asks for."""
    out = os.path.join(HERE, "fab")
    os.makedirs(out, exist_ok=True)
    cli = lambda *a: subprocess.run(["kicad-cli", "pcb", *a, PCB], check=True, capture_output=True)
    report = os.path.join(out, "drc.json")
    cli("drc", "--format", "json", "--severity-error", "--severity-warning", "-o", report)
    d = json.load(open(report))
    board = pcbnew.LoadBoard(PCB)

    def on_trace(v):
        """A starved thermal is fine on a pad a track of its own net also reaches (GND contacts between others)."""
        for i in v["items"]:
            ref, num = i["description"].split(" of ")[-1].split()[0], i["description"].split()[1]
            fp = board.FindFootprintByReference(ref) if i["description"].startswith("Pad ") else None
            if fp:
                pads = [p for p in fp.Pads() if p.GetNumber() == num]
                return any(t.GetNetCode() == p.GetNetCode() and (p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd()))
                           for p in pads for t in board.GetTracks())
        return False

    ignore = {"lib_footprint_issues"}            # (the footprints are generated here or KiCad's: no project library)
    bad = [v for v in d["violations"] if v["type"] not in ignore and not (v["type"] == "starved_thermal" and on_trace(v))]
    bad += d.get("unconnected_items", [])
    for v in bad:
        print("DRC:", v.get("type", "unconnected"), v.get("description", ""), [i["description"] for i in v["items"]])
    assert not bad, f"{len(bad)} DRC problems"
    gerb = os.path.join(out, "gerbers")
    os.makedirs(gerb, exist_ok=True)
    # (one origin for everything: the board's bottom-left corner, the auxiliary origin, as the placement file uses)
    cli("export", "gerbers", "--layers", "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts",
        "--subtract-soldermask", "--use-drill-file-origin", "-o", gerb)
    cli("export", "drill", "--format", "excellon", "--excellon-units", "mm", "--drill-origin", "plot",
        "--generate-map", "--map-format", "gerberx2", "-o", gerb + os.sep)
    with zipfile.ZipFile(os.path.join(out, "m-card-gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gerb)):
            z.write(os.path.join(gerb, f), f)
    pos = os.path.join(out, "pos.csv")
    cli("export", "pos", "--format", "csv", "--units", "mm", "--side", "front", "--use-drill-file-origin", "-o", pos)
    rows = {}
    for fp in board.GetFootprints():
        key = (fp.GetValue(), fp.GetFPID().GetLibItemName().wx_str(), fp.GetFieldText("LCSC") if fp.HasField("LCSC") else "")
        rows.setdefault(key, []).append(fp.GetReference())
    with open(os.path.join(out, "bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, lcsc), refs in sorted(rows.items(), key=lambda r: r[1]):
            w.writerow([value, ",".join(sorted(refs, key=lambda r: (r[0], int(r[1:])))), footprint, lcsc])
    with open(pos) as f, open(os.path.join(out, "cpl.csv"), "w", newline="") as g:
        w = csv.writer(g)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in csv.DictReader(f):
            dx, dy, rot = JLC_FIX.get(r["Ref"], (0.0, 0.0, 0.0))
            w.writerow([r["Ref"], f"{float(r['PosX']) + dx:.3f}mm", f"{float(r['PosY']) + dy:.3f}mm", "Top",
                        f"{(float(r['Rot']) + rot) % 360:.1f}"])
    print("saved", out, ": m-card-gerbers.zip, bom.csv, cpl.csv (check the rotations in JLC's placement preview)")


def render():
    """docs/render-top.png and -bottom.png, with KiCad's 3D models for the stock parts fetched into 3d/ (the generated
    connectors have none)."""
    models = os.path.join(HERE, "3d")
    for m in ("Resistor_SMD/R_0805_2012Metric", "Capacitor_SMD/C_0805_2012Metric", "Package_TO_SOT_SMD/SOT-23-5"):
        group, name = m.split("/")
        path = os.path.join(models, f"{group}.3dshapes", f"{name}.step")
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            url = f"https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/master/{group}.3dshapes/{name}.step"
            subprocess.run(["curl", "-sSfL", "-o", path, url], check=True)
    env = dict(os.environ, KICAD9_3DMODEL_DIR=models)
    for side in ("top", "bottom"):
        subprocess.run(["kicad-cli", "pcb", "render", "--side", side, "--width", "1400", "--height", "1100", "--quality",
                        "high", "--zoom", "1.0", "-o", os.path.join(HERE, "docs", f"render-{side}.png"), PCB],
                       check=True, capture_output=True, env=env)
    print("saved docs/render-top.png, docs/render-bottom.png")


if sys.argv[1:] == ["place"]:
    b = build()
    b.Save(PCB)
    b = pcbnew.LoadBoard(PCB)
    assert pcbnew.ExportSpecctraDSN(b, DSN), "DSN export failed"
    print("saved", PCB, DSN)
elif sys.argv[1:] == ["finish"]:
    b = pcbnew.LoadBoard(PCB)
    assert pcbnew.ImportSpecctraSES(b, SES), "SES import failed"
    n = stitch(b)
    pour(b)
    b.Save(PCB)
    print("saved", PCB, f"({n} stitching vias)")
elif sys.argv[1:] == ["fab"]:
    fab()
elif sys.argv[1:] == ["render"]:
    render()
else:
    sys.exit(__doc__)
