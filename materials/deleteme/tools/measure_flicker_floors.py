#!/usr/bin/env python3
"""Measure every checkpoint's source-to-source stability, then pick the oracle.

The pixel oracle must be chosen by measurement, not convention. A page that
animates - carousel, lazy-load, A/B allocation - moves between its own three
frames, and contracting against it would make the candidate chase source-side
noise. So: compute frame1 vs frame2 vs frame3 similarity for every captured
unit, and only units clearing the stability floor may carry a visual contract.

Metric matches the repo's pixel-mae-similarity-v1: 1 - mean(|a-b|)/255 over RGB.
"""
from __future__ import annotations
import json, pathlib, sys
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAP = ROOT / "source-current" / "2026-08-20.deleteme-r1"
OUT = ROOT / "scope" / "visual-calibration-report.json"
STABILITY_FLOOR = 0.98
THRESHOLD_MARGIN = 0.002
MAX_THRESHOLD = 0.995


def similarity(a: Image.Image, b: Image.Image) -> float:
    a = a.convert("RGB"); b = b.convert("RGB")
    if a.size != b.size:
        w = min(a.width, b.width); h = min(a.height, b.height)
        a = a.crop((0, 0, w, h)); b = b.crop((0, 0, w, h))
    pa = a.tobytes(); pb = b.tobytes()
    total = sum(abs(x - y) for x, y in zip(pa, pb))
    return 1.0 - (total / (len(pa) * 255.0))


def main() -> int:
    rows = []
    for meta in sorted(CAP.rglob("meta.json")):
        d = meta.parent
        frames = sorted(d.glob("frame-*.viewport.png"))
        if len(frames) < 3:
            continue
        imgs = [Image.open(f) for f in frames]
        pairs = {
            "f1_f2": similarity(imgs[0], imgs[1]),
            "f1_f3": similarity(imgs[0], imgs[2]),
            "f2_f3": similarity(imgs[1], imgs[2]),
        }
        floor = min(pairs.values())
        rows.append({
            "unit": f"{d.parent.name}.{d.name}",
            "state": d.parent.name,
            "viewport": d.name,
            "frame_pairs": {k: round(v, 6) for k, v in pairs.items()},
            "flicker_floor": round(floor, 6),
            "stable": floor >= STABILITY_FLOOR,
            "size": list(imgs[0].size),
        })
        for i in imgs:
            i.close()

    rows.sort(key=lambda r: r["flicker_floor"])
    stable = [r for r in rows if r["stable"]]
    unstable = [r for r in rows if not r["stable"]]

    # Oracle: the home page per viewport when it clears the floor, else the most
    # stable unit at that viewport. Recorded either way so the choice is auditable.
    oracle = {}
    for vp in ("desktop", "tablet", "mobile"):
        at_vp = [r for r in stable if r["viewport"] == vp]
        if not at_vp:
            continue
        home = next((r for r in at_vp if r["state"] == "home"), None)
        chosen = home or max(at_vp, key=lambda r: r["flicker_floor"])
        oracle[f"home.{vp}" if home else f"{chosen['state']}.{vp}"] = {
            "unit": chosen["unit"],
            "flicker_floor": chosen["flicker_floor"],
            "threshold": round(min(MAX_THRESHOLD, chosen["flicker_floor"] - THRESHOLD_MARGIN), 6),
            "selected_because": ("home cleared the stability floor" if home
                                 else "home was unstable; most stable unit at this viewport promoted"),
        }

    report = {
        "schema_version": "offline-clone.visual-calibration.v1",
        "metric": "pixel-mae-similarity-v1",
        "stability_floor": STABILITY_FLOOR,
        "threshold_rule": f"min({MAX_THRESHOLD}, flicker_floor - {THRESHOLD_MARGIN})",
        "ignore_regions": [],
        "units_measured": len(rows),
        "stable_units": len(stable),
        "unstable_units": len(unstable),
        "oracle": oracle,
        "rows": rows,
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"measured {len(rows)} units | stable {len(stable)} | unstable {len(unstable)}")
    print("\noracle:")
    for k, v in oracle.items():
        print(f"   {k:22s} floor={v['flicker_floor']:.6f} threshold={v['threshold']:.6f}")
    print("\nleast stable units:")
    for r in rows[:8]:
        print(f"   {r['unit']:34s} {r['flicker_floor']:.6f} {'' if r['stable'] else '<- below floor'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
