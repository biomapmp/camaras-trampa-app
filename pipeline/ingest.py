import argparse
import os
import re
from datetime import datetime, timedelta

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from common import BASE, load_config, load_species_map, load_sites, normalize, write_csv

DATE_KEYS = (0x9003, 0x0132)
MAKE_KEY, MODEL_KEY = 0x010F, 0x0110
GPS_IFD = 0x8825


def _to_deg(value):
    try:
        d, m, s = value
        return float(d) + float(m) / 60.0 + float(s) / 3600.0
    except Exception:
        try:
            return float(value)
        except Exception:
            return None


def read_meta(path):
    meta = {"datetime": "", "make": "", "model": "", "lat": "", "lon": "", "width": "", "height": ""}
    try:
        with Image.open(path) as im:
            meta["width"], meta["height"] = im.size
            exif = im.getexif()
            if not exif:
                return meta
            meta["make"] = str(exif.get(MAKE_KEY, "") or "").strip()
            meta["model"] = str(exif.get(MODEL_KEY, "") or "").strip()
            for k in DATE_KEYS:
                if exif.get(k):
                    meta["datetime"] = str(exif.get(k)).strip()
                    break
            gps = exif.get_ifd(GPS_IFD)
            if gps:
                tags = {GPSTAGS.get(k, k): v for k, v in gps.items()}
                lat, lon = _to_deg(tags.get("GPSLatitude")), _to_deg(tags.get("GPSLongitude"))
                if lat is not None and lon is not None:
                    if str(tags.get("GPSLatitudeRef", "N")).upper().startswith("S"):
                        lat = -lat
                    if str(tags.get("GPSLongitudeRef", "E")).upper().startswith("W"):
                        lon = -lon
                    meta["lat"], meta["lon"] = f"{lat:.6f}", f"{lon:.6f}"
    except Exception:
        pass
    return meta


def parse_filename(stem):
    out = {"number": "", "species_raw": "", "point": "", "camera": ""}
    name = stem
    m = re.match(r"\s*(\d+)\s*[-.)]?\s*(.*)", name)
    if m:
        out["number"] = m.group(1)
        name = m.group(2)
    sp = name.split("(")[0]
    sp = re.split(r"\s+[-–]\s+", sp)[0]
    out["species_raw"] = re.sub(r"[-_\s]+$", "", sp).strip()
    pt = re.search(r"(?:Pto|Punto)\.?\s*(\d+)", stem, re.IGNORECASE)
    cam = re.search(r"Cam\.?\s*(\d+)", stem, re.IGNORECASE)
    out["point"] = pt.group(1) if pt else ""
    out["camera"] = cam.group(1) if cam else ""
    return out


def site_from_path(rel_parts, sites):
    raw = rel_parts[0] if rel_parts else ""
    cleaned = re.sub(r"^\s*\d+\s*[-.)]?\s*", "", raw).strip()
    key = normalize(cleaned)
    if key in sites:
        return sites[key]["site"]
    for k, v in sites.items():
        if k and (k in key or key in k):
            return v["site"]
    return cleaned or raw


def resolve_species(raw, smap):
    uncertain = 0
    key = normalize(raw)
    if "posible" in key:
        uncertain = 1
        key = normalize(key.replace("posible", ""))
    if key in smap:
        return smap[key], uncertain
    for k in sorted(smap, key=len, reverse=True):
        if k and k in key:
            return smap[k], uncertain
    return {"species": raw.strip().title() if raw else "", "scientific_name": "", "taxon_group": "", "notes": "unmapped"}, uncertain


def parse_dt(value):
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def collect_records(raw_dir, smap, sites, image_ext, media_ext):
    records = []
    for root, _, files in os.walk(raw_dir):
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in media_ext:
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, raw_dir)
            parts = rel.split(os.sep)
            stem = os.path.splitext(fn)[0]
            info = parse_filename(stem)
            sp, uncertain = resolve_species(info["species_raw"], smap)
            site = site_from_path(parts, sites)
            media_type = "image" if ext in image_ext else "video"
            meta = read_meta(full) if media_type == "image" else {"datetime": "", "make": "", "model": "", "lat": "", "lon": "", "width": "", "height": ""}
            dt = parse_dt(meta["datetime"])
            point = info["point"]
            camera = info["camera"]
            if site in sites and point in sites[site]["points"]:
                camera = camera or sites[site]["points"][point]["camera"]
            records.append({
                "filepath": os.path.abspath(full),
                "relpath": rel.replace(os.sep, "/"),
                "media_type": media_type,
                "site": site,
                "point": point,
                "camera": camera,
                "species_raw": info["species_raw"],
                "species": sp["species"],
                "scientific_name": sp["scientific_name"],
                "taxon_group": sp["taxon_group"],
                "uncertain": uncertain,
                "datetime": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "",
                "date": dt.strftime("%Y-%m-%d") if dt else "",
                "hour": dt.hour if dt else "",
                "lat": meta["lat"],
                "lon": meta["lon"],
                "make": meta["make"],
                "model": meta["model"],
                "width": meta["width"],
                "height": meta["height"],
                "size_bytes": os.path.getsize(full),
                "event_id": "",
                "_dt": dt,
            })
    return records


def assign_events(records, interval_min):
    labelled = [r for r in records if r.get("species")]
    labelled.sort(key=lambda r: (r["site"], r["point"], r["species"], r["_dt"] or datetime.max))
    interval = timedelta(minutes=int(interval_min))
    next_id = 0
    last_dt = {}
    current_event = {}
    for r in labelled:
        if r["_dt"] is None:
            continue
        k = (r["site"], r["point"], r["species"])
        if k not in last_dt or (r["_dt"] - last_dt[k]) > interval:
            next_id += 1
            current_event[k] = next_id
        r["event_id"] = f"E{current_event[k]:05d}"
        last_dt[k] = r["_dt"]
    return records


def run_ingest(cfg):
    smap = load_species_map(cfg["species_map"])
    sites = load_sites(cfg["sites"])
    records = collect_records(cfg["raw_dir"], smap, sites, {e.lower() for e in cfg["image_ext"]}, {e.lower() for e in cfg["media_ext"]})
    assign_events(records, cfg.get("event_interval_min", 60))
    return records


def main():
    ap = argparse.ArgumentParser(description="Carpetas de fotos + EXIF -> master sheet de camaras trampa")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_dir = cfg["out_dir"]
    os.makedirs(out_dir, exist_ok=True)
    smap = load_species_map(cfg["species_map"])

    records = run_ingest(cfg)
    fields = [k for k in records[0].keys() if k != "_dt"] if records else []
    for r in records:
        r.pop("_dt", None)
    write_csv(os.path.join(out_dir, "master_sheet.csv"), records, fields)

    ev_rows = []
    seen = set()
    by_id = {}
    for r in records:
        if r["event_id"] and r["event_id"] not in seen:
            seen.add(r["event_id"])
            by_id[r["event_id"]] = r
    for eid in sorted(by_id):
        r = by_id[eid]
        ev_rows.append({
            "event_id": eid,
            "site": r["site"],
            "point": r["point"],
            "camera": r["camera"],
            "species": r["species"],
            "scientific_name": r["scientific_name"],
            "datetime": r["datetime"],
            "date": r["date"],
            "hour": r["hour"],
            "lat": r["lat"],
            "lon": r["lon"],
        })
    write_csv(os.path.join(out_dir, "events.csv"), ev_rows)

    unmapped = sorted({r["species_raw"] for r in records if r["species_raw"] and normalize(r["species_raw"]) not in smap and not any(k in normalize(r["species_raw"]) for k in smap)})
    media = len(records)
    print(f"ok: {media} archivos -> {out_dir}/master_sheet.csv")
    print(f"    {len(ev_rows)} eventos independientes (>= {cfg.get('event_interval_min')} min) -> events.csv")
    print(f"    sitios: {len({r['site'] for r in records})} | especies: {len({r['species'] for r in records if r['species']})}")
    if unmapped:
        print("    sin mapear en species_map.csv: " + ", ".join(unmapped))


if __name__ == "__main__":
    main()
