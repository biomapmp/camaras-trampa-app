import argparse
import csv
import os
from pathlib import Path

from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parent


def thumb_name(relpath):
    return relpath.replace("/", "__")


def main():
    ap = argparse.ArgumentParser(description="Genera miniaturas para el bundle del repo (data/fotos)")
    ap.add_argument("--master-sheet", default=str(BASE / "data" / "master_sheet.csv"))
    ap.add_argument("--raw-dir", required=True, help="carpeta con las fotos originales (misma que uso ingest)")
    ap.add_argument("--out", default=str(BASE / "data" / "fotos"))
    ap.add_argument("--thumb-px", type=int, default=800)
    ap.add_argument("--quality", type=int, default=70)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    with open(args.master_sheet, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    ok = miss = 0
    for r in rows:
        rel = r.get("relpath")
        if not rel:
            continue
        src = os.path.join(args.raw_dir, rel)
        dst = os.path.join(args.out, thumb_name(rel))
        if not os.path.exists(src):
            miss += 1
            continue
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((args.thumb_px, args.thumb_px))
                im.save(dst, format="JPEG", quality=args.quality, optimize=True)
            ok += 1
        except Exception:
            miss += 1
    total = sum(os.path.getsize(os.path.join(args.out, f)) for f in os.listdir(args.out)) / 1024 / 1024
    print(f"ok: {ok} miniaturas -> {args.out} ({total:.1f} MB) | faltantes: {miss}")


if __name__ == "__main__":
    main()
