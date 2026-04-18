"""
scatt_ocr.py  —  Robust OCR for SCATT Expert screenshot tables
================================================================
Supports multiple screenshots from the same session.
Shot IDs are read from the # column and used to merge/deduplicate.
Falls back to sequential numbering if IDs are unreadable.
Hard cap: 100 shots total across all screenshots.
"""

import re
import os
import sys
import cv2
import numpy as np
import pytesseract
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_SHOTS = 100

COLS = [
    ("id",       0.00, 0.07),
    ("D",        0.07, 0.15),
    ("R",        0.15, 0.27),
    ("T",        0.27, 0.38),
    ("hold_10",  0.38, 0.50),
    ("hold_10a", 0.50, 0.62),
    ("S1",       0.62, 0.74),
    ("S2",       0.74, 0.87),
    ("DA",       0.87, 0.96),
    ("_star",    0.96, 1.00),
]

DIRECTION_MAP = {
    "->": "→", ">": "→", "=>": "→",
    "<-": "←", "<": "←",
    "^": "↑", "A": "↑",
    "v": "↓", "V": "↓",
    "→": "→", "←": "←", "↑": "↑", "↓": "↓",
    "↗": "↗", "↘": "↘", "↙": "↙", "↖": "↖",
    "↺": "↺",
}

HEADER_KEYWORDS = {"r", "t", "da", "s1", "s2", "10.0", "10a0", "#", "d", "si"}


def _col_for(cx_frac):
    for name, lo, hi in COLS:
        if lo <= cx_frac < hi:
            return name
    return None


def _parse_pct(s):
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def _parse_float(s, max_val=None):
    s = s.strip().replace(",", ".")
    m = re.search(r"(\d+\.?\d*)", s)
    if not m:
        return None
    v = float(m.group(1))
    if v == int(v) and v > 200:
        v = v / 100.0
    if max_val is not None and v > max_val:
        v = v / 10.0
    return v


def _normalise_direction(s):
    s = s.strip()
    return DIRECTION_MAP.get(s, s if s else "?")


def _parse_id(s):
    if not s:
        return None
    m = re.search(r"^(\d+)$", s.strip())
    if m:
        v = int(m.group(1))
        if 1 <= v <= MAX_SHOTS:
            return v
    return None


def extract_single(image_path, min_conf=30):
    """Extract shots from a single screenshot."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {image_path}")

    img4x = cv2.resize(img, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    H, W = img4x.shape[:2]

    kernel = np.array([[0, -0.5, 0], [-0.5, 3, -0.5], [0, -0.5, 0]])
    img4x = cv2.filter2D(img4x, -1, kernel)
    img4x = np.clip(img4x, 0, 255).astype(np.uint8)

    cfg = "--psm 11 --oem 3"
    data = pytesseract.image_to_data(
        img4x, output_type=pytesseract.Output.DICT, config=cfg
    )

    ROW_BUCKET = 18
    row_map = {}

    for i, txt in enumerate(data["text"]):
        txt = txt.strip()
        if not txt:
            continue
        conf = data["conf"][i]
        if conf < min_conf:
            continue
        x = data["left"][i]
        w = data["width"][i]
        y = data["top"][i]
        cx = (x + w / 2) / W
        col = _col_for(cx)
        if col is None or col == "_star":
            continue
        y_bucket = round(y / ROW_BUCKET) * ROW_BUCKET
        row_map.setdefault(y_bucket, {}).setdefault(col, []).append((txt, conf))

    sorted_ys = sorted(row_map.keys())
    if not sorted_ys:
        return []

    first_row = row_map[sorted_ys[0]]
    first_texts = {v[0][0].lower() for v in first_row.values() if v}
    if first_texts & HEADER_KEYWORDS:
        sorted_ys = sorted_ys[1:]

    shots = []
    seq = 1

    for y_bucket in sorted_ys:
        row = row_map[y_bucket]

        def best(col, _row=row):
            tokens = _row.get(col, [])
            if not tokens:
                return None
            return max(tokens, key=lambda t: t[1])[0]

        r_txt = best("R")
        if r_txt is None:
            continue
        score = _parse_float(r_txt)
        if score is None or not (7.0 <= score <= 10.9):
            continue

        id_txt = best("id")
        ocr_id = _parse_id(id_txt)
        h10    = best("hold_10")
        h10a   = best("hold_10a")
        s1_txt = best("S1")
        s2_txt = best("S2")
        da_txt = best("DA")
        d_txt  = best("D")
        t_txt  = best("T")

        t_txt = best("T")
        aiming = _parse_float(t_txt, max_val=60.0) if t_txt else None

        shot = {
            "id":          ocr_id if ocr_id is not None else seq,
            "id_reliable": ocr_id is not None,
            "score":       score,
            "direction":   _normalise_direction(d_txt) if d_txt else "?",
            "aiming_sec":  aiming,
            "hold_10":     _parse_pct(h10)  if h10  else None,
            "hold_10a":    _parse_pct(h10a) if h10a else None,
            "S1":          _parse_float(s1_txt, max_val=30.0) if s1_txt else None,
            "S2":          _parse_float(s2_txt, max_val=30.0) if s2_txt else None,
            "DA":          _parse_float(da_txt, max_val=9.9)  if da_txt else None,
            "_source":     image_path,
        }
        shots.append(shot)
        seq += 1

    return shots


def extract(image_paths, min_conf=30, progress_cb=None):
    """
    Extract and merge shots from one or more screenshots.
    progress_cb: callable(done, total, path)
    Returns sorted deduplicated list of shot dicts, max 100 shots.
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    # Sort by filename so screenshot_00, screenshot_01 etc. merge in order
    image_paths = sorted(image_paths, key=lambda p: os.path.basename(p).lower())
    total = len(image_paths)
    all_shots = []

    if total == 1:
        shots = extract_single(image_paths[0], min_conf)
        if progress_cb:
            progress_cb(1, 1, image_paths[0])
        all_shots.extend(shots)
    else:
        results = {}
        with ThreadPoolExecutor(max_workers=min(total, 4)) as ex:
            futures = {ex.submit(extract_single, p, min_conf): p for p in image_paths}
            done = 0
            for fut in as_completed(futures):
                path = futures[fut]
                done += 1
                try:
                    results[path] = fut.result()
                except Exception as e:
                    results[path] = []
                    print(f"[WARN] OCR failed for {path}: {e}")
                if progress_cb:
                    progress_cb(done, total, path)
        for p in image_paths:
            all_shots.extend(results.get(p, []))

    if not all_shots:
        return []

    any_reliable = any(s.get("id_reliable") for s in all_shots)

    if any_reliable:
        merged = {}
        for shot in all_shots:
            sid = shot["id"]
            if sid not in merged:
                merged[sid] = shot
            else:
                existing_nulls = sum(1 for k in ["score","S1","S2","DA","hold_10","hold_10a"] if merged[sid].get(k) is None)
                new_nulls      = sum(1 for k in ["score","S1","S2","DA","hold_10","hold_10a"] if shot.get(k) is None)
                if new_nulls < existing_nulls:
                    merged[sid] = shot
        shots_out = sorted(merged.values(), key=lambda s: s["id"])
    else:
        shots_out = all_shots
        for i, s in enumerate(shots_out):
            s["id"] = i + 1

    if len(shots_out) > MAX_SHOTS:
        print(f"[WARN] {len(shots_out)} shots — capping at {MAX_SHOTS}")
        shots_out = shots_out[:MAX_SHOTS]

    ids = [s["id"] for s in shots_out]
    if len(set(ids)) != len(ids):
        for i, s in enumerate(shots_out):
            s["id"] = i + 1

    for s in shots_out:
        s.pop("id_reliable", None)
        s.pop("_source", None)

    return shots_out


if __name__ == "__main__":
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["scatt.png"]
    shots = extract(paths)
    if not shots:
        print("No shots extracted.")
        sys.exit(1)
    print(f"Extracted {len(shots)} shots")
    for s in shots:
        print(f"  {s}")
