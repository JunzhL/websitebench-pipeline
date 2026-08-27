#!/usr/bin/env python3
"""Build member-area Jinja templates from the authenticated capture DOMs.

Inputs are the git-ignored ``source-auth-scratch/2026-08-18.jefit-auth-r1``
DOM files (PII-bearing evidence, consulted locally only). Every emitted
template is:

1. localized exactly like the anonymous pages (same Mapper policy — scripts
   dropped, assets onto the vendored mirror, external boundaries);
2. scrubbed: the capture account's username becomes ``{{ username }}``, its
   personal email becomes ``{{ email }}``, and community feeds are rebuilt
   from synthetic fixture posts so no third-party user content ships;
3. parametrized: entity regions (plan cards, editor rows, feed cards,
   settings values) become Jinja loops/variables bound to the clone's own
   SQLite state.

Everything else in the captured member DOM is preserved verbatim.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
SITE = TOOLS.parent

_spec = importlib.util.spec_from_file_location(
    "build_clone_pages", TOOLS / "build_clone_pages.py"
)
_bcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bcp)

SCRATCH = SITE / "source-auth-scratch" / "2026-08-18.jefit-auth-r1"
OUT = SITE / "clone" / "frontend" / "member"

CAPTURE_USERNAME = "Jz0023"
PERSONAL_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@(?!jefit\.com)[A-Za-z0-9.-]+\.[a-z]{2,}")

# capture file -> emitted template name (verbatim-localized base pass; the
# per-page surgery below refines the ones with dynamic regions).
BASES = {
    "workouts-empty.html": "workouts.html",
    "workouts-routine-saved.html": "workouts-populated.html",
    "workouts-routine-editor.html": "workouts-edit.html",
    "workouts-plan-menu.html": "workouts-plan-menu.html",
    "progress-empty.html": "progress-history.html",
    "workout-log-active.html": "workout-log-active.html",
    "workout-log-done.html": "workout-log-done.html",
    "progress-photos-empty.html": "progress-photos.html",
    "progress-insights-empty.html": "progress-insights.html",
    "progress-notes-empty.html": "progress-notes.html",
    "progress-bodystats-empty.html": "progress-body-stats.html",
    "member-exercises-custom-empty.html": "exercises-custom.html",
    "member-exercises.html": "exercises-database.html",
    "member-exercises-filters.html": "exercises-filters.html",
    "member-exercise-detail.html": "exercise-detail.html",
    "settings-account.html": "settings-account.html",
    "settings-profile.html": "settings-profile.html",
    "settings-privacy.html": "settings-privacy.html",
    "settings-datacontrols.html": "settings-datacontrols.html",
    "settings-integrations.html": "settings-integrations.html",
    "qa-feed.html": "qa.html",
    "popular-feed.html": "popular.html",
    "account-menu.html": "account-menu.html",
    "getapp-menu.html": "getapp-menu.html",
    "sync-info.html": "sync-info.html",
    "create-post-dialog.html": "create-post-dialog.html",
}
# DOM captured as a JSON-encoded string.
JSON_BASES = {
    "dashboard-discover-mycircle.json": "dashboard.html",
    "elite-plan-modal.json": "elite-plan-modal.html",
}


def load_dom(name: str) -> str:
    path = SCRATCH / name
    if name.endswith(".json"):
        return json.loads(path.read_text())
    return path.read_text()


AVATAR_RE = re.compile(r'/assets/customavatars/[A-Za-z0-9_.-]+')
# Neutral local placeholder: the captured avatar files belong to real community
# members (identifiers in the path, payloads outside the frozen closure), so no
# clone document may reference them.
AVATAR_PLACEHOLDER = (
    "data:image/svg+xml;utf8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E"
    "%3Crect width='40' height='40' fill='%23dbe3ef'/%3E"
    "%3Ccircle cx='20' cy='15' r='7' fill='%23a9b7cc'/%3E"
    "%3Cpath d='M6 40c0-8 6.5-13 14-13s14 5 14 13z' fill='%23a9b7cc'/%3E"
    "%3C/svg%3E"
)


def localize_and_scrub(dom: str, report: dict) -> str:
    mapper = _bcp.Mapper(report)
    dom = _bcp.rewrite_document(dom, mapper, report)
    dom = dom.replace(CAPTURE_USERNAME, "{{ username }}")
    dom = PERSONAL_EMAIL_RE.sub("{{ email }}", dom)
    dom = AVATAR_RE.sub(AVATAR_PLACEHOLDER, dom)
    return dom


def build_all() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: dict = {}
    for source, target in {**BASES, **JSON_BASES}.items():
        report = {
            "rewritten": 0,
            "dropped_tags": [],
            "content_fallback_refs": [],
            "script_blocks_dropped": 0,
            "ld_json_dropped": 0,
            "first_party_localized": 0,
            "external_boundaries": [],
        }
        dom = localize_and_scrub(load_dom(source), report)
        remote = _bcp.remaining_remote(dom)
        (OUT / target).write_text(dom)
        summary[target] = {
            "bytes": len(dom),
            "scripts_dropped": report["script_blocks_dropped"],
            "remaining_remote": remote[:10],
            "username_scrubbed": "{{ username }}" in dom,
        }
    return summary


DIV_TOKEN = re.compile(r"<div\b|</div>")


def match_div(doc: str, open_start: int) -> int:
    depth = 0
    for token in DIV_TOKEN.finditer(doc, open_start):
        if token.group(0) == "<div":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return token.end()
    raise SystemExit("unbalanced <div> during member surgery")


VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
_TAG = re.compile(r"<(/?)([a-zA-Z][-a-zA-Z0-9]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>")


def split_panel_fragment(fragment: str) -> tuple[str, str]:
    """Split a panel slice into (self-contained panel, ancestor closers).

    Panel slices are byte ranges cut between a nav's end and `</main>`, so they
    carry closers belonging to ancestors opened *before* the range. Those
    closers are not spurious for the composed document — they close the
    surrounding layout — but inside a wrapper element they terminate the
    wrapper early, ejecting the panel's content into the wrapper's parent.
    That is how all five settings panels ended up stacked as unhideable
    siblings. Return the balanced panel content for the wrapper plus the
    unmatched closers, which the caller re-emits outside the wrappers so the
    surrounding layout still closes exactly once.
    """
    stack: list[str] = []
    body: list[str] = []
    tail: list[str] = []
    pos = 0
    while pos < len(fragment):
        match = _TAG.search(fragment, pos)
        if match is None:
            body.append(fragment[pos:])
            break
        body.append(fragment[pos : match.start()])
        closing, name, attrs = match.group(1), match.group(2).lower(), match.group(3)
        if name in ("script", "style") and not closing:
            end = fragment.find(f"</{name}>", match.end())
            end = len(fragment) if end < 0 else end + len(name) + 3
            body.append(fragment[match.start() : end])
            pos = end
            continue
        if closing:
            if name in stack:
                while stack and stack[-1] != name:
                    body.append(f"</{stack.pop()}>")
                stack.pop()
                body.append(match.group(0))
            else:
                tail.append(match.group(0))  # closes an ancestor of the slice
        else:
            body.append(match.group(0))
            if name not in VOID_TAGS and not attrs.rstrip().endswith("/"):
                stack.append(name)
        pos = match.end()
    while stack:
        body.append(f"</{stack.pop()}>")
    return "".join(body), "".join(tail)


def balance_fragment(fragment: str) -> str:
    """Return `fragment` as a self-contained, well-nested HTML fragment.

    Drops closers for tags the fragment never opened and closes anything still
    open, leaving nesting untouched.
    """
    stack: list[str] = []
    out: list[str] = []
    pos = 0
    while pos < len(fragment):
        match = _TAG.search(fragment, pos)
        if match is None:
            out.append(fragment[pos:])
            break
        out.append(fragment[pos : match.start()])
        closing, name, attrs = match.group(1), match.group(2).lower(), match.group(3)
        if name in ("script", "style") and not closing:
            end = fragment.find(f"</{name}>", match.end())
            end = len(fragment) if end < 0 else end + len(name) + 3
            out.append(fragment[match.start() : end])
            pos = end
            continue
        if closing:
            if name in stack:  # drop closers for tags this fragment never opened
                while stack and stack[-1] != name:
                    out.append(f"</{stack.pop()}>")
                stack.pop()
                out.append(match.group(0))
        else:
            out.append(match.group(0))
            if name not in VOID_TAGS and not attrs.rstrip().endswith("/"):
                stack.append(name)
        pos = match.end()
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


def _read(name: str) -> str:
    return (OUT / name).read_text()


def _write(name: str, doc: str) -> None:
    (OUT / name).write_text(doc)


def surgery_feeds() -> None:
    """Replace the captured community post cards (real third-party content)
    with a fixture loop using the captured card markup."""

    card_open = '<div class="flex flex-col py-2 bg-bg-primary rounded-lg">'
    for name in ("qa.html", "popular.html"):
        doc = _read(name)
        starts = [m.start() for m in re.finditer(re.escape(card_open), doc)]
        if not starts:
            raise SystemExit(f"{name}: no post cards found")
        first, last = starts[0], starts[-1]
        last_end = match_div(doc, last)
        card = doc[first : match_div(doc, first)]
        # author name
        card = re.sub(
            r'(<p data-slot="text" class="text-base/\[1\.4\] font-semibold '
            r'text-text-primary">)[^<]+(</p>)',
            r"\1{{ p.author }}\2",
            card,
            count=1,
        )
        # relative age
        card = re.sub(
            r'(text-secondary-gray dark:text-d-secondary-gray">)[^<]+(</p>)',
            r"\1{{ p.age }}\2",
            card,
            count=1,
        )
        # body text (first pre/pre-wrap paragraph)
        card = re.sub(
            r'(whitespace-pre[^"]*">).*?(</p>)',
            r"\1{{ p.body }}\2",
            card,
            count=1,
            flags=re.S,
        )
        # likes / comments counts
        card = re.sub(
            r">\d+<!-- --> Likes</p>", ">{{ p.likes }}<!-- --> Likes</p>", card,
            count=1,
        )
        card = re.sub(
            r">\d+<!-- --> Comments</p>",
            ">{{ p.comments }}<!-- --> Comments</p>",
            card,
            count=1,
        )
        # drop any remaining captured images inside the card except the avatar
        doc = (
            doc[:first]
            + "{% for p in posts %}"
            + card
            + "{% endfor %}"
            + doc[last_end:]
        )
        _write(name, doc)


PLAN_CARD_OPEN = '<div class="rounded-xl border border-deco-gray'


def _parametrize_plan_card(card: str) -> str:
    card = re.sub(
        r'href="/my-jefit/workouts/edit\?id=\d+"',
        'href="/my-jefit/workouts/edit?id={{ p.id }}"',
        card,
    )
    card = re.sub(
        r'(<p data-slot="text" class="text-base/\[1\.4\] font-semibold '
        r'text-text-primary">)[^<]+(</p>)',
        r"\1{{ p.name }}\2",
        card,
        count=1,
    )
    card = re.sub(
        r"<span>\d+ days?</span>", "<span>{{ p.days_label }}</span>", card,
        count=1,
    )
    card = re.sub(
        r'(<span class="mx-2 hidden sm:block">•</span><span>)[^<]+(</span>'
        r'<span class="mx-2 hidden sm:block">•</span><span>)[^<]+(</span>)',
        r"\1{{ p.focus }}\2{{ p.level }}\3",
        card,
        count=1,
    )
    card = re.sub(
        r'id="headlessui-menu-button[^"]*"', 'id="plan-menu-{{ p.id }}"', card
    )
    return card


def surgery_workouts() -> None:
    doc = _read("workouts-populated.html")
    starts = [m.start() for m in re.finditer(re.escape(PLAN_CARD_OPEN), doc)]
    if len(starts) != 3:
        raise SystemExit(f"workouts: expected 3 plan cards, saw {len(starts)}")
    current_end = match_div(doc, starts[0])
    list_end = match_div(doc, starts[2])
    gap = doc[current_end : starts[1]]  # 'Downloaded Plans' heading + wrapper
    tail_close = doc[list_end : list_end + 6]
    if tail_close != "</div>":
        raise SystemExit("workouts: list wrapper close not found")
    card = _parametrize_plan_card(doc[starts[0] : current_end])
    current_block = (
        "{% if current %}{% with p = current %}" + card + "{% endwith %}{% endif %}"
    )
    list_block = (
        "{% if plans|length > 1 %}"
        + gap
        + "{% for p in plans %}"
        + card
        + "{% endfor %}</div>{% endif %}"
    )
    doc = doc[: starts[0]] + current_block + list_block + doc[list_end + 6 :]
    _write("workouts.html", doc)
    (OUT / "workouts-populated.html").unlink()


def surgery_editor() -> None:
    doc = _read("workouts-edit.html")
    # plan name input value
    name_at = doc.find("<input", 39000)
    doc = re.sub(
        r'(<input class="relative block w-full appearance-none rounded-lg '
        r"[^\"]*\" id=\"[^\"]*\" data-headlessui-state=\"\")([^>]*?)"
        r'value="[^"]*"',
        r'\1\2value="{{ plan.name }}"',
        doc,
        count=1,
    )
    del name_at
    # day sections: each day = day-header buttons + droppable rows container.
    # The capture holds one day ('Day 1' header + 3 exercise blocks). Carve:
    day_btn = doc.find(
        '<p data-slot="text" class="text-base/[1.4] font-semibold '
        'text-text-primary">Day 1'
    )
    if day_btn < 0:
        raise SystemExit("editor: day header not found")
    droppable = doc.find("<div data-rfd-droppable-id=")
    droppable_end = match_div(doc, droppable)
    # exercise blocks inside the droppable
    block_open = re.compile(
        r'<div data-rfd-draggable-context-id="[^"]*" data-rfd-draggable-id='
    )
    blocks = [
        m.start()
        for m in block_open.finditer(doc, droppable, droppable_end)
    ]
    if not blocks:
        raise SystemExit("editor: no exercise blocks")
    block = doc[blocks[0] : match_div(doc, blocks[0])]
    block = _parametrize_editor_block(block)
    droppable_open_tag = doc[droppable : doc.index(">", droppable) + 1]
    droppable_open_tag = re.sub(
        r'data-rfd-droppable-id="[^"]*"',
        'data-rfd-droppable-id="day-{{ d.id }}"',
        droppable_open_tag,
    )
    rows_html = (
        droppable_open_tag
        + "{% for x in d.exercises %}"
        + block
        + "{% endfor %}</div>"
    )
    # replace the droppable with the loop
    doc = doc[:droppable] + rows_html + doc[droppable_end:]
    # parametrize the day header (title + Day N label) nearest before droppable
    doc = doc.replace(">Day 1<", ">Day {{ d.position }}<", 1)
    doc = re.sub(
        r'(<button aria-label="edit-day-name" class="flex gap-1 items-center '
        r'text-left"><h2 data-slot="text" class="[^"]*">)[^<]*(</h2>)',
        r"\1{{ d.title }}\2",
        doc,
        count=1,
    )
    # wrap the day section in a loop: bound it by the containing element of
    # the day header and droppable. Use the shared wrapper div that starts
    # just before the 'Day N' button block and ends after the droppable.
    header_wrap = doc.rfind("<div", 0, doc.find(">Day {{ d.position }}<") - 400)
    day_end = doc.index("{% endfor %}</div>", header_wrap) + len(
        "{% endfor %}</div>"
    )
    # extend to the day wrapper's close
    day_close = match_div(doc, header_wrap)
    if day_close < day_end:
        day_close = day_end
    day_section = doc[header_wrap:day_close]
    doc = (
        doc[:header_wrap]
        + "{% for d in plan.days %}"
        + day_section
        + "{% endfor %}"
        + doc[day_close:]
    )
    # library rail: replace add-cards with a catalog loop
    adds = [
        m.start()
        for m in re.finditer(r'<button aria-label="Add [^"]*"', doc)
    ]
    if adds:
        first_card = doc.rfind("<div", 0, adds[0])
        last_end = match_div(doc, doc.rfind("<div", 0, adds[-1]))
        lib_card = doc[first_card : match_div(doc, first_card)]
        lib_card = re.sub(
            r'aria-label="Add [^"]*"',
            'aria-label="Add {{ e.name }}" data-exercise-id="{{ e.id }}"',
            lib_card,
        )
        lib_card = re.sub(r'alt="[^"]*"', 'alt="{{ e.name }} Demonstration"',
                          lib_card, count=1)
        lib_card = re.sub(r'srcset="[^"]*"', 'srcset="{{ e.srcset }}"',
                          lib_card, count=1)
        lib_card = re.sub(r'src="[^"]*"', 'src="{{ e.src }}"', lib_card,
                          count=1)
        lib_card = re.sub(
            r'(<p data-slot="text" class="text-base/\[1\.4\] font-normal '
            r'text-text-primary[^"]*">)[^<]+(</p>)',
            r"\1{{ e.name }}\2",
            lib_card,
            count=1,
        )
        doc = (
            doc[:first_card]
            + "{% for e in library %}"
            + lib_card
            + "{% endfor %}"
            + doc[last_end:]
        )
    _write("workouts-edit.html", doc)


def _parametrize_editor_block(block: str) -> str:
    block = re.sub(
        r'data-rfd-draggable-id="[^"]*"', 'data-rfd-draggable-id="x-{{ x.id }}"',
        block,
    )
    block = re.sub(
        r'data-de-id="[^"]*"', 'data-de-id="{{ d.id }}-{{ x.id }}"', block
    )
    block = re.sub(
        r'data-rfd-drag-handle-draggable-id="[^"]*"',
        'data-rfd-drag-handle-draggable-id="x-{{ x.id }}"',
        block,
    )
    block = re.sub(
        r'href="/exercises/\d+/[a-z0-9-]+"',
        'href="/exercises/{{ x.exercise_id }}/{{ x.slug }}"',
        block,
        count=1,
    )
    block = re.sub(r'alt="[^"]*"', 'alt="{{ x.name }} Demonstration"', block,
                   count=1)
    block = re.sub(r'srcset="[^"]*"', 'srcset="{{ x.srcset }}"', block, count=1)
    block = re.sub(r'src="[^"]*"', 'src="{{ x.src }}"', block, count=1)
    # visible exercise name (first bold paragraph after the thumb link)
    block = re.sub(
        r'(<p data-slot="text" class="text-base/\[1\.4\] font-semibold '
        r'text-text-primary[^"]*">)[^<]+(</p>)',
        r"\1{{ x.name }}\2",
        block,
        count=1,
    )
    # set rows: one captured row -> loop over 1..x.sets with entry values
    row = re.search(
        r'<div class="justify-center items-center gap-2" '
        r'style="display: grid; grid-template-columns: repeat\(9, 1fr\);">.*?'
        r"</div></div></div>",
        block,
        re.S,
    )
    if row:
        rows = [
            m.span()
            for m in re.finditer(
                r'<div class="justify-center items-center gap-2" '
                r'style="display: grid; grid-template-columns: repeat\(9, '
                r"1fr\);\">",
                block,
            )
        ]
        # region from first row start to end of block's row area: replace all
        # consecutive row blocks with one loop
        first_start = rows[0][0]
        # each row ends where the next begins; last row: use balanced match
        last_open = rows[-1][0]
        last_end = match_div(block, last_open)
        one_row = block[first_start : match_div(block, first_start)]
        one_row = re.sub(
            r'(style="grid-column: span 1;">)\d+(</div>)',
            r"\1{{ loop.index }}\2",
            one_row,
            count=1,
        )
        row_values = iter(("{{ x.weight_display }}", "{{ x.reps }}"))
        one_row = re.sub(
            r'value="\d+"',
            lambda _m: f'value="{next(row_values)}"',
            one_row,
            count=2,
        )
        one_row = re.sub(
            r'id="headlessui-input-[^"]*"',
            'id="set-{{ x.id }}-{{ loop.index }}-{{ loop.index0 }}"',
            one_row,
        )
        block = (
            block[:first_start]
            + "{% for s in range(x.sets) %}"
            + one_row
            + "{% endfor %}"
            + block[last_end:]
        )
    # rest input value (seconds)
    block = re.sub(
        r'value="60"', 'value="{{ x.rest_seconds }}"', block
    )
    return block


def _parametrize_summary(block: str) -> str:
    block = block.replace(">Training Summary 1<", ">Training Summary {{ loop.index }}<")
    block = re.sub(r">Aug 18, 2026<", ">{{ s.date_label }}<", block, count=1)
    block = re.sub(r">10:07 AM<", ">{{ s.time_label }}<", block, count=1)
    block = re.sub(
        r'(text-elite-gold">)\d+(</p>)', r"\1{{ s.records }}\2", block, count=1
    )
    timer_values = iter(
        (
            "{{ s.training_time }}",  # Training
            "00:00:00",  # Wasted
            "{{ s.actual_time }}",  # Actual
            "{{ s.complete }}",  # Complete
            "{{ s.rest_time }}",  # Rest
            "{{ s.volume }} lbs",  # Volume
        )
    )
    block = re.sub(
        r'(class="text-sm/\[1\.4\] font-semibold text-text-primary">)'
        r"(?:\d{2}:\d{2}:\d{2}|\d+|200 lbs)(</p>)",
        lambda m: m.group(1) + next(timer_values) + m.group(2),
        block,
        count=6,
    )
    # per-exercise group: thumbnail + name + BEST 1RM + set rows
    group = re.search(
        r'<div class="flex justify-between items-center">.*?'
        r"reps</p></div></div></div>",
        block,
        re.S,
    )
    if group is None:
        raise SystemExit("summary: exercise group not found")
    group_html = group.group(0)
    group_html = re.sub(r'alt="[^"]*"', 'alt="{{ g.name }}"', group_html, count=1)
    group_html = re.sub(r'srcset="[^"]*"', 'srcset="{{ g.srcset }}"', group_html,
                        count=1)
    group_html = re.sub(r'src="[^"]*"', 'src="{{ g.src }}"', group_html, count=1)
    group_html = re.sub(
        r'href="/my-jefit/progress/exercise/[^"]*"',
        'href="/my-jefit/progress/exercise/{{ g.exercise_id }}"',
        group_html,
        count=1,
    )
    group_html = re.sub(
        r'(font-semibold text-text-primary">)[^<]+(</p>)', r"\1{{ g.name }}\2",
        group_html, count=1,
    )
    group_html = re.sub(
        r">BEST 1RM: [\d.]+<", ">BEST 1RM: {{ g.best_1rm }}<", group_html,
        count=1,
    )
    row = re.search(
        r'<div class="grid grid-cols-3"><p data-slot="text" class="text-sm/'
        r'\[1\.4\] font-normal text-text-primary">\d+</p>.*?</div></div>',
        group_html,
        re.S,
    )
    if row is None:
        raise SystemExit("summary: set row not found")
    row_html = row.group(0)
    row_html = re.sub(r">\d+</p>", ">{{ r.set_index }}</p>", row_html, count=1)
    row_html = re.sub(
        r">[\d.]+ lbs x \d+ reps<",
        ">{{ r.weight_display }} lbs x {{ r.reps }} reps<",
        row_html,
        count=1,
    )
    group_html = (
        group_html[: row.start()]
        + "{% for r in g.sets %}"
        + row_html
        + "{% endfor %}"
        + group_html[row.end() :]
    )
    block = (
        block[: group.start()]
        + "{% for g in s.groups %}"
        + group_html
        + "{% endfor %}"
        + block[group.end() :]
    )
    return block


def surgery_history() -> None:
    done = _read("workout-log-done.html")
    anchor = done.find("Training Summary 1")
    block_start = done.rfind('<div class="flex flex-col gap-4">', 0, anchor)
    container_end = match_div(done, block_start)
    container = done[block_start:container_end]
    # inside the container: one session card; carve it (first child div)
    card_start = container.index("<div", 1)
    card = container[card_start : match_div(container, card_start)]
    summaries = (
        '<div class="flex flex-col gap-4">{% for s in sessions %}'
        + _parametrize_summary(card)
        + "{% endfor %}</div>"
    )

    doc = _read("progress-history.html")
    empty_at = doc.find('<img alt="No logs"')
    empty_start = doc.rfind("<div", 0, empty_at)
    empty_end = match_div(doc, empty_start)
    empty_block = doc[empty_start:empty_end]
    doc = (
        doc[:empty_start]
        + "{% if not sessions %}"
        + empty_block
        + "{% else %}"
        + summaries
        + "{% endif %}"
        + doc[empty_end:]
    )
    # log modal: carve the open portal dialog from the active capture and
    # embed it hidden; app.js toggles it.
    active = _read("workout-log-active.html")
    portal_at = active.find('<div id="headlessui-portal-root">')
    if portal_at < 0:
        raise SystemExit("history: log-modal portal not found")
    portal = active[portal_at : match_div(active, portal_at)]
    # library add-cards inside the modal -> catalog loop
    adds = [m.start() for m in re.finditer(r'<button aria-label="Add [^"]*"', portal)]
    if adds:
        first_card = portal.rfind("<div", 0, adds[0])
        last_end = match_div(portal, portal.rfind("<div", 0, adds[-1]))
        lib_card = portal[first_card : match_div(portal, first_card)]
        lib_card = re.sub(
            r'aria-label="Add [^"]*"',
            'aria-label="Add {{ e.name }}" data-exercise-id="{{ e.id }}"',
            lib_card,
        )
        lib_card = re.sub(r'alt="[^"]*"', 'alt="{{ e.name }} Demonstration"',
                          lib_card, count=1)
        lib_card = re.sub(r'srcset="[^"]*"', 'srcset="{{ e.srcset }}"',
                          lib_card, count=1)
        lib_card = re.sub(r'src="[^"]*"', 'src="{{ e.src }}"', lib_card,
                          count=1)
        lib_card = re.sub(
            r'(<p data-slot="text" class="text-base/\[1\.4\] font-normal '
            r'text-text-primary[^"]*">)[^<]+(</p>)',
            r"\1{{ e.name }}\2",
            lib_card,
            count=1,
        )
        portal = (
            portal[:first_card]
            + "{% for e in library %}"
            + lib_card
            + "{% endfor %}"
            + portal[last_end:]
        )
    portal = portal.replace(
        '<div id="headlessui-portal-root">',
        '<div id="headlessui-portal-root" data-clone-modal="workout-log" '
        'style="display:none">',
        1,
    )
    doc = doc.replace("</body>", portal + "</body>", 1)
    _write("progress-history.html", doc)
    (OUT / "workout-log-active.html").unlink()
    (OUT / "workout-log-done.html").unlink()


def surgery_bodystats() -> None:
    doc = _read("progress-body-stats.html")
    first_img = doc.find(
        '<div class="flex gap-4 items-center"><img alt="Weight"'
    )
    last_img = doc.find(
        '<div class="flex gap-4 items-center"><img alt="Height"'
    )
    if first_img < 0 or last_img < 0:
        raise SystemExit("bodystats: stat rows not found")
    first_row = doc.rfind("<div", 0, first_img)
    last_row = doc.rfind("<div", 0, last_img)
    last_end = match_div(doc, last_row)
    row = doc[first_row : match_div(doc, first_row)]
    row = re.sub(r'<img alt="[^"]*"', '<img alt="{{ s.stat }}"', row, count=1)
    row = re.sub(
        r'src="/my-jefit/body-stats/[^"]*"', 'src="{{ s.icon }}"', row, count=1
    )
    row = re.sub(
        r'href="/my-jefit/progress/body-stats/[^"]*"',
        'href="/my-jefit/progress/body-stats/{{ s.slug }}"',
        row,
        count=1,
    )
    row = re.sub(
        r'(font-semibold text-text-primary">)[^<]+(</p>)', r"\1{{ s.stat }}\2",
        row, count=1,
    )
    values = iter(
        ("{{ s.current_display }}", "{{ s.unit }}", "{{ s.goal_display }}",
         "{{ s.unit }}")
    )
    row = re.sub(
        r'(<p data-slot="text" class="[^"]*">)(--|lbs|%|in)(</p>)',
        lambda m: m.group(1) + next(values) + m.group(3),
        row,
        count=4,
    )
    row = re.sub(
        r'style="width: 0%;"', 'style="width: {{ s.progress }}%;"', row, count=1
    )
    row = re.sub(
        r'style="left: 0%;"', 'style="left: {{ s.progress }}%;"', row, count=1
    )
    row = re.sub(r">--</h4>", ">{{ s.progress_display }}</h4>", row, count=1)
    doc = (
        doc[:first_row]
        + "{% for s in stats %}"
        + row
        + "{% endfor %}"
        + doc[last_end:]
    )
    _write("progress-body-stats.html", doc)


SETTINGS_TAB_LABELS = ("Account", "Profile", "Privacy", "Data Controls",
                       "Integrations")


def _second_nav_bounds(doc: str) -> tuple[int, int]:
    """Bounds of the settings tab <nav>, found by its own tab labels.

    Positional selection ("the second nav") picked the mobile header's nav
    (`lg:hidden`), so the composed panels landed inside a container hidden at
    desktop widths — invisible once the fragments stopped breaking out of it.
    Match on the tab labels instead, and fail loudly rather than compose into
    the wrong container.
    """
    for match in re.finditer(r"<nav\b", doc):
        close = doc.find("</nav>", match.start())
        if close < 0:
            continue
        block = doc[match.start() : close]
        if all(f">{label}<" in block for label in SETTINGS_TAB_LABELS):
            return match.start(), close + 6
    raise SystemExit("settings: tab nav not found (no nav carries all tab labels)")


def surgery_settings() -> None:
    base = _read("settings-account.html")
    _, tabs_end = _second_nav_bounds(base)
    main_close = base.find("</main>", tabs_end)
    account_panel, panel_tail = split_panel_fragment(base[tabs_end:main_close])

    # --- account panel parametrization ---
    # verification badge + resend control
    account_panel = account_panel.replace(
        ">Unverified<", ">{{ verification_label }}<", 1
    )
    resend_at = account_panel.find("Resend Verification Link")
    if resend_at < 0:
        raise SystemExit("settings: resend link not found")
    ctl_start = max(
        account_panel.rfind("<button", 0, resend_at),
        account_panel.rfind("<a", 0, resend_at),
    )
    ctl_tag = account_panel[ctl_start : ctl_start + 3]
    close_token = "</button>" if ctl_tag.startswith("<b") else "</a>"
    ctl_end = account_panel.find(close_token, resend_at) + len(close_token)
    account_panel = (
        account_panel[:ctl_start]
        + "{% if not email_verified %}"
        + account_panel[ctl_start:ctl_end]
        + "{% endif %}"
        + account_panel[ctl_end:]
    )
    # account type + upgrade cards vs elite membership line
    type_at = account_panel.find(">Free</p>")
    upgrade_at = account_panel.find(
        '<div class="flex flex-col gap-2 mt-4">', type_at
    )
    upgrade_end = match_div(account_panel, upgrade_at)
    upgrade_block = account_panel[upgrade_at:upgrade_end]
    elite_block = (
        '<p data-slot="text" class="text-sm/[1.4] font-normal '
        'text-text-primary">{{ membership_line }}</p>'
    )
    account_panel = (
        account_panel[: type_at + 1]
        + "{{ account_type }}</p>"
        + account_panel[type_at + len(">Free</p>") : upgrade_at]
        + "{% if account_type == 'Free' %}"
        + upgrade_block
        + "{% else %}"
        + elite_block
        + "{% endif %}"
        + account_panel[upgrade_end:]
    )

    panels = {"account": account_panel}
    for tab, source in (
        ("profile", "settings-profile.html"),
        ("privacy", "settings-privacy.html"),
        ("data-controls", "settings-datacontrols.html"),
        ("integrations", "settings-integrations.html"),
    ):
        doc = _read(source)
        _, p_tabs_end = _second_nav_bounds(doc)
        p_main_close = doc.find("</main>", p_tabs_end)
        panels[tab], _ = split_panel_fragment(doc[p_tabs_end:p_main_close])
        (OUT / source).unlink()

    composed = "".join(
        f'<div data-settings-panel="{tab}"'
        + ("" if tab == "account" else ' style="display:none"')
        + ">"
        + panel
        + "</div>"
        for tab, panel in panels.items()
    )
    # The slices' ancestor closers belong outside the wrappers: emit them once
    # so the surrounding layout closes exactly as the captured document did.
    composed += panel_tail
    composed += (
        '<script id="jefit-settings" type="application/json">'
        "{{ settings_json }}</script>"
    )
    doc = base[:tabs_end] + composed + base[main_close:]
    _write("settings.html", doc)
    (OUT / "settings-account.html").unlink()


def surgery_member_exercises() -> None:
    # custom tab: parametrize the free-tier counter
    doc = _read("exercises-custom.html")
    doc = doc.replace("(0/3)", "({{ custom_count }}/3)")
    _write("exercises-custom.html", doc)

    # database tab: count + card loop + pagination + filters slide-over
    doc = _read("exercises-database.html")
    doc = re.sub(
        r">1295&nbsp;</span>EXERCISES FOUND</p>",
        ">{{ count }}&nbsp;</span>EXERCISES FOUND</p>",
        doc,
        count=1,
    )
    card_open = re.compile(
        r'<a rel="noopener noreferrer" class="[^"]*" '
        r'href="/my-jefit/exercises/\d+/[a-z0-9-]+">'
    )
    cards = [m.start() for m in card_open.finditer(doc)]
    if not cards:
        raise SystemExit("member exercises: no cards")
    first, last = cards[0], cards[-1]
    last_end = doc.find("</a>", last) + 4
    card = doc[first : doc.find("</a>", first) + 4]
    card = re.sub(
        r'href="/my-jefit/exercises/\d+/[a-z0-9-]+"',
        'href="/my-jefit/exercises/{{ e.id }}/{{ e.slug }}"',
        card,
        count=1,
    )
    card = re.sub(r'alt="[^"]*"', 'alt="{{ e.name }} Demonstration"', card,
                  count=1)
    card = re.sub(r'srcset="[^"]*"', 'srcset="{{ e.srcset }}"', card, count=1)
    card = re.sub(r'src="[^"]*"', 'src="{{ e.src }}"', card, count=1)
    card = re.sub(
        r'(class="text-\[1\.25rem\] font-semibold text-text-primary">)[^<]+'
        r"(</p>)",
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
    for match, var in zip(reversed(pills[:2]),
                          ("{{ e.equipment }}", "{{ e.muscle }}")):
        card = (
            card[: match.start()] + match.group(1) + var + match.group(3)
            + card[match.end() :]
        )
    card = re.sub(
        r'(line-clamp-4">).*?(</p>)', r"\1{{ e.description }}\2", card,
        count=1, flags=re.S,
    )
    doc = (
        doc[:first]
        + "{% for e in exercises %}"
        + card
        + "{% endfor %}"
        + doc[last_end:]
    )
    nav_at = doc.find('<nav aria-label="Page navigation"')
    if nav_at >= 0:
        first_close = doc.find("</nav>", nav_at)
        second_close = doc.find("</nav>", first_close + 6)
        doc = doc[:nav_at] + "{{ pagination }}" + doc[second_close + 6 :]
    # filters slide-over portal from the filters capture
    filters = _read("exercises-filters.html")
    portal_at = filters.find('<div id="headlessui-portal-root">')
    if portal_at >= 0:
        portal = filters[portal_at : match_div(filters, portal_at)]
        portal = portal.replace(
            '<div id="headlessui-portal-root">',
            '<div id="headlessui-portal-root" data-clone-modal="filters" '
            'style="display:none">',
            1,
        )
        doc = doc.replace("</body>", portal + "</body>", 1)
    doc = doc.replace(
        _bcp.RUNTIME_TAG,
        '<script id="jefit-catalog" type="application/json">{{ catalog_json }}'
        "</script>" + _bcp.RUNTIME_TAG,
        1,
    )
    _write("exercises-database.html", doc)
    (OUT / "exercises-filters.html").unlink()


def surgery_overlays() -> None:
    """Carve each captured overlay portal and embed it hidden in the member
    pages that open it; app.js toggles visibility."""

    portals: dict[str, str] = {}
    for name, key in (
        ("account-menu.html", "account-menu"),
        ("getapp-menu.html", "getapp-menu"),
        ("sync-info.html", "sync-info"),
        ("create-post-dialog.html", "create-post"),
        ("elite-plan-modal.html", "elite-plan"),
        ("workouts-plan-menu.html", "plan-menu"),
    ):
        doc = _read(name)
        at = doc.find('<div id="headlessui-portal-root">')
        if at < 0:
            raise SystemExit(f"{name}: portal not found")
        portal = doc[at : match_div(doc, at)]
        portal = portal.replace(
            '<div id="headlessui-portal-root">',
            f'<div data-clone-overlay="{key}" style="display:none">',
            1,
        )
        portals[key] = portal
        (OUT / name).unlink()

    everywhere = ("account-menu", "getapp-menu", "sync-info", "elite-plan")
    per_page = {
        "dashboard.html": everywhere + ("create-post",),
        "qa.html": everywhere + ("create-post",),
        "popular.html": everywhere + ("create-post",),
        "workouts.html": everywhere + ("plan-menu",),
        "workouts-edit.html": everywhere,
        "progress-history.html": everywhere,
        "progress-photos.html": everywhere,
        "progress-insights.html": everywhere,
        "progress-notes.html": everywhere,
        "progress-body-stats.html": everywhere,
        "exercises-custom.html": everywhere,
        "exercises-database.html": everywhere,
        "exercise-detail.html": everywhere,
        "settings.html": everywhere,
    }
    for page, keys in per_page.items():
        doc = _read(page)
        bundle = "".join(portals[key] for key in keys)
        if "</body>" in doc:
            doc = doc.replace("</body>", bundle + "</body>", 1)
        else:
            doc += bundle
        _write(page, doc)


def main() -> int:
    summary = build_all()
    print("-- surgeries --")
    surgery_feeds()
    print("feeds done")
    surgery_workouts()
    print("workouts done")
    surgery_editor()
    print("editor done")
    surgery_history()
    print("history done")
    surgery_bodystats()
    print("bodystats done")
    surgery_settings()
    print("settings done")
    surgery_member_exercises()
    print("member exercises done")
    surgery_overlays()
    print("overlays done")
    bad = {k: v["remaining_remote"] for k, v in summary.items()
           if v["remaining_remote"]}
    (SITE / "clone" / "frontend" / "member-rewrite-report.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True) + "\n"
    )
    for name, value in sorted(summary.items()):
        print(f"  {name}: {value['bytes']}B scripts={value['scripts_dropped']} "
              f"remote={len(value['remaining_remote'])}")
    if bad:
        print("REMOTE LEFT:", json.dumps(bad)[:600], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
