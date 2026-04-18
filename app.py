"""
app.py — SCATT Performance Analyser Web Dashboard
Run: python app.py
Open: http://localhost:5000
"""

import os
import sys
import json
import uuid
import threading
import traceback
from pathlib import Path
from flask import (
    Flask, request, jsonify, send_file,
    render_template, Response, stream_with_context
)

# Make sure local modules are importable
sys.path.insert(0, os.path.dirname(__file__))
from scatt_ocr import extract as ocr_extract
from scatt_analyser import load_session, inject_screenshot_data, analyse_session, build_report

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB

UPLOAD_DIR = Path("uploads")
REPORT_DIR = Path("reports")
UPLOAD_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

# In-memory job store
jobs = {}  # job_id → {status, progress, message, result, error}


def run_job(job_id, db_path, img_paths):
    """Run OCR + analysis in background thread, update jobs dict."""
    job = jobs[job_id]
    try:
        total_imgs = len(img_paths)

        def progress_cb(done, total, path):
            job["progress"] = int(done / total * 60)  # OCR = 0-60%
            job["message"] = f"OCR: processed {done}/{total} screenshot(s)…"

        job["status"] = "running"
        job["message"] = "Loading session database…"
        job["progress"] = 5

        session = load_session(str(db_path))

        job["message"] = f"Running OCR on {total_imgs} screenshot(s)…"
        job["progress"] = 10

        shot_metrics = ocr_extract(img_paths, progress_cb=progress_cb)

        job["progress"] = 65
        job["message"] = f"Extracted {len(shot_metrics)} shots. Analysing…"

        inject_screenshot_data(session, shot_metrics)
        analysis = analyse_session(session)

        job["progress"] = 80
        job["message"] = "Building PDF report…"

        shooter = session["shooter"].replace(" ", "_")
        out_name = f"SCATT_Report_{shooter}_{job_id[:8]}.pdf"
        out_path = REPORT_DIR / out_name
        build_report(analysis, str(out_path))

        job["progress"] = 100
        job["status"] = "done"
        job["message"] = "Report ready."
        job["report_file"] = out_name
        job["result"] = _serialise_analysis(analysis, shot_metrics)

    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)
        job["error"] = traceback.format_exc()


def _serialise_analysis(analysis, shot_metrics):
    """Convert analysis to JSON-safe dict for the dashboard."""
    shots = analysis["scored_shots"]
    diagnoses = analysis["diagnoses"]

    shot_rows = []
    for s in shots:
        d = diagnoses.get(s["id"], {})
        shot_rows.append({
            "id":       s["id"],
            "score":    s.get("score"),
            "DA":       s.get("DA"),
            "S1":       s.get("S1"),
            "S2":       s.get("S2"),
            "hold_10":  s.get("hold_10"),
            "hold_10a": s.get("hold_10a"),
            "aim_sec":  s.get("aiming_sec"),
            "interval": s.get("interval"),
            "direction":s.get("direction"),
            "rating":   d.get("rating", "green"),
            "archetype":d.get("archetype", ""),
            "summary":  d.get("summary", ""),
        })

    session = analysis["session"]
    return {
        "shooter":      session["shooter"].title(),
        "distance":     session["distance_m"],
        "shot_count":   len(shots),
        "mean_score":   analysis["mean_score"],
        "stdev_score":  analysis["stdev_score"],
        "total_score":  analysis["total_score"],
        "mean_DA":      analysis["mean_DA"],
        "mean_S2":      analysis["mean_S2"],
        "mean_S1":      analysis["mean_S1"],
        "mean_aim":     analysis["mean_aim_time"],
        "fatigue":      analysis["fatigue_delta"],
        "green_count":  len(analysis["green_shots"]),
        "amber_count":  len(analysis["amber_shots"]),
        "red_count":    len(analysis["red_shots"]),
        "top_issues":   analysis["top_issues"],
        "drills":       analysis["drills"],
        "shots":        shot_rows,
        "scores_series": [s.get("score") for s in shots],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyse", methods=["POST"])
def analyse():
    """Upload files and start analysis job."""
    db_file = request.files.get("db")
    img_files = request.files.getlist("screenshots")

    if not db_file:
        return jsonify({"error": "No .scatt-expert file uploaded"}), 400
    if not img_files or all(f.filename == "" for f in img_files):
        return jsonify({"error": "No screenshot(s) uploaded"}), 400

    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir()

    # Save DB
    db_path = job_dir / "session.scatt-expert"
    db_file.save(str(db_path))

    # Save screenshots
    img_paths = []
    for i, f in enumerate(img_files):
        if f.filename:
            ext = Path(f.filename).suffix or ".png"
            p = job_dir / f"screenshot_{i:02d}{ext}"
            f.save(str(p))
            img_paths.append(str(p))

    if not img_paths:
        return jsonify({"error": "No valid screenshots uploaded"}), 400

    jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "message": "Queued…",
        "report_file": None,
        "result": None,
        "error": None,
    }

    t = threading.Thread(target=run_job, args=(job_id, db_path, img_paths), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<job_id>")
def download(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Report not ready"}), 404
    path = REPORT_DIR / job["report_file"]
    return send_file(str(path), as_attachment=True, download_name=job["report_file"])


if __name__ == "__main__":
    print("\n  SCATT Performance Analyser")
    print("  Open → http://localhost:5000\n")
    app.run(debug=False, port=5000, threaded=True)
