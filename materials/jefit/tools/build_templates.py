#!/usr/bin/env python3
"""Carve Jinja templates for the dynamic public pages out of the localized
frozen documents (clone/frontend/pages/*.html).

Everything here is mechanical region surgery on the captured DOM: entity
regions (cards, day lists, pills, instructions) become Jinja loops/variables
fed by clone/backend/fixtures/catalog.json; every carved snippet is the
captured markup itself with only the entity values parametrized. The captured
entity pages (/exercises/2/..., /routines/19113/...) keep their frozen
documents; these templates render every other fixture entity.

Also augments catalog.json with localized media fields (srcset/src per
exercise and routine image) computed with the capture harness's own
query-digest rule, existence-checked against the vendored mirror.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
import urllib.parse

TOOLS = pathlib.Path(__file__).resolve().parent
SITE = TOOLS.parent

_spec = importlib.util.spec_from_file_location(
    "build_clone_pages", TOOLS / "build_clone_pages.py"
)
_bcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bcp)

PAGES = SITE / "clone" / "frontend" / "pages"
TEMPLATES = SITE / "clone" / "frontend" / "templates"
FIXTURES = SITE / "clone" / "backend" / "fixtures"
ASSET_ROOT = _bcp.ASSET_ROOT
STATIC_PREFIX = _bcp.STATIC_PREFIX
CATALOG = FIXTURES / "catalog.json"

WIDTHS = [16, 32, 48, 64, 96, 128, 256, 384, 640, 750, 828, 1080, 1200,
          1920, 2048, 3840]


def fail(message: str) -> None:
    print(f"ANCHOR MISS: {message}", file=sys.stderr)
    raise SystemExit(1)


def optimizer_rel(image_url: str, width: int) -> str:
    query = f"url={urllib.parse.quote(image_url, safe='')}&w={width}&q=75"
    return _bcp.mirror_rel(f"https://www.jefit.com/_next/image?{query}")


def media_fields(image_url: str) -> dict[str, str]:
    """Localized srcset/src for one source image, existence-checked; widths
    the capture never fetched fall back to the nearest captured width."""

    existing: dict[int, str] = {}
    for width in WIDTHS:
        rel = optimizer_rel(image_url, width)
        if (ASSET_ROOT / rel).is_file():
            existing[width] = f"{STATIC_PREFIX}/{rel}"
    original_rel = _bcp.mirror_rel(image_url)
    original = (
        f"{STATIC_PREFIX}/{original_rel}"
        if (ASSET_ROOT / original_rel).is_file()
        else None
    )
    if not existing:
        # No optimizer variant captured; the mirrored original (or its
        # deterministic path) serves every width.
        src = original or f"{STATIC_PREFIX}/{original_rel}"
        srcset = f"{src} 3840w" if original else ""
        return {"srcset": srcset, "src": src}

    def nearest(width: int) -> str:
        if width in existing:
            return existing[width]
        if original:
            return original
        best = min(existing, key=lambda have: abs(have - width))
        return existing[best]

    srcset = ", ".join(f"{nearest(width)} {width}w" for width in WIDTHS)
    return {"srcset": srcset, "src": nearest(3840)}


def replace_once(doc: str, old: str, new: str, label: str) -> str:
    if doc.count(old) < 1:
        fail(f"{label}: pattern not found")
    return doc.replace(old, new, 1)


def region(doc: str, start_pat: str, end_pat: str, label: str) -> tuple[int, int]:
    start = doc.find(start_pat)
    if start < 0:
        fail(f"{label}: start not found")
    end = doc.find(end_pat, start)
    if end < 0:
        fail(f"{label}: end not found")
    return start, end + len(end_pat)


DIV_TOKEN = re.compile(r"<div\b|</div>")


def match_div(doc: str, open_start: int) -> int:
    """Index just past the </div> matching the <div at ``open_start``."""

    depth = 0
    for token in DIV_TOKEN.finditer(doc, open_start):
        if token.group(0) == "<div":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return token.end()
    fail("unbalanced <div>")
    return -1


CARD_START = (
    '<a rel="noopener noreferrer" class="w-full border border-tertiary-gray '
    'rounded-xl bg-bg-primary " href="/exercises/'
)


def carve_exercise_card(doc: str) -> tuple[str, int, int]:
    first = doc.find(CARD_START)
    if first < 0:
        fail("exercise card start")
    # region spans all consecutive cards
    last_start = doc.rfind(CARD_START)
    last_end = doc.find("</a>", last_start) + 4
    card_end = doc.find("</a>", first) + 4
    card = doc[first:card_end]
    return card, first, last_end


def parametrize_exercise_card(card: str) -> str:
    card = re.sub(
        r'href="/exercises/\d+/[a-z0-9-]+"',
        'href="/exercises/{{ e.id }}/{{ e.slug }}"',
        card,
        count=1,
    )
    card = re.sub(r'alt="[^"]*"', 'alt="{{ e.name }} Demonstration"', card, count=1)
    card = re.sub(r'srcset="[^"]*"', 'srcset="{{ e.srcset }}"', card, count=1)
    card = re.sub(r'src="[^"]*"', 'src="{{ e.src }}"', card, count=1)
    card = re.sub(
        r'(class="text-\[1\.25rem\] font-semibold text-text-primary">)[^<]+(</p>)',
        r"\1{{ e.name }}\2",
        card,
        count=1,
    )
    pills = list(
        re.finditer(
            r'(class="text-base/\[1\.4\] font-semibold text-jefit-blue '
            r'underline">)([^<]+)(</span>)',
            card,
        )
    )
    if len(pills) < 2:
        fail("exercise card pills")
    # replace second first so offsets stay valid
    m2, m1 = pills[1], pills[0]
    card = (
        card[: m2.start()]
        + m2.group(1)
        + "{{ e.equipment }}"
        + m2.group(3)
        + card[m2.end() :]
    )
    card = (
        card[: m1.start()]
        + m1.group(1)
        + "{{ e.muscle }}"
        + m1.group(3)
        + card[m1.end() :]
    )
    card = re.sub(
        r'(line-clamp-4">).*?(</p>)',
        r"\1{{ e.description }}\2",
        card,
        count=1,
        flags=re.S,
    )
    return card


def carve_pagination(doc: str) -> tuple[str, int, int]:
    start = doc.find('<nav aria-label="Page navigation"')
    if start < 0:
        fail("pagination nav")
    # two sibling navs (mobile + desktop); take through the second </nav>
    first_close = doc.find("</nav>", start)
    second_close = doc.find("</nav>", first_close + 6)
    if second_close < 0:
        fail("pagination second nav")
    return doc[start : second_close + 6], start, second_close + 6


def build_exercises_template() -> None:
    doc = (PAGES / "exercises.html").read_text()
    card, c_start, c_end = carve_exercise_card(doc)
    loop = "{% for e in exercises %}" + parametrize_exercise_card(card) + "{% endfor %}"
    doc = doc[:c_start] + loop + doc[c_end:]

    pagination, p_start, p_end = carve_pagination(doc)
    doc = doc[:p_start] + "{{ pagination }}" + doc[p_end:]

    doc = replace_once(
        doc,
        ">1295<!-- -->&nbsp;</span>EXERCISES FOUND</p>",
        ">{{ count }}<!-- -->&nbsp;</span>EXERCISES FOUND</p>",
        "exercises count",
    )
    doc = replace_once(
        doc,
        "<title>Exercise Database - JEFIT</title>",
        "<title>{{ title }}</title>",
        "exercises title",
    )
    # client-side filter data + page context
    doc = replace_once(
        doc,
        _bcp.RUNTIME_TAG,
        '<script id="jefit-catalog" type="application/json">{{ catalog_json }}'
        "</script>" + _bcp.RUNTIME_TAG,
        "exercises catalog embed",
    )
    TEMPLATES.mkdir(parents=True, exist_ok=True)
    (TEMPLATES / "exercises.html").write_text(doc)

    # store the pagination region + number-anchor variants for the renderer
    number_current = re.search(
        r'<a aria-label="Page 1"[^>]*>.*?</a>', pagination, re.S
    )
    number_other = re.search(
        r'<a aria-label="Page 2"[^>]*>.*?</a>', pagination, re.S
    )
    if not (number_current and number_other):
        fail("pagination number anchors")
    ui = {
        "pagination_region": pagination,
        "number_current": number_current.group(0),
        "number_other": number_other.group(0),
    }
    (FIXTURES / "ui.json").write_text(json.dumps(ui, indent=1, sort_keys=True))


def build_exercise_detail_template(catalog: dict) -> None:
    doc = (PAGES / "exercise-detail.html").read_text()
    doc = replace_once(
        doc,
        "<title>Barbell Bench Press - JEFIT</title>",
        "<title>{{ name }} - JEFIT</title>",
        "detail title",
    )
    doc = re.sub(
        r"(<h1[^>]*>)Barbell Bench Press(</h1>)", r"\1{{ name }}\2", doc, count=1
    )
    # hero: the gif preload + every gif img reference becomes the entity image
    doc = doc.replace(
        f"{STATIC_PREFIX}/cdn.jefit.com/assets/img/exercises/gifs/2.gif",
        "{{ hero_src }}",
    )
    # muscle pill rail: label + balanced flex container
    label_html = (
        '>Target Muscle Groups</span><div class="flex flex-wrap gap-2 '
        'justify-start">'
    )
    label_at = doc.find(label_html)
    if label_at < 0:
        fail("muscle pills label")
    flex_open = label_at + label_html.rindex("<div")
    m_start = label_at
    m_end = match_div(doc, flex_open)
    pills_region = doc[m_start:m_end]
    pill = re.search(
        r'<a class="flex items-center flex-col" data-headlessui-state="" '
        r'href="/exercises/chest">.*?</a>',
        pills_region,
        re.S,
    )
    if not pill:
        fail("muscle main pill")
    main_pill = pill.group(0)
    main_pill = re.sub(
        r'href="/exercises/[a-z-]+"', 'href="{{ muscle_href }}"', main_pill
    )
    main_pill = re.sub(r'alt="[^"]*"', 'alt="{{ muscle }} muscle group image"',
                       main_pill, count=1)
    main_pill = re.sub(r'src="[^"]*"', 'src="{{ muscle_icon }}"', main_pill,
                       count=1)
    main_pill = re.sub(
        r'(font-semibold text-jefit-blue">)[^<]+(</p>)', r"\1{{ muscle }}\2",
        main_pill, count=1,
    )
    doc = doc[:m_start] + label_html + main_pill + "</div>" + doc[m_end:]

    # equipment pill rail
    eq_label = '>Equipment</span><div class="flex flex-wrap gap-2 justify-start">'
    eq_at = doc.find(eq_label)
    if eq_at < 0:
        fail("equipment pills label")
    e_start = eq_at
    e_end = match_div(doc, eq_at + eq_label.rindex("<div"))
    eq_region = doc[e_start:e_end]
    eq_pill = re.search(
        r'<a class="flex items-center flex-col" data-headlessui-state="" '
        r'href="/exercises/[a-z-]+">.*?</a>',
        eq_region,
        re.S,
    )
    if not eq_pill:
        fail("equipment pill")
    equipment_pill = eq_pill.group(0)
    equipment_pill = re.sub(
        r'href="/exercises/[a-z-]+"', 'href="{{ equipment_href }}"',
        equipment_pill,
    )
    equipment_pill = re.sub(
        r'alt="[^"]*"', 'alt="{{ equipment }} equipment example"',
        equipment_pill, count=1,
    )
    equipment_pill = re.sub(
        r'(srcset|src)="[^"]*"', r'\1="{{ equipment_icon }}"', equipment_pill
    )
    equipment_pill = re.sub(
        r'(font-semibold text-jefit-blue">)[^<]+(</p>)',
        r"\1{{ equipment }}\2", equipment_pill, count=1,
    )
    doc = doc[:e_start] + eq_label + equipment_pill + "</div>" + doc[e_end:]

    # difficulty / exercise type / log type values
    doc = replace_once(
        doc,
        '>Difficulty</span><p data-slot="text" class="text-base/[1.4] '
        'font-normal text-text-primary capitalize">beginner</p>',
        '>Difficulty</span><p data-slot="text" class="text-base/[1.4] '
        'font-normal text-text-primary capitalize">{{ difficulty }}</p>',
        "difficulty value",
    )
    doc = replace_once(doc, 'capitalize">strength<', 'capitalize">{{ exercise_type }}<',
                       "exercise type value")
    doc = replace_once(doc, 'capitalize">weight and reps<',
                       'capitalize">{{ log_type }}<', "log type value")

    # instructions body
    doc = re.sub(
        r'(>Instructions</h2><p data-slot="text" class="text-base/\[1\.4\] '
        r'font-normal text-text-primary whitespace-pre-wrap">).*?(</p>)',
        r"\1{{ instructions }}\2",
        doc,
        count=1,
        flags=re.S,
    )
    # alternative rail heading + cards -> fixture loop over same-muscle items
    doc = replace_once(
        doc,
        ">Alternative Chest Exercises</p>",
        ">Alternative {{ muscle }} Exercises</p>",
        "alternatives heading",
    )
    # two alternatives carousels (desktop + mobile) of 25 slides each; both
    # become the same fixture loop
    slide_open = '<div role="group" aria-roledescription="slide"'
    search_from = 0
    for _ in range(2):
        first = doc.find(slide_open, search_from)
        if first < 0:
            fail("alternatives slides")
        # consecutive slides: advance while the next slide follows the close
        cursor = first
        last_end = first
        while True:
            close = match_div(doc, cursor)
            last_end = close
            nxt = doc.find(slide_open, close)
            if nxt < 0 or doc[close:nxt].strip() != "":
                break
            cursor = nxt
        slide = doc[first : match_div(doc, first)]
        slide = re.sub(
            r'href="/exercises/\d+/[a-z0-9-]+"',
            'href="/exercises/{{ a.id }}/{{ a.slug }}"',
            slide,
            count=1,
        )
        slide = re.sub(r'alt="[^"]*"', 'alt="{{ a.name }}banner"', slide, count=1)
        slide = re.sub(r'srcset="[^"]*"', 'srcset="{{ a.srcset }}"', slide, count=1)
        slide = re.sub(r'src="[^"]*"', 'src="{{ a.src }}"', slide, count=1)
        slide = re.sub(
            r'(font-normal text-white p-2">)[^<]+(</p>)', r"\1{{ a.name }}\2",
            slide, count=1,
        )
        slide = slide.replace(' style="transform: translate3d(0px, 0px, 0px);"', "")
        inserted = "{% for a in alternatives %}" + slide + "{% endfor %}"
        doc = doc[:first] + inserted + doc[last_end:]
        search_from = first + len(inserted)
    (TEMPLATES / "exercise-detail.html").write_text(doc)


def build_routines_templates(catalog: dict) -> None:
    doc = (PAGES / "routines.html").read_text()
    li_start = doc.find('<li><a class="group flex h-full items-center gap-3')
    if li_start < 0:
        fail("routines list start")
    last_li = doc.rfind('<li><a class="group flex h-full items-center gap-3')
    last_end = doc.find("</li>", last_li) + 5
    li = doc[li_start : doc.find("</li>", li_start) + 5]
    li = re.sub(
        r'href="/routines/\d+/[a-z0-9-]+"',
        'href="/routines/{{ r.id }}/{{ r.slug }}"',
        li,
        count=1,
    )
    li = re.sub(r'alt="[^"]*"', 'alt="{{ r.name }} banner"', li, count=1)
    li = re.sub(r'srcset="[^"]*"', 'srcset="{{ r.srcset }}"', li, count=1)
    li = re.sub(r'src="[^"]*"', 'src="{{ r.src }}"', li, count=1)
    li = re.sub(
        r'(line-clamp-2 text-lg leading-snug sm:text-xl">)[^<]+(</h3>)',
        r"\1{{ r.name }}\2",
        li,
        count=1,
    )
    li = re.sub(
        r'(mt-1 truncate text-text-secondary">)[^<]+(</p>)',
        r"\1{{ r.meta }}\2",
        li,
        count=1,
    )
    loop = "{% for r in routines %}" + li + "{% endfor %}"
    doc = doc[:li_start] + loop + doc[last_end:]
    doc = replace_once(
        doc,
        '<span data-slot="text" class="text-sm/[1.4] font-semibold '
        'text-text-primary">Most Downloaded</span>',
        '<span data-slot="text" class="text-sm/[1.4] font-semibold '
        'text-text-primary">{{ sort_label }}</span>',
        "sort label",
    )
    (TEMPLATES / "routines.html").write_text(doc)

    # category page template from the beginner capture
    cat = (PAGES / "routines-beginner.html").read_text()
    grid_anchor = '<a data-headlessui-state="" href="/routines/'
    g_start = cat.find(grid_anchor)
    if g_start < 0:
        fail("category grid start")
    g_last = cat.rfind(grid_anchor)
    g_end = cat.find("</a>", g_last) + 4
    card = cat[g_start : cat.find("</a>", g_start) + 4]
    card = re.sub(
        r'href="/routines/\d+/[a-z0-9-]+"',
        'href="/routines/{{ r.id }}/{{ r.slug }}"',
        card,
        count=1,
    )
    card = re.sub(r'alt="[^"]*"', 'alt="Routine Banner for {{ r.name }}"', card,
                  count=1)
    card = re.sub(r'srcset="[^"]*"', 'srcset="{{ r.srcset }}"', card, count=1)
    card = re.sub(r'src="[^"]*"', 'src="{{ r.src }}"', card, count=1)
    pills = list(
        re.finditer(
            r'(bg-\[#EDF1F9\] text-secondary-gray rounded">)(.*?)(</span>)', card
        )
    )
    if len(pills) >= 3:
        for match, var in zip(
            reversed(pills[:3]), ("{{ r.days_label }}", "{{ r.focus }}",
                                  "{{ r.level }}")
        ):
            card = card[: match.start()] + match.group(1) + var + match.group(3) + card[match.end():]
    card = re.sub(
        r'(<h2 data-slot="text" class="text-\[2\.5rem\] font-bold '
        r'text-text-primary[^"]*">)[^<]+(</h2>)',
        r"\1{{ r.name }}\2",
        card,
        count=1,
    )
    card = re.sub(
        r'(class="font-normal text-secondary-gray text-sm line-clamp-3">).*?(</p>)',
        r"\1{{ r.description }}\2",
        card,
        count=1,
        flags=re.S,
    )
    cat = cat[:g_start] + "{% for r in routines %}" + card + "{% endfor %}" + cat[g_end:]
    title = re.search(r"<title>([^<]*)</title>", cat)
    cat = cat.replace(title.group(0), "<title>{{ title }}</title>", 1)
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", cat, re.S)
    if not heading:
        fail("category heading")
    cat = cat.replace(heading.group(1), "{{ heading }}", 1)
    (TEMPLATES / "routines-category.html").write_text(cat)


def build_routine_detail_template() -> None:
    doc = (PAGES / "routine-detail.html").read_text()
    title = re.search(r"<title>([^<]*)</title>", doc)
    doc = doc.replace(title.group(0), "<title>{{ name }} - JEFIT</title>", 1)
    # plan name appears as heading + summary sentence + og fields
    doc = doc.replace(">6-Weeks to Six-Pack Abs</", ">{{ name }}</")
    # tag pills row: Cutting / Intermediate / Machine strength
    for value, var in (
        (">Cutting<", ">{{ focus }}<"),
        (">Intermediate<", ">{{ level }}<"),
        (">Machine strength<", ">{{ equipment_tag }}<"),
    ):
        if value in doc:
            doc = doc.replace(value, var, 1)
    # Plan Details summary + description
    doc = re.sub(
        r"The 6-Weeks to Six-Pack Abs routine by JefitTeam is a 2 day workout "
        r"plan\. It is an intermediate level plan to achieve cutting fitness "
        r"goals\.",
        "{{ summary }}",
        doc,
        count=1,
    )
    # the captured description appears twice: the visible body copy and the
    # meta description; both become the entity's description
    while True:
        d_start = doc.find("For those looking to build a defined six pack")
        if d_start < 0:
            break
        end_p = doc.find("</p>", d_start)
        end_attr = doc.find('"', d_start)
        d_end = min(x for x in (end_p, end_attr) if x > 0)
        doc = doc[:d_start] + "{{ description }}" + doc[d_end:]
    if "{{ description }}" not in doc:
        fail("routine description")

    # banner images (list + og) use the routine banner media
    doc = re.sub(r'srcset="[^"]*uc%2Ffile[^"]*"', 'srcset="{{ banner_srcset }}"', doc)
    doc = re.sub(r'src="[^"]*uc%2Ffile[^"]*"', 'src="{{ banner_src }}"', doc)
    doc = re.sub(
        r'srcset="[^"]*3ea96139e5204b56[^"]*"', 'srcset="{{ banner_srcset }}"', doc
    )
    doc = re.sub(
        r'src="[^"]*3ea96139e5204b56[^"]*"', 'src="{{ banner_src }}"', doc
    )

    # day cards region: from the first day header block to the last row end,
    # bounded by the Featured heading container.
    day_start = doc.find('<div class="flex flex-col grow rounded-lg">')
    if day_start < 0:
        fail("day cards start")
    featured = doc.find('<div class="mx-auto max-w-8xl mt-10 mb-20 px-4">')
    if featured < 0 or featured < day_start:
        fail("featured bound")
    day_region = doc[day_start:featured]
    # exercise row snippet
    row = re.search(
        r'<div class="flex gap-3 items-center py-3 px-2 relative">.*?'
        r"Sets x .*?Reps</p>.*?</div>",
        day_region,
        re.S,
    )
    if not row:
        fail("day exercise row")
    row_html = row.group(0)
    row_html = re.sub(
        r'href="/exercises/\d+/[a-z0-9-]+"',
        'href="/exercises/{{ x.id }}/{{ x.slug }}"',
        row_html,
    )
    row_html = re.sub(r'alt="[^"]*"', 'alt="{{ x.name }} Demonstration"',
                      row_html, count=1)
    row_html = re.sub(r'srcset="[^"]*"', 'srcset="{{ x.srcset }}"', row_html,
                      count=1)
    row_html = re.sub(r'src="[^"]*"', 'src="{{ x.src }}"', row_html, count=1)
    row_html = re.sub(
        r'(font-semibold text-text-primary">)[^<]+(</p>)', r"\1{{ x.name }}\2",
        row_html, count=1,
    )
    row_html = re.sub(
        r">\d+ Sets x \d+ Reps</p>", ">{{ x.sets }} Sets x {{ x.reps }} Reps</p>",
        row_html, count=1,
    )
    # day header block: bounded between header start and the rows container
    header = re.search(
        r'<div class="flex items-center gap-4 justify-between bg-alice-blue '
        r'rounded-t-lg[^>]*>.*?</div></div>',
        day_region,
        re.S,
    )
    if not header:
        fail("day header")
    header_html = header.group(0)
    header_html = re.sub(
        r'(font-semibold text-text-primary">)Any(</p>)', r"\1Any\2", header_html
    )
    header_html = re.sub(
        r'(font-semibold text-text-primary">)Week 1 - 3(</p>)',
        r"\1{{ d.title }}\2",
        header_html,
        count=1,
    )
    header_html = re.sub(
        r">Est\.&nbsp;<!-- -->\d+<!-- -->&nbsp;min</p>",
        ">Est.&nbsp;<!-- -->{{ d.est_min }}<!-- -->&nbsp;min</p>",
        header_html,
        count=1,
    )
    header_html = re.sub(
        r">\d+<!-- --> exercise<!-- -->s</p>",
        ">{{ d.count }}<!-- --> exercise<!-- -->s</p>",
        header_html,
        count=1,
    )
    rows_open = '<div class="border-2 border-border-secondary rounded-b-md overflow-hidden w-full flex-col flex p-4">'
    if rows_open not in day_region:
        fail("day rows container")
    # Source copy for a day with no exercises (from the captured builder DOM).
    empty_day = (
        '<p data-slot="text" class="text-base/[1.4] font-semibold '
        'text-text-primary">This day is empty</p>'
    )
    day_card = (
        header_html
        + rows_open
        + "{% if d.exercises %}{% for x in d.exercises %}"
        + row_html
        + "{% endfor %}{% else %}"
        + empty_day
        + "{% endif %}</div>"
    )
    day_loop = (
        '<div class="flex flex-col grow rounded-lg">{% for d in days %}'
        '<div class="mb-6">' + day_card + "</div>{% endfor %}</div>"
    )
    doc = doc[:day_start] + day_loop + doc[featured:]
    (TEMPLATES / "routine-detail.html").write_text(doc)


def augment_catalog() -> dict:
    catalog = json.loads(CATALOG.read_text())
    for entry in catalog["exercises"]:
        entry.update(media_fields(entry["image"]))
    for entry in catalog["routines"]:
        entry.update(media_fields(entry["image"]))
        match = re.match(r"(\d+)", entry["meta"])
        count = int(match.group(1)) if match else len(entry["days"])
        entry["days_label"] = f"{count} Day" if count == 1 else f"{count} Days"
    CATALOG.write_text(json.dumps(catalog, indent=1, sort_keys=True) + "\n")
    return catalog


def main() -> int:
    catalog = augment_catalog()
    build_exercises_template()
    build_exercise_detail_template(catalog)
    build_routines_templates(catalog)
    build_routine_detail_template()
    print("templates:", sorted(p.name for p in TEMPLATES.glob("*.html")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
