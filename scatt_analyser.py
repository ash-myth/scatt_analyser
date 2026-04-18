"""
SCATT Performance Analyser
Session intelligence engine + PDF report generator
Works with .scatt-expert files (SQLite format)
"""

import sqlite3
import struct
import zlib
import math
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect, Circle, Line, String
from reportlab.graphics import renderPDF

C_BG        = colors.HexColor("#0D1117")
C_PANEL     = colors.HexColor("#161B22")
C_BORDER    = colors.HexColor("#30363D")
C_GREEN     = colors.HexColor("#3FB950")
C_AMBER     = colors.HexColor("#D29922")
C_RED       = colors.HexColor("#F85149")
C_BLUE      = colors.HexColor("#58A6FF")
C_WHITE     = colors.HexColor("#E6EDF3")
C_MUTED     = colors.HexColor("#8B949E")
C_GOLD      = colors.HexColor("#FFD700")
C_SCATT_MAG = colors.HexColor("#E040FB") 

# ─────────────────────────────────────────────
#  COLUMN DEFINITIONS (from reverse-engineering)
# ─────────────────────────────────────────────
# # = shot number
# D = drift direction arrow at moment of shot
# R = result / score (decimal, e.g. 10.6)
# T = total aiming time in seconds (= trace_offset / sample_rate)
# 10.0 = % of aiming time aimpoint spent inside 10-ring radius
# 10a0 = % of final aiming phase inside 10-ring
# S1  = barrel speed in last 1.0 second (mm/s)
# S2  = barrel speed in last 0.25 second (mm/s)
# DA  = deviation of aimpoint from centre at exact moment of shot (mm)


# ─────────────────────────────────────────────
#  BENCHMARKS  (10m Air Rifle)
# ─────────────────────────────────────────────
BENCH = {
    "score_elite":       10.5,
    "score_good":        10.3,
    "DA_elite":          1.0,    # mm — deviation at shot moment
    "DA_good":           2.0,
    "S2_elite":          10.0,   # mm/s — very slow final approach
    "S2_good":           14.0,
    "S1_elite":          12.0,
    "hold_pct_elite":    98,     # % time in 10-ring
    "hold_pct_good":     90,
    "aiming_min":         7.0,   # seconds — too quick
    "aiming_max":        14.0,   # seconds — too slow, hunt begins
    "aiming_sweet":      10.0,   # ideal
    "interval_min":      40.0,   # seconds between shots
    "interval_max":      90.0,
}

def load_session(filepath: str) -> dict:
    """Load and parse a .scatt-expert SQLite file."""
    conn = sqlite3.connect(filepath)
    cur  = conn.cursor()

    cur.execute("""
        SELECT s.session_id, p.name, s.distance, s.caliber,
               s.sample_rate, s.shot_count, s.timer, s.F
        FROM sessions s JOIN persons p ON s.person_id = p.person_id
        LIMIT 1
    """)
    row = cur.fetchone()
    session = {
        "session_id":  row[0],
        "shooter":     row[1],
        "distance_m":  row[2],
        "caliber_mm":  row[3],
        "sample_rate": row[4],
        "shot_count":  row[5],
        "start_timer": row[6],
        "F":           row[7],
    }

    cur.execute("""
        SELECT s.shot_id, s.timer, s.trace_offset,
               t.timer_enter, length(t.data) as dlen
        FROM shots s
        JOIN traces t ON s.trace_id = t.trace_id
        WHERE s.deleted = 0
        ORDER BY s.shot_id
    """)
    raw_shots = cur.fetchall()
    conn.close()

    sr = session["sample_rate"]
    shots = []
    prev_timer = None

    for shot_id, timer, trace_offset, timer_enter, dlen in raw_shots:
        aiming_sec = trace_offset / sr
        interval   = (timer - prev_timer) / 1000.0 if prev_timer else None
        prev_timer = timer

        shots.append({
            "id":          shot_id,
            "timer":       timer,
            "aiming_sec":  round(aiming_sec, 2),
            "interval":    round(interval, 1) if interval else None,
            "dlen":        dlen,
            "score":       None,
            "direction":   None,
            "hold_10":     None,   # % in 10-ring full aiming
            "hold_10a":    None,   # % in 10-ring final phase
            "S1":          None,   # speed last 1.0s
            "S2":          None,   # speed last 0.25s
            "DA":          None,   # deviation at shot moment (mm)
        })

    session["shots"] = shots
    return session


def inject_screenshot_data(session: dict, shot_metrics: list) -> None:
    """
    Merge per-shot metrics read from the SCATT UI into the session.
    OCR aiming_sec overrides DB-derived value when present.
    """
    lookup = {m["id"]: m for m in shot_metrics}
    for shot in session["shots"]:
        m = lookup.get(shot["id"])
        if m:
            # Override DB aiming_sec with OCR value if available
            if m.get("aiming_sec") is not None:
                shot["aiming_sec"] = m["aiming_sec"]
            shot.update({k: v for k, v in m.items() if k != "aiming_sec"})

def rate_value(val, good_thresh, elite_thresh, lower_is_better=True):
    """Return 'green'/'amber'/'red' rating."""
    if val is None:
        return "grey"
    if lower_is_better:
        if val <= elite_thresh: return "green"
        if val <= good_thresh:  return "amber"
        return "red"
    else:
        if val >= elite_thresh: return "green"
        if val >= good_thresh:  return "amber"
        return "red"


def classify_shot(shot: dict) -> dict:
    """
    Return a rich diagnosis dict for a single shot.
    """
    diag = {"flags": [], "archetype": None, "rating": "green", "summary": ""}

    score   = shot.get("score")
    DA      = shot.get("DA")
    S2      = shot.get("S2")
    S1      = shot.get("S1")
    hold_10 = shot.get("hold_10")  # e.g. 74 (%)
    hold_10a= shot.get("hold_10a")
    t       = shot.get("aiming_sec")
    iv      = shot.get("interval")

    # — Aiming time flags —
    if t is not None:
        if t < BENCH["aiming_min"]:
            diag["flags"].append(("RUSHED", "Fired too quickly — hold may not have settled."))
        elif t > BENCH["aiming_max"]:
            diag["flags"].append(("PROLONGED", f"Aiming time {t:.1f}s is long — hunt risk increases."))

    # — Interval flags —
    if iv is not None:
        if iv > 85:
            diag["flags"].append(("LONG PAUSE", f"{iv:.0f}s between shots — check focus/routine."))

    # — Deviation at shot (DA) —
    if DA is not None:
        if DA > BENCH["DA_good"]:
            diag["flags"].append(("HIGH DEVIATION", f"Shot released {DA}mm from centre — timing or coordination issue."))
        elif DA > BENCH["DA_elite"]:
            diag["flags"].append(("DEVIATION", f"{DA}mm offset at release — aim for <1mm."))

    # — Final speed S2 —
    if S2 is not None:
        if S2 > BENCH["S2_good"]:
            diag["flags"].append(("FAST FINAL PHASE", f"Barrel moving at {S2:.1f}mm/s in last 0.25s — possible flinch or rush."))
        elif S2 > BENCH["S2_elite"]:
            diag["flags"].append(("SPEED WARNING", f"S2={S2:.1f}mm/s — slow down the final approach."))

    # — Hold stability —
    if hold_10 is not None:
        h = int(str(hold_10).replace("%", "")) if isinstance(hold_10, str) else hold_10
        if h < BENCH["hold_pct_good"]:
            diag["flags"].append(("POOR HOLD", f"Only {h}% of aiming time in 10-ring — stability needs work."))
        elif h < BENCH["hold_pct_elite"]:
            diag["flags"].append(("HOLD DRIFT", f"{h}% in 10-ring — close but not elite-level consistency."))

    # — Archetype classification —
    if DA is not None and DA > 2.5 and S2 is not None and S2 > 14:
        diag["archetype"] = "FLINCH / SNATCH"
        diag["flags"].append(("FLINCH SIGNATURE", "High deviation + fast final phase = likely trigger snatch or anticipation."))
    elif t is not None and t > 13.5 and hold_10 is not None:
        h = int(str(hold_10).replace("%", "")) if isinstance(hold_10, str) else hold_10
        if h < 85:
            diag["archetype"] = "HUNT & FIRE"
            diag["flags"].append(("HUNT DETECTED", "Long hold with poor 10-ring time = barrel was hunting, fired in a poor position."))
    elif DA is not None and DA < 0.8 and S2 is not None and S2 < 10:
        diag["archetype"] = "CLEAN RELEASE"
    elif t is not None and t < 8.0:
        diag["archetype"] = "RUSHED"
    else:
        diag["archetype"] = "AVERAGE"

    red_flags   = [f for f in diag["flags"] if f[0] in ("FLINCH SIGNATURE","HIGH DEVIATION","POOR HOLD","HUNT DETECTED","FAST FINAL PHASE")]
    amber_flags = [f for f in diag["flags"] if f[0] in ("PROLONGED","DEVIATION","HOLD DRIFT","SPEED WARNING","LONG PAUSE","RUSHED")]

    if red_flags:
        diag["rating"] = "red"
    elif amber_flags:
        diag["rating"] = "amber"
    else:
        diag["rating"] = "green"

    if diag["archetype"] == "CLEAN RELEASE":
        diag["summary"] = "Clean. Low deviation, controlled final approach."
    elif diag["archetype"] == "FLINCH / SNATCH":
        diag["summary"] = "Flinch signature. Slow down trigger pull, don't anticipate the shot."
    elif diag["archetype"] == "HUNT & FIRE":
        diag["summary"] = "Hunting detected. Reset and re-enter if hold doesn't settle by 12s."
    elif diag["archetype"] == "RUSHED":
        diag["summary"] = "Too quick. Allow hold to settle before committing to trigger."
    else:
        if red_flags:
            diag["summary"] = red_flags[0][1]
        elif amber_flags:
            diag["summary"] = amber_flags[0][1]
        else:
            diag["summary"] = "Acceptable. Minor refinements available."

    return diag


def analyse_session(session: dict) -> dict:
    """Run full session analysis. Returns enriched analysis object."""
    shots = session["shots"]
    scored = [s for s in shots if s.get("score") is not None]

    scores    = [s["score"]     for s in scored]
    DAs       = [s["DA"]        for s in scored if s.get("DA") is not None]
    S2s       = [s["S2"]        for s in scored if s.get("S2") is not None]
    S1s       = [s["S1"]        for s in scored if s.get("S1") is not None]
    aim_times = [s["aiming_sec"]for s in scored]
    intervals = [s["interval"]  for s in scored if s.get("interval")]

    def mean(lst): return sum(lst)/len(lst) if lst else None
    def stdev(lst):
        if len(lst) < 2: return 0
        m = mean(lst)
        return math.sqrt(sum((x-m)**2 for x in lst)/len(lst))

    diagnoses = {}
    for shot in scored:
        diagnoses[shot["id"]] = classify_shot(shot)

    red_shots   = [s["id"] for s in scored if diagnoses[s["id"]]["rating"] == "red"]
    amber_shots = [s["id"] for s in scored if diagnoses[s["id"]]["rating"] == "amber"]
    green_shots = [s["id"] for s in scored if diagnoses[s["id"]]["rating"] == "green"]
    n = len(scored)
    first_third = scored[:n//3]
    last_third  = scored[-(n//3):]
    first_scores = [s["score"] for s in first_third]
    last_scores  = [s["score"] for s in last_third]
    fatigue_delta = mean(last_scores) - mean(first_scores) if first_scores and last_scores else 0

    all_flag_types = {}
    for d in diagnoses.values():
        for flag_name, _ in d["flags"]:
            all_flag_types[flag_name] = all_flag_types.get(flag_name, 0) + 1
    top_issues = sorted(all_flag_types.items(), key=lambda x: -x[1])[:3]

    drills = []
    issue_names = [i[0] for i in top_issues]
    if "FLINCH SIGNATURE" in issue_names or "FAST FINAL PHASE" in issue_names:
        drills.append({
            "name": "Surprise Break Drill",
            "desc": "Load without looking. Have a training partner confirm shots. Remove anticipation by making the exact fire moment unknown to you.",
            "duration": "10 shots"
        })
    if "HUNT & FIRE" in issue_names or "PROLONGED" in issue_names:
        drills.append({
            "name": "12-Second Rule",
            "desc": "If your aimpoint hasn't settled inside the 10-ring within 12 seconds, lower the rifle and restart. Never fire a hunting shot.",
            "duration": "Full session discipline"
        })
    if "HIGH DEVIATION" in issue_names or "DEVIATION" in issue_names:
        drills.append({
            "name": "Blind Shot / Natural Point of Aim",
            "desc": "Close eyes, settle into position, open eyes. Where is your aimpoint? Adjust body — not muscle — until it's centred. Repeat before every shot.",
            "duration": "Pre-session routine"
        })
    if not drills:
        drills.append({
            "name": "Consistency Consolidation",
            "desc": "Your technique is solid. Focus on replicating your best shots. Review your top 5 green shots and identify what felt different.",
            "duration": "Ongoing"
        })

    return {
        "session":        session,
        "scored_shots":   scored,
        "diagnoses":      diagnoses,
        "mean_score":     round(mean(scores), 3) if scores else None,
        "stdev_score":    round(stdev(scores), 3) if scores else None,
        "total_score":    round(sum(scores), 1) if scores else None,
        "mean_DA":        round(mean(DAs), 2) if DAs else None,
        "mean_S2":        round(mean(S2s), 2) if S2s else None,
        "mean_S1":        round(mean(S1s), 2) if S1s else None,
        "mean_aim_time":  round(mean(aim_times), 2) if aim_times else None,
        "mean_interval":  round(mean(intervals), 1) if intervals else None,
        "red_shots":      red_shots,
        "amber_shots":    amber_shots,
        "green_shots":    green_shots,
        "fatigue_delta":  round(fatigue_delta, 3),
        "top_issues":     top_issues,
        "drills":         drills,
    }

def build_report(analysis: dict, output_path: str):
    session  = analysis["session"]
    shots    = analysis["scored_shots"]
    diagnoses= analysis["diagnoses"]

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm,  bottomMargin=12*mm,
    )

    W = A4[0] - 30*mm   # usable width

    # ── Styles ──
    styles = getSampleStyleSheet()

    def style(name, **kw):
        base = kw.pop("base", "Normal")
        s = ParagraphStyle(name, parent=styles[base], **kw)
        return s

    S_title   = style("title",   fontSize=22, textColor=C_WHITE,   leading=28, spaceAfter=2)
    S_sub     = style("sub",     fontSize=10, textColor=C_MUTED,   leading=14, spaceAfter=8)
    S_h2      = style("h2",      fontSize=13, textColor=C_BLUE,    leading=18, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold")
    S_h3      = style("h3",      fontSize=10, textColor=C_WHITE,   leading=14, spaceBefore=6,  spaceAfter=2, fontName="Helvetica-Bold")
    S_body    = style("body",    fontSize=8.5,textColor=C_WHITE,   leading=13)
    S_muted   = style("muted",   fontSize=8,  textColor=C_MUTED,   leading=12)
    S_green   = style("green",   fontSize=9,  textColor=C_GREEN,   leading=13, fontName="Helvetica-Bold")
    S_amber   = style("amber",   fontSize=9,  textColor=C_AMBER,   leading=13, fontName="Helvetica-Bold")
    S_red_s   = style("red_s",   fontSize=9,  textColor=C_RED,     leading=13, fontName="Helvetica-Bold")
    S_centre  = style("centre",  fontSize=9,  textColor=C_WHITE,   leading=13, alignment=TA_CENTER)
    S_drill   = style("drill",   fontSize=8.5,textColor=C_WHITE,   leading=13, leftIndent=6)

    story = []

    def dark_table(data, col_widths, style_cmds, row_heights=None):
        t = Table(data, colWidths=col_widths, rowHeights=row_heights)
        base = [
            ("BACKGROUND",  (0,0), (-1,-1), C_PANEL),
            ("GRID",        (0,0), (-1,-1), 0.5, C_BORDER),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[C_PANEL, colors.HexColor("#0F1419")]),
            ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING",  (0,0),(-1,-1), 6),
            ("RIGHTPADDING", (0,0),(-1,-1), 6),
            ("TOPPADDING",   (0,0),(-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ]
        t.setStyle(TableStyle(base + style_cmds))
        return t

    shooter  = session["shooter"].title()
    dist     = f"{session['distance_m']:.0f}m"
    caliber  = f"{session['caliber_mm']}mm"
    n_shots  = session["shot_count"]

    ts_ms    = session["start_timer"]
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000)
        date_str = dt.strftime("%d %b %Y  %H:%M")
    except:
        date_str = "—"

    story.append(Paragraph("SCATT PERFORMANCE REPORT", S_title))
    story.append(Paragraph(f"{shooter}  ·  {dist} Air Rifle  ·  {caliber}  ·  {date_str}  ·  {n_shots} shots", S_sub))
    story.append(HRFlowable(width="100%", thickness=1, color=C_BLUE, spaceAfter=10))

    story.append(Paragraph("SESSION SCORECARD", S_h2))

    def stat_cell(label, value, unit="", rating=None):
        colour = {"green": C_GREEN, "amber": C_AMBER, "red": C_RED}.get(rating, C_WHITE)
        return [
            Paragraph(label, S_muted),
            Paragraph(f'<font color="#{colour.hexval()[2:]}">{value}</font> <font size="7" color="#{C_MUTED.hexval()[2:]}">{unit}</font>', S_h3)
        ]

    mean_sc  = analysis["mean_score"]
    tot_sc   = analysis["total_score"]
    n_sc     = len(shots)
    mean_DA  = analysis["mean_DA"]
    mean_S2  = analysis["mean_S2"]
    mean_aim = analysis["mean_aim_time"]
    fat_d    = analysis["fatigue_delta"]

    sc_rating = "green" if mean_sc and mean_sc >= BENCH["score_elite"] else ("amber" if mean_sc and mean_sc >= BENCH["score_good"] else "red")
    da_rating = rate_value(mean_DA, BENCH["DA_good"], BENCH["DA_elite"])
    s2_rating = rate_value(mean_S2, BENCH["S2_good"], BENCH["S2_elite"])
    fat_rating= "green" if fat_d >= -0.05 else ("amber" if fat_d >= -0.15 else "red")

    scorecard_data = [
        [Paragraph("METRIC", S_muted), Paragraph("VALUE", S_muted), Paragraph("BENCHMARK", S_muted), Paragraph("STATUS", S_muted)],
        [Paragraph("Mean Score",   S_body), Paragraph(f"{mean_sc:.3f}" if mean_sc else "—", S_body), Paragraph("≥ 10.5 elite", S_muted), Paragraph(sc_rating.upper(),  ParagraphStyle("x", textColor={"green":C_GREEN,"amber":C_AMBER,"red":C_RED}.get(sc_rating, C_MUTED), fontSize=8, fontName="Helvetica-Bold"))],
        [Paragraph("Total Score",  S_body), Paragraph(f"{tot_sc:.1f}" if tot_sc else "—", S_body), Paragraph(f"/{n_sc*10.9:.0f} theoretical", S_muted), Paragraph("", S_body)],
        [Paragraph("Mean DA (mm)", S_body), Paragraph(f"{mean_DA:.2f}" if mean_DA else "—", S_body), Paragraph("< 1.0 elite", S_muted), Paragraph(da_rating.upper(), ParagraphStyle("x2", textColor={"green":C_GREEN,"amber":C_AMBER,"red":C_RED}.get(da_rating, C_MUTED), fontSize=8, fontName="Helvetica-Bold"))],
        [Paragraph("Mean S2 (mm/s)",S_body),Paragraph(f"{mean_S2:.1f}" if mean_S2 else "—", S_body), Paragraph("< 10 elite", S_muted), Paragraph(s2_rating.upper(), ParagraphStyle("x3", textColor={"green":C_GREEN,"amber":C_AMBER,"red":C_RED}.get(s2_rating, C_MUTED), fontSize=8, fontName="Helvetica-Bold"))],
        [Paragraph("Mean Aim Time",S_body), Paragraph(f"{mean_aim:.1f}s" if mean_aim else "—", S_body), Paragraph("8–12s ideal", S_muted), Paragraph("", S_body)],
        [Paragraph("Fatigue Trend",S_body), Paragraph(f"{fat_d:+.3f}" if fat_d else "0", S_body), Paragraph("≥ 0 ideal", S_muted), Paragraph(fat_rating.upper(), ParagraphStyle("x4", textColor={"green":C_GREEN,"amber":C_AMBER,"red":C_RED}.get(fat_rating, C_MUTED), fontSize=8, fontName="Helvetica-Bold"))],
    ]

    scorecard = dark_table(
        scorecard_data,
        [W*0.30, W*0.20, W*0.30, W*0.20],
        [("BACKGROUND", (0,0), (-1,0), C_BORDER),
         ("TEXTCOLOR",  (0,0), (-1,0), C_MUTED),
         ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
         ("FONTSIZE",   (0,0), (-1,0), 8),]
    )
    story.append(scorecard)
    story.append(Spacer(1, 8))

    n_g = len(analysis["green_shots"])
    n_a = len(analysis["amber_shots"])
    n_r = len(analysis["red_shots"])
    total = n_g + n_a + n_r or 1

    story.append(Paragraph("SHOT HEALTH BREAKDOWN", S_h2))
    health_data = [[
        Paragraph(f'<font color="#{C_GREEN.hexval()[2:]}">{n_g} CLEAN</font>', S_centre),
        Paragraph(f'<font color="#{C_AMBER.hexval()[2:]}">{n_a} WATCH</font>',  S_centre),
        Paragraph(f'<font color="#{C_RED.hexval()[2:]}">{n_r} ISSUE</font>',    S_centre),
    ]]
    health_tbl = dark_table(health_data, [W/3]*3,
        [("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),
         ("FONTSIZE",(0,0),(-1,-1),12),
         ("TOPPADDING",(0,0),(-1,-1),8),
         ("BOTTOMPADDING",(0,0),(-1,-1),8)])
    story.append(health_tbl)
    story.append(Spacer(1, 8))
    story.append(Paragraph("KEY ISSUES THIS SESSION", S_h2))
    issue_rows = [[Paragraph("ISSUE", S_muted), Paragraph("COUNT", S_muted), Paragraph("WHAT IT MEANS", S_muted)]]
    issue_explanations = {
        "FLINCH SIGNATURE": "High deviation + fast trigger = anticipating the shot. Relax trigger finger.",
        "FAST FINAL PHASE": "Barrel moving too fast in last 0.25s. Decelerate the trigger pull.",
        "HIGH DEVIATION":   "Shot released far from centre. Improve coordination — fire at hold minimum.",
        "DEVIATION":        "Moderate offset at release. Watch for your best hold window.",
        "POOR HOLD":        "Less than 90% time in 10-ring. Position or NPA needs adjustment.",
        "HOLD DRIFT":       "Close to elite. Small position changes may lock in the 10-ring.",
        "PROLONGED":        "Aiming too long — hold degrades after 12–13s. Decide earlier.",
        "HUNT & FIRE":      "Fired while hold was not settled. Lower and restart.",
        "RUSHED":           "Shot fired before hold settled. Slow the approach phase.",
        "LONG PAUSE":       "Long gap between shots — check mental reset routine.",
        "SPEED WARNING":    "Final approach still slightly fast. Practice slow trigger pressure.",
    }
    for issue, count in analysis["top_issues"]:
        expl = issue_explanations.get(issue, "")
        issue_rows.append([
            Paragraph(issue, ParagraphStyle("issue", textColor=C_AMBER, fontSize=8, fontName="Helvetica-Bold")),
            Paragraph(str(count), S_body),
            Paragraph(expl, S_muted),
        ])
    if len(issue_rows) == 1:
        issue_rows.append([Paragraph("No major issues detected", S_green), Paragraph("—", S_body), Paragraph("Strong session.", S_body)])

    story.append(dark_table(issue_rows, [W*0.28, W*0.10, W*0.62],
        [("BACKGROUND",(0,0),(-1,0), C_BORDER),
         ("FONTNAME",  (0,0),(-1,0),"Helvetica-Bold"),
         ("FONTSIZE",  (0,0),(-1,0),8)]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("PRESCRIBED DRILLS", S_h2))
    for drill in analysis["drills"]:
        drill_data = [[
            Paragraph(f'◉  {drill["name"]}', S_h3),
            Paragraph(drill["duration"], S_muted),
        ],[
            Paragraph(drill["desc"], S_drill),
            Paragraph("", S_body),
        ]]
        dt = dark_table(drill_data, [W*0.78, W*0.22],
            [("SPAN",(0,1),(1,1)),
             ("TOPPADDING",(0,0),(-1,-1),5),
             ("BOTTOMPADDING",(0,0),(-1,-1),5)])
        story.append(dt)
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 8))

    story.append(Paragraph("PER-SHOT ANALYSIS", S_h2))

    header = [
        Paragraph("#",       S_muted),
        Paragraph("Score",   S_muted),
        Paragraph("DA mm",   S_muted),
        Paragraph("S1",      S_muted),
        Paragraph("S2",      S_muted),
        Paragraph("Aim s",   S_muted),
        Paragraph("Int s",   S_muted),
        Paragraph("Status",  S_muted),
        Paragraph("Diagnosis", S_muted),
    ]
    shot_rows = [header]

    for shot in shots:
        d = diagnoses.get(shot["id"], {})
        rating  = d.get("rating", "green")
        summary = d.get("summary", "—")
        arch    = d.get("archetype", "")

        rc = {"green": C_GREEN, "amber": C_AMBER, "red": C_RED}.get(rating, C_MUTED)

        def val(v, fmt="{:.1f}", fallback="—"):
            return fmt.format(v) if v is not None else fallback

        row = [
            Paragraph(str(shot["id"]), S_body),
            Paragraph(val(shot.get("score"), "{:.1f}"), S_body),
            Paragraph(val(shot.get("DA"),    "{:.1f}"), S_body),
            Paragraph(val(shot.get("S1"),    "{:.1f}"), S_body),
            Paragraph(val(shot.get("S2"),    "{:.1f}"), S_body),
            Paragraph(val(shot.get("aiming_sec"), "{:.1f}"), S_body),
            Paragraph(val(shot.get("interval"),   "{:.0f}"), S_body),
            Paragraph(f'<font color="#{rc.hexval()[2:]}">{arch or rating.upper()}</font>',
                      ParagraphStyle("st", fontSize=7, fontName="Helvetica-Bold")),
            Paragraph(summary[:70], S_muted),
        ]
        shot_rows.append(row)

    col_w = [W*f for f in [0.04, 0.07, 0.07, 0.06, 0.06, 0.07, 0.06, 0.12, 0.45]]
    shot_tbl = dark_table(shot_rows, col_w,
        [("BACKGROUND",(0,0),(-1,0), C_BORDER),
         ("FONTNAME",  (0,0),(-1,0),"Helvetica-Bold"),
         ("FONTSIZE",  (0,0),(-1,-1),7),
         ("TOPPADDING",(0,0),(-1,-1),3),
         ("BOTTOMPADDING",(0,0),(-1,-1),3)])
    story.append(shot_tbl)
    story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=4))
    story.append(Paragraph(
        "Generated by SCATT Performance Analyser  ·  Benchmarks: ISSF 10m Air Rifle  ·  Not affiliated with MEC-SCATT",
        ParagraphStyle("footer", fontSize=7, textColor=C_MUTED, alignment=TA_CENTER)
    ))

    doc.build(story)
    print(f"[OK] Report saved → {output_path}")

if __name__ == "__main__":
    import argparse
    from scatt_ocr import extract as ocr_extract

    parser = argparse.ArgumentParser(
        description="SCATT Performance Analyser — dynamic OCR pipeline"
    )
    parser.add_argument(
        "db",
        help="Path to .scatt-expert SQLite file",
        nargs="?",
        default="sample-data.scatt-expert",
    )
    parser.add_argument(
        "screenshot",
        help="Path to SCATT Expert table screenshot (PNG/JPG)",
        nargs="?",
        default=None,
    )
    parser.add_argument(
        "--out",
        help="Output PDF path (default: SCATT_Report_<shooter>.pdf)",
        default=None,
    )
    parser.add_argument(
        "--ocr-only",
        action="store_true",
        help="Just run OCR and print extracted metrics, no PDF",
    )
    args = parser.parse_args()

    # ── 1. Load session from DB ──────────────────────────────────────────────
    print(f"[1/4] Loading session from: {args.db}")
    session = load_session(args.db)
    shooter = session["shooter"].title()
    print(f"      Shooter: {shooter}  |  DB shots: {session['shot_count']}")

    # ── 2. OCR the screenshot ────────────────────────────────────────────────
    if args.screenshot:
        img_path = args.screenshot
    else:
        # Auto-detect: look for any PNG/JPG in current directory
        import glob
        candidates = glob.glob("*.png") + glob.glob("*.jpg") + glob.glob("*.jpeg")
        # Prefer files with 'scatt' in name
        scatt_candidates = [f for f in candidates if "scatt" in f.lower()]
        img_path = scatt_candidates[0] if scatt_candidates else (candidates[0] if candidates else None)

    if img_path:
        print(f"[2/4] Running OCR on: {img_path}")
        shot_metrics = ocr_extract(img_path)
        print(f"      Extracted {len(shot_metrics)} shots — "
              f"DA coverage: {sum(1 for s in shot_metrics if s.get('DA') is not None)}/{len(shot_metrics)}")

        if args.ocr_only:
            print("\nExtracted metrics:")
            for s in shot_metrics:
                print(f"  {s}")
            raise SystemExit(0)

        inject_screenshot_data(session, shot_metrics)
    else:
        print("[2/4] No screenshot found — proceeding with DB data only (metrics will be partial)")

    # ── 3. Analyse ───────────────────────────────────────────────────────────
    print("[3/4] Analysing session...")
    analysis = analyse_session(session)

    n_scored = len(analysis["scored_shots"])
    print(f"\n{'='*52}")
    print(f"  Shooter    : {shooter}")
    print(f"  Shots      : {n_scored}")
    print(f"  Mean Score : {analysis['mean_score']}  (σ={analysis['stdev_score']})")
    print(f"  Total      : {analysis['total_score']}  / {n_scored * 10:.0f} possible")
    print(f"  Mean DA    : {analysis['mean_DA']} mm")
    print(f"  Mean S2    : {analysis['mean_S2']} mm/s")
    print(f"  Green      : {len(analysis['green_shots'])} shots")
    print(f"  Amber      : {len(analysis['amber_shots'])} shots")
    print(f"  Red        : {len(analysis['red_shots'])} shots")
    print(f"  Fatigue Δ  : {analysis['fatigue_delta']:+.3f}")
    print(f"  Top issue  : {analysis['top_issues'][0] if analysis['top_issues'] else 'None'}")
    print(f"{'='*52}\n")

    # ── 4. Build PDF ─────────────────────────────────────────────────────────
    out_path = args.out or f"SCATT_Report_{shooter.replace(' ', '_')}.pdf"
    print(f"[4/4] Building PDF → {out_path}")
    build_report(analysis, out_path)
    print("      Done.")