"""
streamlit_app.py — SCATT Performance Analyser
Run: streamlit run streamlit_app.py
"""

import os
import sys
import time
import uuid
import tempfile
import threading
import traceback
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(__file__))
from scatt_ocr import extract as ocr_extract
from scatt_analyser import load_session, inject_screenshot_data, analyse_session, build_report

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SCATT Analyser",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;600;800&family=Space+Grotesk:wght@400;600;700;800&display=swap');

:root {
    --bg:        #0b0d11;
    --surface:   #13161d;
    --border:    #1e2330;
    --accent:    #e8ff47;
    --accent2:   #47ffe8;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --green:     #4ade80;
    --amber:     #fbbf24;
    --red:       #f87171;
    --mono:      'JetBrains Mono', monospace;
    --sans:      'Syne', sans-serif;
}

/* Global */
html, body, [class*="css"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--sans) !important;
}

/* Header */
.scatt-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 2rem 0 0.5rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2rem;
}
.scatt-header h1 {
    font-family: var(--sans);
    font-size: 2.2rem;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: -0.03em;
    margin: 0;
}
.scatt-header span {
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--muted);
    letter-spacing: 0.15em;
    text-transform: uppercase;
}

/* Upload zone */
.upload-zone {
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: 12px;
    padding: 1.6rem 1.4rem;
    margin-bottom: 1rem;
    transition: border-color 0.2s;
}
.upload-label {
    font-family: var(--mono);
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 6px;
}

/* Metric cards */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 12px;
    margin: 1.5rem 0;
}
.metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
}
.metric-label {
    font-family: var(--mono);
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 4px;
}
.metric-value {
    font-family: var(--mono);
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--accent);
    line-height: 1;
}
.metric-sub {
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--muted);
    margin-top: 2px;
}

/* Shot table */
.shot-table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    margin: 1rem 0;
}
.shot-table-wrap table {
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 0.8rem;
}
.shot-table-wrap th {
    background: var(--bg);
    color: var(--muted);
    font-size: 0.65rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}
.shot-table-wrap td {
    padding: 9px 14px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
}
.shot-table-wrap tr:last-child td { border-bottom: none; }
.shot-table-wrap tr:hover td { background: rgba(232,255,71,0.03); }

/* Rating dots */
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
.dot-green { background: var(--green); }
.dot-amber { background: var(--amber); }
.dot-red   { background: var(--red);   }

/* Issue tags */
.tag {
    display: inline-block;
    background: rgba(232,255,71,0.08);
    border: 1px solid rgba(232,255,71,0.2);
    color: var(--accent);
    font-family: var(--mono);
    font-size: 0.65rem;
    letter-spacing: 0.08em;
    padding: 3px 10px;
    border-radius: 20px;
    margin: 3px 4px 3px 0;
}

/* Drill cards */
.drill-card {
    background: var(--surface);
    border-left: 3px solid var(--accent2);
    border-radius: 0 8px 8px 0;
    padding: 0.9rem 1.1rem;
    margin-bottom: 8px;
    font-size: 0.85rem;
}

/* Progress bar override */
.stProgress > div > div > div > div {
    background: var(--accent) !important;
}

/* Button */
.stButton > button {
    background: var(--accent) !important;
    color: #0b0d11 !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: var(--mono) !important;
    font-size: 0.8rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.1em !important;
    padding: 0.55rem 1.8rem !important;
    width: 100% !important;
}
.stButton > button:hover {
    background: #d4eb3a !important;
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: var(--surface) !important;
    border: 1px dashed var(--border) !important;
    border-radius: 10px !important;
}

/* Sidebar */
[data-testid="stSidebar"] { background: var(--surface) !important; }

/* Section headings */
.section-heading {
    font-family: var(--mono);
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    margin: 2rem 0 0.8rem;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
}

/* Score sparkline colours */
.score-high { color: var(--green); font-weight: 700; }
.score-mid  { color: var(--amber); font-weight: 700; }
.score-low  { color: var(--red);   font-weight: 700; }

/* Status badge */
.status-badge {
    display: inline-block;
    font-family: var(--mono);
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 3px 12px;
    border-radius: 20px;
    margin-left: 10px;
}
.status-running { background: rgba(251,191,36,0.15); color: var(--amber); border: 1px solid rgba(251,191,36,0.35); }
.status-done    { background: rgba(74,222,128,0.12); color: var(--green); border: 1px solid rgba(74,222,128,0.30); }
.status-error   { background: rgba(248,113,113,0.12); color: var(--red);   border: 1px solid rgba(248,113,113,0.30); }

/* Hide default Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)


def _serialise_analysis(analysis, shot_metrics):
    shots = analysis["scored_shots"]
    diagnoses = analysis["diagnoses"]
    shot_rows = []
    for s in shots:
        d = diagnoses.get(s["id"], {})
        shot_rows.append({
            "id":        s["id"],
            "score":     s.get("score"),
            "DA":        s.get("DA"),
            "S1":        s.get("S1"),
            "S2":        s.get("S2"),
            "hold_10":   s.get("hold_10"),
            "hold_10a":  s.get("hold_10a"),
            "aim_sec":   s.get("aiming_sec"),
            "interval":  s.get("interval"),
            "direction": s.get("direction"),
            "rating":    d.get("rating", "green"),
            "archetype": d.get("archetype", ""),
            "summary":   d.get("summary", ""),
        })
    session = analysis["session"]
    return {
        "shooter":       session["shooter"].title(),
        "distance":      session["distance_m"],
        "shot_count":    len(shots),
        "mean_score":    analysis["mean_score"],
        "stdev_score":   analysis["stdev_score"],
        "total_score":   analysis["total_score"],
        "mean_DA":       analysis["mean_DA"],
        "mean_S2":       analysis["mean_S2"],
        "mean_S1":       analysis["mean_S1"],
        "mean_aim":      analysis["mean_aim_time"],
        "fatigue":       analysis["fatigue_delta"],
        "green_count":   len(analysis["green_shots"]),
        "amber_count":   len(analysis["amber_shots"]),
        "red_count":     len(analysis["red_shots"]),
        "top_issues":    analysis["top_issues"],
        "drills":        analysis["drills"],
        "shots":         shot_rows,
        "scores_series": [s.get("score") for s in shots],
    }


def run_analysis(db_bytes, img_bytes_list, img_names, status_container):
    """Run the full pipeline; updates st.session_state.result."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Save DB
        db_path = tmpdir / "session.scatt-expert"
        db_path.write_bytes(db_bytes)

        # Save screenshots
        img_paths = []
        for i, (data, name) in enumerate(zip(img_bytes_list, img_names)):
            ext = Path(name).suffix or ".png"
            p = tmpdir / f"screenshot_{i:02d}{ext}"
            p.write_bytes(data)
            img_paths.append(str(p))

        # Progress state
        prog_bar  = status_container.progress(0)
        prog_text = status_container.empty()

        def progress_cb(done, total, path):
            pct = int(done / total * 60) + 10
            prog_bar.progress(min(pct, 70))
            prog_text.markdown(
                f'<p style="font-family:\'JetBrains Mono\',monospace;font-size:0.75rem;color:#64748b;">'
                f'OCR · {done}/{total} screenshot(s)</p>',
                unsafe_allow_html=True,
            )

        try:
            prog_text.markdown(
                '<p style="font-family:\'JetBrains Mono\',monospace;font-size:0.75rem;color:#64748b;">'
                'Loading session database…</p>',
                unsafe_allow_html=True,
            )
            prog_bar.progress(5)
            session = load_session(str(db_path))

            prog_bar.progress(10)
            shot_metrics = ocr_extract(img_paths, progress_cb=progress_cb)

            prog_bar.progress(70)
            prog_text.markdown(
                f'<p style="font-family:\'JetBrains Mono\',monospace;font-size:0.75rem;color:#64748b;">'
                f'Extracted {len(shot_metrics)} shots — analysing…</p>',
                unsafe_allow_html=True,
            )
            inject_screenshot_data(session, shot_metrics)
            analysis = analyse_session(session)

            prog_bar.progress(85)
            prog_text.markdown(
                '<p style="font-family:\'JetBrains Mono\',monospace;font-size:0.75rem;color:#64748b;">'
                'Building PDF report…</p>',
                unsafe_allow_html=True,
            )
            shooter   = session["shooter"].replace(" ", "_")
            out_name  = f"SCATT_Report_{shooter}.pdf"
            out_path  = REPORT_DIR / out_name
            build_report(analysis, str(out_path))

            prog_bar.progress(100)
            prog_text.empty()

            st.session_state.result     = _serialise_analysis(analysis, shot_metrics)
            st.session_state.report_path = str(out_path)
            st.session_state.status     = "done"

        except Exception as e:
            st.session_state.status = "error"
            st.session_state.error  = traceback.format_exc()


BENCH = {
    "score_elite":    10.5,
    "score_good":     10.3,
    "DA_elite":        1.0,
    "DA_good":         2.0,
    "S2_elite":       10.0,
    "S2_good":        14.0,
    "S1_elite":       12.0,
    "hold_pct_elite": 98,
    "hold_pct_good":  90,
    "aiming_min":      7.0,
    "aiming_max":     14.0,
    "aiming_sweet":   10.0,
    "interval_min":   40.0,
    "interval_max":   90.0,
}


def _bench_rating(metric, value):
    if value is None:
        return "muted"
    if metric == "score":
        return "green" if value >= BENCH["score_elite"] else ("amber" if value >= BENCH["score_good"] else "red")
    if metric == "DA":
        return "green" if value <= BENCH["DA_elite"] else ("amber" if value <= BENCH["DA_good"] else "red")
    if metric == "S2":
        return "green" if value <= BENCH["S2_elite"] else ("amber" if value <= BENCH["S2_good"] else "red")
    if metric == "aim":
        return "green" if BENCH["aiming_min"] <= value <= BENCH["aiming_max"] else "amber"
    if metric == "fatigue":
        return "green" if value >= 0 else ("amber" if value >= -0.05 else "red")
    return "muted"


def _render_scorecard(r):
    COLOR = {"green": "#4ade80", "amber": "#fbbf24", "red": "#f87171", "muted": "#64748b"}

    mean_sc  = r.get("mean_score")
    tot_sc   = r.get("total_score")
    n_sc     = r.get("shot_count", 0)
    mean_DA  = r.get("mean_DA")
    mean_S2  = r.get("mean_S2")
    mean_aim = r.get("mean_aim")
    fat_d    = r.get("fatigue")

    def pill(rating):
        c = COLOR[rating]
        lbl = rating.upper()
        return (
            f'<span style="display:inline-block;padding:2px 10px;border-radius:20px;'
            f'border:1px solid {c}33;background:{c}18;color:{c};'
            f'font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;font-weight:700;'
            f'letter-spacing:0.08em;">{lbl}</span>'
        )

    rows = [
        ("Mean Score",     f"{mean_sc:.3f}"   if mean_sc  else "—", "≥ 10.5 elite",              pill(_bench_rating("score",   mean_sc))),
        ("Total Score",    f"{tot_sc:.1f}"    if tot_sc   else "—", f"/{n_sc*10.9:.0f} theoretical", ""),
        ("Mean DA (mm)",   f"{mean_DA:.2f}"   if mean_DA  else "—", "< 1.0 elite",                pill(_bench_rating("DA",      mean_DA))),
        ("Mean S2 (mm/s)", f"{mean_S2:.1f}"   if mean_S2  else "—", "< 10 elite",                 pill(_bench_rating("S2",      mean_S2))),
        ("Mean Aim Time",  f"{mean_aim:.1f}s" if mean_aim else "—", "7–14 s ideal",               pill(_bench_rating("aim",     mean_aim))),
        ("Fatigue Trend",  (f"{fat_d:+.3f}"   if fat_d    else "0"), "≥ 0 ideal",                 pill(_bench_rating("fatigue", fat_d))),
    ]

    rows_html = ""
    for i, (metric, value, bench, status) in enumerate(rows):
        bg = "background:#0b0d1180;" if i % 2 == 0 else ""
        rows_html += f"""
        <tr style="{bg}">
            <td style="color:#94a3b8;font-size:0.75rem;padding:10px 14px;white-space:nowrap;">{metric}</td>
            <td style="color:#e2e8f0;font-size:0.85rem;font-weight:700;padding:10px 14px;font-family:'JetBrains Mono',monospace;">{value}</td>
            <td style="color:#64748b;font-size:0.7rem;padding:10px 14px;">{bench}</td>
            <td style="padding:10px 14px;text-align:right;">{status}</td>
        </tr>"""

    return f"""
    <div style="background:#13161d;border:1px solid #1e2330;border-radius:10px;overflow:hidden;margin:0.5rem 0 1.5rem;">
        <table style="width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace;">
            <thead>
                <tr style="background:#0b0d11;border-bottom:1px solid #1e2330;">
                    <th style="color:#64748b;font-size:0.62rem;letter-spacing:0.1em;text-transform:uppercase;padding:10px 14px;text-align:left;">METRIC</th>
                    <th style="color:#64748b;font-size:0.62rem;letter-spacing:0.1em;text-transform:uppercase;padding:10px 14px;text-align:left;">VALUE</th>
                    <th style="color:#64748b;font-size:0.62rem;letter-spacing:0.1em;text-transform:uppercase;padding:10px 14px;text-align:left;">BENCHMARK</th>
                    <th style="color:#64748b;font-size:0.62rem;letter-spacing:0.1em;text-transform:uppercase;padding:10px 14px;text-align:right;">STATUS</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>"""


def score_color_class(score):
    if score is None:
        return ""
    if score >= 9.5:
        return "score-high"
    if score >= 9.0:
        return "score-mid"
    return "score-low"


def fmt(val, decimals=2):
    if val is None:
        return "—"
    return f"{val:.{decimals}f}"


# ── Session state init ─────────────────────────────────────────────────────────
for key, default in [
    ("result", None),
    ("report_path", None),
    ("status", "idle"),
    ("error", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(180deg,#13161d 0%,#0b0d11 100%);
border:1px solid #1e2330;border-radius:14px;
padding:1.8rem 1.8rem 1.6rem;margin-bottom:2rem;">

<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;">

<div style="display:flex;flex-direction:column;gap:6px;">

<div style="display:flex;align-items:center;gap:14px;">
<h1 style="font-size:2.4rem;font-weight:800;color:#e8ff47;margin:0;letter-spacing:-0.02em;">
🎯 SCATT Analyser
</h1>

<span style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.18em;">
Performance Intelligence
</span>
</div>

<div style="display:flex;align-items:center;gap:10px;margin-top:4px;">
<span style="font-size:0.65rem;color:#64748b;text-transform:uppercase;">Built by</span>
<span style="font-size:1.05rem;font-weight:700;color:#e2e8f0;">Ashmit Chatterjee</span>
<span style="font-size:0.65rem;color:#64748b;">· SCATT Shooting Performance Analyser</span>
</div>

</div>

<div style="display:flex;flex-direction:column;align-items:flex-end;gap:10px;">

<span style="display:inline-flex;align-items:center;gap:6px;
background:rgba(251,191,36,0.12);border:1px solid rgba(251,191,36,0.35);
color:#fbbf24;font-size:0.65rem;font-weight:700;
padding:6px 14px;border-radius:999px;">
<span style="width:6px;height:6px;border-radius:50%;background:#fbbf24;"></span>
Work in Progress
</span>

<div style="display:flex;gap:16px;font-family:'JetBrains Mono',monospace;font-size:0.7rem;color:#64748b;">
<span>Upload → Analyse → Improve</span>
</div>

</div>

</div>

</div>
""", unsafe_allow_html=True)


# ── Upload Panel ───────────────────────────────────────────────────────────────
with st.container():
    col_db, col_imgs = st.columns([1, 2], gap="large")

    with col_db:
        st.markdown('<div class="upload-label">Session File</div>', unsafe_allow_html=True)
        db_file = st.file_uploader(
            "Upload session file",
            type=None
        )
        if db_file:
            st.markdown(
                f'<p style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;color:#4ade80;">✓ {db_file.name}</p>',
                unsafe_allow_html=True,
            )

    with col_imgs:
        st.markdown('<div class="upload-label">Screenshots</div>', unsafe_allow_html=True)
        img_files = st.file_uploader(
            "SCATT screenshots",
            type=["png", "jpg", "jpeg", "bmp", "tiff"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if img_files:
            st.markdown(
                f'<p style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;color:#4ade80;">✓ {len(img_files)} file(s) selected</p>',
                unsafe_allow_html=True,
            )

# ── Run Button ─────────────────────────────────────────────────────────────────
_, btn_col, _ = st.columns([2, 1, 2])
with btn_col:
    run = st.button("▶  ANALYSE SESSION", disabled=(not db_file or not img_files))

if run and db_file and img_files:
    st.session_state.result      = None
    st.session_state.report_path = None
    st.session_state.status      = "running"
    st.session_state.error       = None

    status_box = st.empty()
    with status_box.container():
        run_analysis(
            db_bytes        = db_file.read(),
            img_bytes_list  = [f.read() for f in img_files],
            img_names       = [f.name for f in img_files],
            status_container= st,
        )
    status_box.empty()
    st.rerun()

# ── Error ──────────────────────────────────────────────────────────────────────
if st.session_state.status == "error":
    st.error("Analysis failed.")
    with st.expander("Traceback"):
        st.code(st.session_state.error, language="python")

# ── Results ────────────────────────────────────────────────────────────────────
if st.session_state.status == "done" and st.session_state.result:
    r = st.session_state.result

    # ── Shooter banner ────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;
                padding:1.2rem 1.6rem;margin:1.5rem 0;display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap;">
        <div>
            <div style="font-family:var(--mono);font-size:0.65rem;letter-spacing:0.14em;
                        text-transform:uppercase;color:var(--muted);">Shooter</div>
            <div style="font-family:'Space Grotesk',sans-serif;font-size:1.5rem;font-weight:800;
                        color:var(--text);">{r['shooter']}</div>
        </div>
        <div style="width:1px;height:40px;background:var(--border);"></div>
        <div>
            <div style="font-family:var(--mono);font-size:0.65rem;letter-spacing:0.14em;
                        text-transform:uppercase;color:var(--muted);">Distance</div>
            <div style="font-family:var(--mono);font-size:1.4rem;font-weight:700;
                        color:var(--accent);">{r['distance']} m</div>
        </div>
        <div style="width:1px;height:40px;background:var(--border);"></div>
        <div>
            <div style="font-family:var(--mono);font-size:0.65rem;letter-spacing:0.14em;
                        text-transform:uppercase;color:var(--muted);">Shots</div>
            <div style="font-family:var(--mono);font-size:1.4rem;font-weight:700;
                        color:var(--text);">{r['shot_count']}</div>
        </div>
        <div style="margin-left:auto;">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#4ade80;margin-right:4px;"></span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;">{r['green_count']}</span>&nbsp;&nbsp;
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#fbbf24;margin-right:4px;"></span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;">{r['amber_count']}</span>&nbsp;&nbsp;
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f87171;margin-right:4px;"></span>
            <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;">{r['red_count']}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_overview, tab_shots, tab_drills, tab_export = st.tabs([
        "📊  Overview", "🎯  Shot Log", "🏋️  Drills", "⬇  Export"
    ])

    # ════════════════════════════ OVERVIEW TAB ════════════════════════════════
    with tab_overview:
        # Key metrics
        st.markdown('<div class="section-heading">Key Metrics</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Total Score</div>
                <div class="metric-value">{fmt(r['total_score'], 1)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Mean Score</div>
                <div class="metric-value">{fmt(r['mean_score'])}</div>
                <div class="metric-sub">σ {fmt(r['stdev_score'])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Mean DA</div>
                <div class="metric-value">{fmt(r['mean_DA'])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Mean S1</div>
                <div class="metric-value">{fmt(r['mean_S1'])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Mean S2</div>
                <div class="metric-value">{fmt(r['mean_S2'])}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Mean Aim</div>
                <div class="metric-value">{fmt(r['mean_aim'])}</div>
                <div class="metric-sub">seconds</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Fatigue Δ</div>
                <div class="metric-value" style="color:{'#f87171' if (r['fatigue'] or 0) < 0 else '#4ade80'};">
                    {fmt(r['fatigue'])}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Score series chart
        scores = [s for s in r["scores_series"] if s is not None]
        if scores:
            st.markdown('<div class="section-heading">Score Series</div>', unsafe_allow_html=True)
            import pandas as pd
            import altair as alt

            df = pd.DataFrame({
                "Shot": list(range(1, len(scores)+1)),
                "Score": scores
            })

            y_min = max(min(scores) - 0.15, 9.5)
            y_max = max(scores) + 0.15

            chart = alt.Chart(df).mark_line(point=True).encode(
                x=alt.X("Shot:Q", title="Shot"),
                y=alt.Y("Score:Q", scale=alt.Scale(domain=[y_min, y_max])),
                tooltip=["Shot", "Score"]
            ).properties(
                height=220
            )

            st.altair_chart(chart, use_container_width=True)

        # Top issues
        if r.get("top_issues"):
            st.markdown('<div class="section-heading">Top Issues</div>', unsafe_allow_html=True)
            tags = "".join(
                f'<span style="display:inline-block;background:rgba(232,255,71,0.08);border:1px solid rgba(232,255,71,0.2);'
                f'color:#e8ff47;font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;letter-spacing:0.08em;'
                f'padding:3px 10px;border-radius:20px;margin:3px 4px 3px 0;">{issue}</span>'
                for issue in r["top_issues"]
            )
            st.markdown(f'<div style="margin-bottom:1rem;">{tags}</div>', unsafe_allow_html=True)

        # Benchmark scorecard
        st.markdown('<div class="section-heading">Benchmark Scorecard</div>', unsafe_allow_html=True)
        st.markdown(_render_scorecard(r), unsafe_allow_html=True)

    # ════════════════════════════ SHOT LOG TAB ════════════════════════════════
    with tab_shots:
        # Build full self-contained HTML for the table so CSS works reliably
        def rating_dot(rating):
            colors = {"green": "#4ade80", "amber": "#fbbf24", "red": "#f87171"}
            c = colors.get(rating, "#64748b")
            return f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{c};margin-right:6px;vertical-align:middle;"></span>'

        def score_color(score):
            if score is None:
                return "#e2e8f0"
            if score >= 9.5:
                return "#4ade80"
            if score >= 9.0:
                return "#fbbf24"
            return "#f87171"

        rows_html = ""
        for s in r["shots"]:
            sc = s.get("score")
            rows_html += f"""
            <tr>
                <td style="font-weight:600;color:#e2e8f0;">#{s['id']}</td>
                <td style="font-weight:700;color:{score_color(sc)};">{fmt(sc)}</td>
                <td>{fmt(s['DA'])}</td>
                <td>{fmt(s['S1'])}</td>
                <td>{fmt(s['S2'])}</td>
                <td>{fmt(s['hold_10'])}</td>
                <td>{fmt(s['aim_sec'])}</td>
                <td>{rating_dot(s['rating'])}{s.get('archetype') or '—'}</td>
                <td style="color:#64748b;font-size:0.72rem;">{s.get('summary') or ''}</td>
            </tr>
            """

        table_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ background: transparent; font-family: 'JetBrains Mono', monospace; }}
            .wrap {{
                background: #13161d;
                border: 1px solid #1e2330;
                border-radius: 10px;
                overflow: hidden;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.8rem;
            }}
            th {{
                background: #0b0d11;
                color: #64748b;
                font-size: 0.62rem;
                letter-spacing: 0.1em;
                text-transform: uppercase;
                padding: 10px 14px;
                text-align: left;
                border-bottom: 1px solid #1e2330;
                white-space: nowrap;
            }}
            td {{
                padding: 9px 14px;
                border-bottom: 1px solid #1e2330;
                color: #e2e8f0;
                white-space: nowrap;
            }}
            tr:last-child td {{ border-bottom: none; }}
            tr:hover td {{ background: rgba(232,255,71,0.03); }}
        </style>
        </head>
        <body>
        <div class="wrap">
            <table>
                <thead>
                    <tr>
                        <th>Shot</th><th>Score</th><th>DA</th><th>S1</th><th>S2</th>
                        <th>Hold10</th><th>Aim(s)</th><th>Rating</th><th>Summary</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
        </body>
        </html>
        """

        row_count = len(r["shots"])
        table_height = min(80 + row_count * 40, 600)  # cap at 600px, scrollable inside
        components.html(table_html, height=table_height, scrolling=True)

    # ════════════════════════════ DRILLS TAB ══════════════════════════════════
    with tab_drills:
        drills = r.get("drills", [])
        if drills:
            for drill in drills:
                st.markdown(f"""
                <div style="background:#13161d;border-left:3px solid #47ffe8;border-radius:0 8px 8px 0;
                            padding:0.9rem 1.1rem;margin-bottom:10px;font-size:0.85rem;color:#e2e8f0;">
                    <div style="font-weight:700;margin-bottom:4px;color:#e2e8f0;">{drill.get("name","")}</div>
                    <div style="margin-bottom:6px;">{drill.get("desc","")}</div>
                    <div style="opacity:0.6;font-size:0.75rem;font-family:'JetBrains Mono',monospace;">
                        {drill.get("duration","")}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown(
                '<p style="color:#64748b;font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;">'
                'No drill prescriptions generated for this session.</p>',
                unsafe_allow_html=True,
            )

    # ════════════════════════════ EXPORT TAB ══════════════════════════════════
    with tab_export:
        if st.session_state.report_path and Path(st.session_state.report_path).exists():
            with open(st.session_state.report_path, "rb") as f:
                pdf_bytes = f.read()
            st.markdown(
                '<p style="color:#64748b;font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;margin-bottom:1rem;">'
                'Your session PDF report is ready to download.</p>',
                unsafe_allow_html=True,
            )
            dl_col, _ = st.columns([1, 3])
            with dl_col:
                st.download_button(
                    label="⬇  Download PDF Report",
                    data=pdf_bytes,
                    file_name=Path(st.session_state.report_path).name,
                    mime="application/pdf",
                )
        else:
            st.markdown(
                '<p style="color:#64748b;font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;">'
                'PDF report not available.</p>',
                unsafe_allow_html=True,
            )

# ── Idle hint ──────────────────────────────────────────────────────────────────
if st.session_state.status == "idle":
    st.markdown("""
    <div style="text-align:center;padding:4rem 0 2rem;opacity:0.35;">
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.75rem;
                    letter-spacing:0.2em;text-transform:uppercase;color:#64748b;">
            Upload a .scatt-expert file + screenshots to begin
        </div>
    </div>
    """, unsafe_allow_html=True)
