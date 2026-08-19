#!/usr/bin/env python3
"""Build the clone's catalog fixture from the captured discovery DOM.

Real entities come only from captured pages (exercises list pages 1-2, the
bench-press detail, the routines index + beginner category, the six-pack
routine detail). The remainder of the catalog is synthetic-but-plausible
fill that preserves filter-facet coverage, list density (18 cards per page)
and one pagination boundary, per the data-reduction rule (entity counts may
shrink; fields, density, pagination and states may not).

Output: clone/backend/fixtures/catalog.json (deterministic, sorted keys).
"""
from __future__ import annotations

import html as html_lib
import json
import pathlib
import re
import urllib.parse

SITE = pathlib.Path(__file__).resolve().parents[1]
CAP = SITE / "source-current" / "2026-08-18.jefit-r1"
OUT = SITE / "clone" / "backend" / "fixtures" / "catalog.json"

MUSCLES = [
    "Abs", "Back", "Biceps", "Cardio", "Chest", "Forearms", "Glutes",
    "Shoulders", "Triceps", "Upper Legs", "Lower Legs",
]
EQUIPMENT = [
    "Body Weight", "Bands", "Barbell", "Bench", "Dumbbell", "Exercise Ball",
    "EZ Curl Bar", "Kettlebell", "Cardio Machine", "Strength Machine",
    "Pullup Bar", "Weight Plate",
]

CARD_RE = re.compile(
    r'<a rel="noopener noreferrer" class="w-full border border-tertiary-gray '
    r'rounded-xl bg-bg-primary " href="/exercises/(\d+)/([a-z0-9-]+)">'
    r"(.*?)</a>",
    re.S,
)
NAME_RE = re.compile(
    r'class="text-\[1\.25rem\] font-semibold text-text-primary">([^<]+)</p>'
)
PILL_RE = re.compile(
    r'class="text-base/\[1\.4\] font-semibold text-jefit-blue underline">'
    r"([^<]+)</span>"
)
DESC_RE = re.compile(r'line-clamp-4">(.*?)</p>', re.S)
IMG_RE = re.compile(r"url=([^&\"]+)&")


def text(value: str) -> str:
    return html_lib.unescape(value).strip()


def parse_exercise_cards(page: pathlib.Path) -> list[dict]:
    doc = page.read_text()
    cards = []
    for match in CARD_RE.finditer(doc):
        body = match.group(3)
        name = NAME_RE.search(body)
        pills = PILL_RE.findall(body)
        desc = DESC_RE.search(body)
        image = IMG_RE.search(body)
        cards.append(
            {
                "id": int(match.group(1)),
                "slug": match.group(2),
                "name": text(name.group(1)) if name else "",
                "muscle": text(pills[0]) if pills else "",
                "equipment": text(pills[1]) if len(pills) > 1 else "",
                "description": text(desc.group(1)) if desc else "",
                "image": urllib.parse.unquote(
                    html_lib.unescape(image.group(1)) if image else ""
                ),
                "evidence": "captured-list-card",
            }
        )
    return cards


# Deterministic synthetic fill: names composed from facet vocabulary, short
# structural instructions. Never copied from any uncaptured source page.
SYNTH_MOVES = {
    "Abs": ("Hanging Knee Raise", "Weighted Crunch", "Plank Reach"),
    "Back": ("Single-Arm Row", "Reverse Fly Hold", "Rack Pull"),
    "Biceps": ("Concentration Curl", "Hammer Curl Iso", "Drag Curl"),
    "Cardio": ("Interval Climber", "Row Sprint", "Step Circuit"),
    "Chest": ("Squeeze Press", "Deficit Push-Up", "Incline Fly Hold"),
    "Forearms": ("Wrist Roller", "Reverse Wrist Curl", "Plate Pinch"),
    "Glutes": ("Hip Thrust Hold", "Frog Pump", "Deficit Lunge"),
    "Shoulders": ("Arnold Press Iso", "Y-Raise", "Cuban Rotation"),
    "Triceps": ("Overhead Extension", "Kickback Hold", "JM Press"),
    "Upper Legs": ("Tempo Split Squat", "Sissy Squat", "Leg Drive Press"),
    "Lower Legs": ("Standing Calf Drive", "Seated Calf Pulse", "Tibia Raise"),
}
SYNTH_DESC = (
    "{name} is a {muscle} movement performed with {equipment}.\n\n"
    "Steps :\n\n"
    "1.) Set up with the {equipment} in a stable position and brace your core.\n\n"
    "2.) Move through the full range under control, focusing on the "
    "{muscle} muscles.\n\n"
    "3.) Pause at the hardest point, then return slowly to the start and repeat.\n"
)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def synthesize(real: list[dict], target_total: int) -> list[dict]:
    have = {(e["muscle"], e["equipment"]) for e in real}
    images = [e["image"] for e in real if e["image"]]
    result = []
    next_id = 9001  # clone-local synthetic id space, never a captured id
    combos = []
    for mi, muscle in enumerate(MUSCLES):
        for ei in range(len(EQUIPMENT)):
            equipment = EQUIPMENT[(mi + ei) % len(EQUIPMENT)]
            combos.append((muscle, equipment))
    seen = set()
    for muscle, equipment in combos:
        if len(real) + len(result) >= target_total:
            break
        if (muscle, equipment) in have or (muscle, equipment) in seen:
            continue
        seen.add((muscle, equipment))
        base = SYNTH_MOVES[muscle][len(result) % 3]
        name = f"{equipment} {base}" if equipment != "Body Weight" else base
        result.append(
            {
                "id": next_id,
                "slug": slugify(name),
                "name": name,
                "muscle": muscle,
                "equipment": equipment,
                "description": SYNTH_DESC.format(
                    name=name, muscle=muscle, equipment=equipment
                ),
                "image": images[len(result) % len(images)],
                "evidence": "synthetic-facet-fill",
            }
        )
        next_id += 1
    return result


ROUTINE_CARD_RE = re.compile(r'href="/routines/(\d+)/([a-z0-9-]+)"(.*?)</a>', re.S)
ROUTINE_META_RE = re.compile(
    r'>(\d+ days?)[^<]*</span>|class="text-sm/\[1\.4\][^"]*">([^<]{2,60})</p>'
)
CATEGORY_RE = re.compile(r'href="/routines/([a-z][a-z-]+)"')


def parse_routiness(doc: str) -> list[dict]:
    routines = []
    seen = set()
    for match in ROUTINE_CARD_RE.finditer(doc):
        rid = int(match.group(1))
        if rid in seen:
            continue
        seen.add(rid)
        body = match.group(3)
        name = re.search(
            r'<h3 data-slot="text" class="font-semibold text-text-primary '
            r'line-clamp-2[^"]*">([^<]+)</h3>',
            body,
        ) or re.search(
            r'<h2 data-slot="text" class="text-\[2\.5rem\] font-bold '
            r'text-text-primary[^"]*">([^<]+)</h2>',
            body,
        ) or re.search(r"<h3[^>]*>([^<]{3,80})</h3>", body) or re.search(
            # Featured-carousel slides carry the plan name only in the banner
            # image's alt text ("<Name>banner").
            r'<img alt="([^"]{3,80}?)\s?banner"',
            body,
        )
        image = IMG_RE.search(body)
        metas = re.findall(
            r'class="text-sm/\[1\.4\] font-normal mt-1 truncate '
            r'text-text-secondary">([^<]+)<',
            body,
        )
        if not metas:
            pills = [
                re.sub(r"<!--[^>]*-->", "", pill).strip()
                for pill in re.findall(
                    r'bg-\[#EDF1F9\] text-secondary-gray rounded">(.*?)</span>',
                    body,
                )
            ]
            if len(pills) >= 3:
                level, focus, days = pills[0], pills[1], pills[2]
                metas = [f"{days.lower()} · {focus} · {level}"]
        description = re.search(
            r'class="font-normal text-secondary-gray text-sm '
            r'line-clamp-3">(.*?)</p>',
            body,
            re.S,
        )
        routines.append(
            {
                "id": rid,
                "slug": match.group(2),
                "name": text(name.group(1)) if name else "",
                "meta": text(metas[0]) if metas else "",
                "description": text(description.group(1)) if description else "",
                "image": urllib.parse.unquote(
                    html_lib.unescape(image.group(1)) if image else ""
                ),
                "evidence": "captured-list-card",
            }
        )
    return routines


def enrich_exercise_details(exercises: list[dict]) -> None:
    """Attach detail-page fields. Only /exercises/2/barbell-bench-press had its
    detail DOM captured (served verbatim); every other detail page renders
    these clone-local structural defaults, disclosed as inference."""

    difficulties = ("Beginner", "Intermediate", "Advanced")
    for index, entry in enumerate(exercises):
        cardio = entry["muscle"] == "Cardio"
        entry["detail"] = {
            "difficulty": difficulties[index % 3],
            "exercise_type": "Cardio" if cardio else "Strength",
            "log_type": "Duration and Distance" if cardio else "Weight and Reps",
            "evidence": "inferred-structural" if entry["id"] != 2 else "captured",
        }


def synthesize_routine_days(routines: list[dict], exercises: list[dict]) -> None:
    """Deterministic synthetic day plans for every routine whose detail DOM
    was not captured (only 19113 was; it is served from the frozen capture).
    Day density and Sets x Reps rows mirror the captured detail structure."""

    pool = [e for e in exercises if e["muscle"] != "Cardio"]
    reps_cycle = (8, 10, 12, 15)
    for r_index, routine in enumerate(routines):
        match = re.match(r"(\d+) day", routine["meta"])
        day_count = min(int(match.group(1)) if match else 3, 7)
        days = []
        for day_index in range(day_count):
            per_day = 4 + (r_index + day_index) % 3
            items = []
            for slot in range(per_day):
                exercise = pool[(r_index * 7 + day_index * 5 + slot * 3) % len(pool)]
                items.append(
                    {
                        "exercise_id": exercise["id"],
                        "name": exercise["name"],
                        "sets": 3 + (slot % 2),
                        "reps": reps_cycle[(day_index + slot) % 4],
                    }
                )
            days.append(
                {
                    "title": f"Day {day_index + 1}",
                    "est_min": 8 * per_day + 4,
                    "exercises": items,
                }
            )
        routine["days"] = days
        parts = [p.strip() for p in routine["meta"].split("·")]
        focus = parts[1] if len(parts) > 1 else "Maintaining"
        level = parts[2] if len(parts) > 2 else "Beginner"
        routine["focus"] = focus
        routine["level"] = level
        if not routine.get("description"):
            routine["description"] = (
                f"The {routine['name']} routine by JefitTeam is a "
                f"{parts[0] if parts else 'multi day'} workout plan. It is "
                f"a {level.lower()} level plan to achieve "
                f"{focus.lower()} fitness goals."
            )


def main() -> int:
    real = parse_exercise_cards(CAP / "exercises" / "desktop" / "page.html")
    page2 = parse_exercise_cards(CAP / "exercises-page2" / "desktop" / "page.html")
    known = {e["id"] for e in real}
    real += [e for e in page2 if e["id"] not in known]
    fill = synthesize(real, target_total=53)
    exercises = real + fill

    routines_doc = (CAP / "routines" / "desktop" / "page.html").read_text()
    beginner_doc = (
        CAP / "routines-beginner" / "desktop" / "page.html"
    ).read_text()
    routines = parse_routiness(routines_doc)
    known_r = {r["id"] for r in routines}
    for extra in parse_routiness(beginner_doc):
        if extra["id"] not in known_r:
            extra["evidence"] = "captured-category-card"
            known_r.add(extra["id"])
            routines.append(extra)
    detail_doc = (CAP / "routine-detail" / "desktop" / "page.html").read_text()
    focuses = ("Bulking", "Maintaining", "Cutting")
    for index, extra in enumerate(parse_routiness(detail_doc)):
        if extra["id"] in known_r:
            continue
        # Featured-carousel cards carry name+image only; the remaining fields
        # are deterministic synthetic fill (disclosed).
        if not extra["meta"]:
            extra["meta"] = f"{3 + index % 3} days · {focuses[index % 3]} · Beginner"
        extra["evidence"] = "captured-featured-card"
        known_r.add(extra["id"])
        routines.append(extra)
    categories = []
    for slug in dict.fromkeys(CATEGORY_RE.findall(routines_doc)):
        categories.append(slug)
    enrich_exercise_details(exercises)
    synthesize_routine_days(routines, exercises)

    catalog = {
        "schema_version": "jefit.clone-catalog.v1",
        "muscles": MUSCLES,
        "equipment": EQUIPMENT,
        "exercises": exercises,
        "routines": routines,
        "routine_categories": categories,
        "counts": {
            "exercises_total": len(exercises),
            "exercises_captured": len(real),
            "exercises_synthetic": len(fill),
            "page_size": 18,
            "routines_total": len(routines),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, indent=1, sort_keys=True) + "\n")
    print(
        f"exercises {len(exercises)} ({len(real)} captured), "
        f"routines {len(routines)}, categories {categories}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
