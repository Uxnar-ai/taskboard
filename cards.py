#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taskboard · 卡片读写与排期

卡片就是 auto-lab 的 markdown 卡片（<LOCAL_PATH>/auto-lab/tasks/*.md），
格式与 tasks/TEMPLATE.md 完全一致 —— 所以 scripts/tasks.py 一行不用改也能读。

本模块只做三件事：读、写、算日期。不碰 HTTP，不碰认证。
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

# 卡片目录（可用 TASKBOARD_CARDS 覆盖，便于测试）
CARDS_DIR = Path(os.environ.get("TASKBOARD_CARDS") or r"<LOCAL_PATH>/auto-lab/tasks")
ARCHIVE_DIR = CARDS_DIR / "archive"

SKIP = {"TEMPLATE.md", "README.md"}
OPEN_STATUS = {"planned", "doing", "carry"}          # 占用当天名额 / 未结案
CLOSED_STATUS = {"done", "abandoned", "stale"}       # 与 tasks.py 的 CLOSED 一致
ALL_STATUS = ["planned", "doing", "carry", "done", "abandoned", "stale"]
STATUS_LABEL = {
    "planned": "待做",
    "doing": "执行中",
    "carry": "明天收尾",
    "done": "已完成",
    "abandoned": "作废",
    "stale": "过期放弃",
}
BUDGETS = ["full", "half", "touch"]
MAX_PER_DAY = 2

META_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")


# ---------------------------------------------------------------- 读

def _split(text: str):
    """拆成 (meta dict, sections [(title, body)], title)"""
    meta: dict[str, str] = {}
    sections: list[tuple[str, str]] = []
    title = ""
    cur = None
    buf: list[str] = []

    for line in text.splitlines():
        if cur is None:
            m = META_RE.match(line)
            if m:
                meta[m.group(1)] = m.group(2).strip()
                continue
            if not title and line.startswith("# "):
                title = line[2:].strip()
                continue
            m2 = SECTION_RE.match(line)
            if m2:
                cur = m2.group(1)
                buf = []
            continue
        m2 = SECTION_RE.match(line)
        if m2:
            sections.append((cur, "\n".join(buf).strip()))
            cur = m2.group(1)
            buf = []
        else:
            buf.append(line)
    if cur is not None:
        sections.append((cur, "\n".join(buf).strip()))
    return meta, sections, title


def _bullets(body: str) -> list[str]:
    out = []
    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^[-*+]\s+", "", s)
        s = re.sub(r"^\[[ xX]\]\s*", "", s)     # - [ ] xxx → xxx
        if s in ("（待补）", "(待补)"):
            continue
        out.append(s)
    return out


def _parse_card(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, sections, title = _split(text)
    sec = {k: v for k, v in sections}

    stem_parts = path.stem.split("-", 3)
    if len(stem_parts) == 4:
        meta.setdefault("date", "-".join(stem_parts[:3]))
        meta.setdefault("slug", stem_parts[3])

    return {
        "path": path,
        "name": path.name,
        "slug": meta.get("slug") or path.stem,
        "title": title or meta.get("slug", path.stem),
        "date": meta.get("date", ""),
        "status": meta.get("status", "planned"),
        "budget": meta.get("budget", "full"),
        "spec": meta.get("spec", ""),
        "lede": sec.get("一句话", "").strip(),
        "reqs": _bullets(sec.get("硬要求", "")),
        "criteria": _bullets(sec.get("完成判据", "")),
        "notes": sec.get("备注", "").strip(),
        "created": meta.get("created", ""),
        "updated": meta.get("updated", ""),
        "origin": meta.get("origin", "cli"),
        "archived": path.parent.name == "archive",
        "raw": text,
    }


def list_cards(include_archive: bool = False) -> list[dict]:
    out = []
    if not CARDS_DIR.exists():
        return out
    for p in sorted(CARDS_DIR.glob("*.md")):
        if p.name in SKIP:
            continue
        try:
            out.append(_parse_card(p))
        except OSError:
            continue
    if include_archive and ARCHIVE_DIR.exists():
        for p in sorted(ARCHIVE_DIR.glob("*.md")):
            try:
                out.append(_parse_card(p))
            except OSError:
                continue
    return out


def get(slug: str, include_archive: bool = True) -> dict | None:
    for c in list_cards(include_archive=include_archive):
        if c["slug"] == slug:
            return c
    return None


# ---------------------------------------------------------------- 排期

def _open_on(day: str, cards: list[dict] | None = None) -> int:
    cards = cards if cards is not None else list_cards()
    return sum(1 for c in cards if c["date"] == day and c["status"] in OPEN_STATUS)


def pick_date(start: str, skip_slug: str | None = None) -> tuple[str, bool]:
    """从 start 起找一个还没挤满的日期。返回 (实际日期, 是否被顺延)"""
    cards = [c for c in list_cards() if c["slug"] != skip_slug]
    try:
        d = datetime.strptime(start, "%Y-%m-%d").date()
    except ValueError:
        d = date.today()
    for _ in range(180):
        if _open_on(d.isoformat(), cards) < MAX_PER_DAY:
            return d.isoformat(), d.isoformat() != start
        d += timedelta(days=1)
    return start, False


def today_view(day: str | None = None) -> dict:
    """等价于 tasks.py today 的语义"""
    day = day or date.today().isoformat()
    live = [c for c in list_cards() if c["status"] not in CLOSED_STATUS]
    here = [c for c in live if c["date"] == day]
    overdue, future = [], []
    for c in live:
        if not c["date"]:
            continue
        try:
            gap = (datetime.strptime(day, "%Y-%m-%d").date()
                   - datetime.strptime(c["date"], "%Y-%m-%d").date()).days
        except ValueError:
            continue
        if gap > 0:
            c = dict(c, gap=gap)
            overdue.append(c)
        elif gap < 0:
            c = dict(c, gap=-gap)
            future.append(c)
    return {
        "date": day,
        "today": [_public(c) for c in here],
        "overdue": [_public(c) for c in overdue],
        "future": [_public(c) for c in future],
    }


def _public(c: dict) -> dict:
    return {k: v for k, v in c.items() if k not in ("path", "raw")}


# ---------------------------------------------------------------- 写

def _slugify_auto(day: str, cards: list[dict]) -> str:
    mmdd = day.replace("-", "")[4:]
    n = 1
    used = {c["slug"] for c in cards}
    while f"d{mmdd}-{n}" in used:
        n += 1
    return f"d{mmdd}-{n}"


def _render(c: dict) -> str:
    reqs = "\n".join(f"- {x}" for x in c["reqs"]) or "- （待补）"
    crit = "\n".join(f"- [ ] {x}" for x in c["criteria"]) or "- [ ] （待补）"
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return f"""# {c['title']}

date: {c['date']}
status: {c['status']}
budget: {c['budget']}
spec: {c['spec']}
slug: {c['slug']}
created: {c.get('created') or now}
updated: {now}
origin: {c.get('origin') or 'web'}

## 一句话

{c.get('lede') or '（待补）'}

## 硬要求

{reqs}

## 完成判据

{crit}

## 备注

{c.get('notes') or ''}
""".rstrip() + "\n"


def create(title: str, lede: str = "", slug: str = "", budget: str = "full",
           spec: str = "", reqs: list[str] | None = None,
           criteria: list[str] | None = None, notes: str = "",
           want_date: str = "", origin: str = "web") -> dict:
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    cards = list_cards()
    want = want_date or date.today().isoformat()
    real_date, shifted = pick_date(want)

    slug = (slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        slug = _slugify_auto(real_date, cards)
    elif get(slug):
        raise ValueError(f"短名已被占用：{slug}")

    budget = budget if budget in BUDGETS else "full"
    card = {
        "title": title.strip() or "未命名任务",
        "slug": slug,
        "date": real_date,
        "status": "planned",
        "budget": budget,
        "spec": (spec or f"src/{slug}/PLAN.md").strip(),
        "lede": (lede or "").strip(),
        "reqs": [x.strip() for x in (reqs or []) if x.strip()],
        "criteria": [x.strip() for x in (criteria or []) if x.strip()],
        "notes": notes.strip(),
        "origin": origin,
        "created": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    path = CARDS_DIR / f"{real_date}-{slug}.md"
    path.write_text(_render(card), encoding="utf-8")
    card["path"] = path
    card["shifted"] = shifted
    card["wanted_date"] = want
    return card


def update(slug: str, **fields) -> dict:
    card = get(slug, include_archive=False)
    if not card:
        raise KeyError(slug)
    for key in ("title", "lede", "budget", "spec", "notes"):
        if key in fields and fields[key] is not None:
            card[key] = fields[key]
    for key in ("reqs", "criteria"):
        if key in fields and fields[key] is not None:
            card[key] = [x.strip() for x in fields[key] if x.strip()]
    if fields.get("date"):
        new_date, _ = pick_date(fields["date"], skip_slug=slug)
        card["date"] = new_date
    path: Path = card["path"]
    path.write_text(_render(card), encoding="utf-8")
    new_path = path.with_name(f"{card['date']}-{card['slug']}.md")
    if new_path != path:
        path.replace(new_path)
        card["path"] = new_path
    return card


def set_status(slug: str, status: str, note: str = "") -> dict:
    if status not in ALL_STATUS:
        raise ValueError(status)
    card = get(slug, include_archive=False)
    if not card:
        raise KeyError(slug)
    card["status"] = status
    text = _render(card)
    if status in CLOSED_STATUS:
        stamp = date.today().isoformat()
        text = text.rstrip() + f"\n\n---\n\n**结案 {stamp} · {status}**：{note}\n"
    card["path"].write_text(text, encoding="utf-8")
    if status in CLOSED_STATUS:
        ARCHIVE_DIR.mkdir(exist_ok=True)
        dest = ARCHIVE_DIR / card["path"].name
        shutil.move(str(card["path"]), str(dest))
        card["path"] = dest
    return card


def remove(slug: str) -> None:
    card = get(slug, include_archive=False)
    if not card:
        raise KeyError(slug)
    if card["status"] != "planned":
        raise PermissionError("只有「待做」的卡可以直接删除；执行中/明天收尾请先改状态")
    card["path"].unlink()


def stats() -> dict:
    cards = list_cards(include_archive=True)
    today = date.today().isoformat()
    opens = [c for c in cards if c["status"] in OPEN_STATUS]
    return {
        "total": len([c for c in cards if not c["archived"]]),
        "today": len([c for c in opens if c["date"] == today]),
        "planned": len([c for c in opens if c["status"] == "planned"]),
        "doing": len([c for c in opens if c["status"] == "doing"]),
        "carry": len([c for c in opens if c["status"] == "carry"]),
        "done": len([c for c in cards if c["status"] == "done"]),
        "slots_left_today": max(0, MAX_PER_DAY - _open_on(today)),
    }
