# 🎯 SCATT Performance Analyser

> **Shooting session intelligence — upload, analyse, improve.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-scattanalyser--ashmit.streamlit.app-e8ff47?style=for-the-badge&logo=streamlit&logoColor=black)](https://scattanalyser-ashmit.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3.10-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.56-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)

---

## What It Does

The SCATT Analyser is a web dashboard that turns raw `.scatt-expert` session files and table screenshots into actionable performance intelligence for competitive shooters.

Upload your session file and one or more SCATT Expert table screenshots — the app extracts every shot's metrics via OCR, cross-references them with the session database, and delivers a full diagnostic report with per-shot ratings, issue tagging, drill prescriptions, and a downloadable PDF.

---

## Pipeline

```
.scatt-expert (SQLite)  +  Screenshot(s)
         │                       │
         ▼                       ▼
   Session loader           Tesseract OCR
   (zlib blob decode)    (4x upscale + sharpen)
         │                       │
         └──────────┬────────────┘
                    ▼
           Shot merging & deduplication
           (ID-reliable merge across multiple screenshots)
                    ▼
           Performance analysis engine
           (fatigue delta, DA/S1/S2 diagnostics,
            archetype classification, drill prescription)
                    ▼
         Streamlit Dashboard  +  PDF Report
```

---

## Features

- **Multi-screenshot OCR** — handles sessions >35 shots split across multiple screenshots; shot IDs deduplicated automatically
- **Shot diagnostics** — each shot rated green / amber / red with archetype label (e.g. "Late trigger", "Unstable hold") and plain-English summary
- **Session metrics** — mean score, σ, mean DA/S1/S2, aiming time, fatigue delta (first half vs second half score trend)
- **Benchmark scorecard** — compares your session against elite and good performance thresholds
- **Drill prescriptions** — auto-generated training recommendations based on top issues detected
- **PDF export** — full session report downloadable from the Export tab
- **Dark UI** — JetBrains Mono + Syne, neon yellow accent, zero Streamlit chrome

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit, Altair, custom HTML/CSS components |
| OCR | Tesseract 5.5 via pytesseract, OpenCV (4x upscale + sharpening kernel) |
| Session parsing | SQLite3 + zlib blob decompression |
| PDF generation | ReportLab |
| Deployment | Streamlit Cloud |

---

## Local Setup

```bash
# 1. Install Tesseract (Windows)
# https://github.com/UB-Mannheim/tesseract/wiki
# Check "Add to PATH" during install

# 2. Clone and install
git clone https://github.com/ash-myth/scatt_analyser.git
cd scatt_analyser
pip install -r requirements.txt

# 3. Run
streamlit run streamlit_app.py
```

---

## Usage

1. Upload your `.scatt-expert` session file
2. Upload one or more SCATT Expert table screenshots
   - If session > 35 shots, scroll the table and screenshot each page
3. Click **Analyse Session**
4. Explore Overview → Shot Log → Drills → Export tabs
5. Download PDF report

---

## Project Structure

```
scatt_analyser/
├── streamlit_app.py      # UI layer — tabs, upload, progress, charts
├── scatt_analyser.py     # Analysis engine — session parsing, diagnostics, PDF
├── scatt_ocr.py          # OCR pipeline — multi-image extraction, deduplication
├── requirements.txt
└── packages.txt          # System deps for Streamlit Cloud (tesseract-ocr)
```

---

## Screenshots

![SCATT Analyser Dashboard](https://scattanalyser-ashmit.streamlit.app/)

---

Built by [Ashmit Chatterjee](https://github.com/ash-myth)
