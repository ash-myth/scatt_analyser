SCATT Performance Analyser — Web Dashboard v2
=============================================

SETUP
-----
1. Install Tesseract OCR (Windows):
   https://github.com/UB-Mannheim/tesseract/wiki
   Check "Add to PATH" during install.

2. Install Python packages:
   pip install -r requirements.txt

RUN
---
   python app.py
   Open: http://localhost:5000

USAGE
-----
1. Drop your .scatt-expert file (click ✕ to clear if wrong file)
2. Drop one or more SCATT Expert table screenshots
   - If session > 35 shots: scroll the SCATT table, screenshot each page
   - Shot IDs are read automatically, no duplicates
3. Click Analyse Session
4. Download the PDF report when done

CHANGES v2
----------
- Aiming time (T column) now correctly read from screenshot, not DB
- Multi-screenshot shot ID deduplication improved
- Score chart fixed (was empty due to layout timing)
- Readable DM Sans font for body text
- Clear (✕) button on both upload zones — no page refresh needed
