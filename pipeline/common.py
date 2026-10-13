import csv
import json
import os
import re
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load_config(path=None):
    p = Path(path) if path else BASE / "config" / "pipeline.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    out = dict(cfg)
    out["raw_dir"] = str((BASE / cfg["raw_dir"]).resolve()) if not os.path.isabs(cfg["raw_dir"]) else cfg["raw_dir"]
    out["out_dir"] = str((BASE / cfg["out_dir"]).resolve()) if not os.path.isabs(cfg["out_dir"]) else cfg["out_dir"]
    out["sites"] = str((BASE / cfg["sites"]).resolve())
    out["species_map"] = str((BASE / cfg["species_map"]).resolve())
    return out


def read_dsv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        return [dict(r) for r in csv.DictReader(fh, delimiter=delim)]


def normalize(text):
    if text is None:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def load_species_map(path):
    m = {}
    for row in read_dsv(path):
        key = normalize(row.get("raw_name", ""))
        if not key:
            continue
        m[key] = {
            "species": (row.get("species") or "").strip(),
            "scientific_name": (row.get("scientific_name") or "").strip(),
            "taxon_group": (row.get("taxon_group") or "").strip(),
            "notes": (row.get("notes") or "").strip(),
        }
    return m


def load_sites(path):
    sites = {}
    if not os.path.exists(path):
        return sites
    for row in read_dsv(path):
        site = (row.get("site") or "").strip()
        if not site:
            continue
        key = normalize(site)
        sites.setdefault(key, {"site": site, "points": {}})
        pt = (row.get("point") or "").strip()
        if pt:
            sites[key]["points"][pt] = {
                "lat": (row.get("lat") or "").strip(),
                "lon": (row.get("lon") or "").strip(),
                "camera": (row.get("camera") or "").strip(),
                "deploy_start": (row.get("deploy_start") or "").strip(),
                "deploy_end": (row.get("deploy_end") or "").strip(),
            }
    return sites


def write_csv(path, rows, fieldnames=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
