"""FRI urnik: javni seznam predmetov -> urniki predmetov -> JSON.

Uporaba:
  python scraper.py                      # vsi predmeti v aktivnem urniku
  python scraper.py --limit 3            # preizkus treh predmetov
  python scraper.py --html fixtures/primer_skupina.html  # brez spleta

Ne prijavlja študentov, ne spreminja podatkov na portalu.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Comment

BASE_URL = "https://urnik.fri.uni-lj.si/"
LOG = logging.getLogger("fri_scraper")
SUBJECT_RE = re.compile(r"^(.+?)\s*\(([0-9A-Za-z]+)\)\s*$")
HOVER_SUBJECT_RE = re.compile(r"^(.+?)\s*\(([0-9A-Za-z]+)\)_(P|LV|AV|LAB|SV|SE|V)$")
OCCUPANCY_RE = re.compile(r"\(\s*(\d+)\s*/\s*(\d+)\s*\)")


def get_param(href: str | None, key: str) -> str | None:
    if not href:
        return None
    return parse_qs(urlparse(href).query).get(key, [None])[0]


def get_text(node) -> str | None:
    return node.get_text(" ", strip=True) if node else None


def parse_subject_index(html: str, page_url: str) -> list[dict]:
    """Najde vse povezave `?subject=...` na začetni strani."""
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, dict] = {}
    for a in soup.select('a[href*="subject="]'):
        code = get_param(a.get("href"), "subject")
        if not code:
            continue
        label = get_text(a) or ""
        match = SUBJECT_RE.match(label)
        name = match.group(1).strip() if match and match.group(2) == code else label
        result[code] = {"sifra": code, "naziv": name, "url": urljoin(page_url, a["href"])}
    return sorted(result.values(), key=lambda item: (item["naziv"].casefold(), item["sifra"]))


def parse_allocations(html: str, fallback_subject: dict | None = None) -> list[dict]:
    """Razčleni `grid-entry`; `fallback_subject` uporabi le, ko ni oznake v hover."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for entry in soup.select(".grid-entry[data-allocation-id]"):
        allocation_id = entry.get("data-allocation-id")
        start = entry.get("data-start")
        day = entry.get("data-day")
        duration = entry.get("data-duration")
        if not (allocation_id and start and day and duration):
            LOG.warning("Nepopoln termin %s: preskakujem", allocation_id)
            continue
        try:
            # V HTML-ju je `data-duration` v urah (po videnih primerih celo število).
            hours = int(duration)
            end = (datetime.strptime(start, "%H:%M") + timedelta(hours=hours)).strftime("%H:%M")
        except ValueError:
            LOG.warning("Napačna ura/trajanje pri terminu %s", allocation_id)
            continue

        hover = entry.select_one(".entry-hover")
        hover_lines = [s.strip() for s in hover.stripped_strings] if hover else []
        subject_code = None
        subject_name = None
        for line in hover_lines:
            match = HOVER_SUBJECT_RE.fullmatch(line)
            if match:
                subject_name, subject_code = match.group(1).strip(), match.group(2)
                break
        if subject_code is None and fallback_subject:
            subject_code = fallback_subject["sifra"]
            subject_name = fallback_subject["naziv"]

        subject_link = entry.select_one("a.link-subject")
        classroom_link = entry.select_one("a.link-classroom")
        teacher_links = entry.select("a.link-teacher")
        groups = []
        seen_groups = set()
        for link in entry.select("a.link-group"):
            group_id = get_param(link.get("href"), "group")
            if group_id and group_id not in seen_groups:
                groups.append({"fri_group_id": group_id, "naziv": get_text(link)})
                seen_groups.add(group_id)

        occupied = capacity = None
        if hover:
            for comment in hover.find_all(string=lambda x: isinstance(x, Comment)):
                match = OCCUPANCY_RE.search(str(comment))
                if match:
                    occupied, capacity = int(match.group(1)), int(match.group(2))
                    break

        rows.append({
            "fri_allocation_id": allocation_id,
            "predmet_sifra": subject_code,
            "predmet_naziv": subject_name,
            "fri_activity_id": get_param(subject_link.get("href"), "activity") if subject_link else None,
            "tip": (get_text(entry.select_one(".entry-type")) or "").lstrip("| ").strip() or None,
            "dan": day,
            "zacetek": start,
            "konec": end,
            "trajanje_ur": hours,
            "ucilnica": get_text(classroom_link),
            "fri_ucilnica_id": get_param(classroom_link.get("href"), "classroom") if classroom_link else None,
            "izvajalci": [{"fri_teacher_id": get_param(a.get("href"), "teacher"), "ime": get_text(a)} for a in teacher_links],
            "zasedenost": occupied,
            "kapaciteta": capacity,
            "skupine": groups,
        })
    return rows


def merge_allocations(term_lists: list[list[dict]]) -> list[dict]:
    """Odstrani ponovitve istega FRI termina; ohrani vse povezane skupine."""
    merged: dict[str, dict] = {}
    for terms in term_lists:
        for t in terms:
            key = t["fri_allocation_id"]
            if key not in merged:
                merged[key] = t
                continue
            old = merged[key]
            old_groups = {g["fri_group_id"] for g in old["skupine"]}
            old["skupine"].extend(g for g in t["skupine"] if g["fri_group_id"] not in old_groups)
            for field in ("predmet_sifra", "predmet_naziv", "zasedenost", "kapaciteta"):
                if old[field] is None:
                    old[field] = t[field]
    return sorted(merged.values(), key=lambda x: (x["dan"], x["zacetek"], x["fri_allocation_id"]))


def get_html(client: httpx.Client, url: str) -> tuple[str, str]:
    response = client.get(url)
    response.raise_for_status()
    if "html" not in response.headers.get("content-type", "").lower():
        raise ValueError(f"Odgovor ni HTML: {response.url}")
    return response.text, str(response.url)


def scrape_all(limit: int | None = None, delay: float = 0.5) -> dict:
    headers = {"User-Agent": "FRI-urnik-student-project/0.1 (educational, low-rate)"}
    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        homepage_html, homepage_url = get_html(client, BASE_URL)
        subjects = parse_subject_index(homepage_html, homepage_url)
        if not subjects:
            raise RuntimeError("Na začetni strani ni povezav do predmetov. Preveri HTML in URL portala.")
        if limit is not None:
            subjects = subjects[:limit]
        term_lists = []
        failures = []
        for index, subject in enumerate(subjects, start=1):
            LOG.info("[%d/%d] %s (%s)", index, len(subjects), subject["naziv"], subject["sifra"])
            try:
                html, _ = get_html(client, subject["url"])
                term_lists.append(parse_allocations(html, fallback_subject=subject))
            except (httpx.HTTPError, ValueError) as exc:
                LOG.error("Napaka pri predmetu %s: %s", subject["sifra"], exc)
                failures.append({"sifra": subject["sifra"], "napaka": str(exc)})
            if index < len(subjects):
                time.sleep(delay)
        if not term_lists:
            raise RuntimeError("Nobenega urnika ni bilo mogoče prenesti.")
        return {
            "vir": homepage_url,
            "pridobljeno_utc": datetime.now(timezone.utc).isoformat(),
            "nepopolno": bool(failures) or limit is not None,
            "napake": failures,
            "predmeti": subjects,
            "termini": merge_allocations(term_lists),
        }


def main():
    parser = argparse.ArgumentParser(description="FRI scraper -> JSON")
    parser.add_argument("--limit", type=int, default=None, help="Prenesi največ N predmetov (test)")
    parser.add_argument("--delay", type=float, default=0.5, help="Premor med zahtevami, v sekundah")
    parser.add_argument("--html", type=Path, help="Preizkusi parser z lokalno HTML-datoteko")
    parser.add_argument("--output", type=Path, default=Path("fri_urnik.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit mora biti vsaj 1")
    if args.delay < 0:
        parser.error("--delay ne sme biti negativen")

    if args.html:
        terms = parse_allocations(args.html.read_text(encoding="utf-8"))
        data = {"vir": str(args.html), "pridobljeno_utc": datetime.now(timezone.utc).isoformat(),
                "nepopolno": False, "napake": [], "predmeti": [], "termini": merge_allocations([terms])}
    else:
        data = scrape_all(limit=args.limit, delay=args.delay)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Shranjeno: {args.output} | predmeti: {len(data['predmeti'])} | termini: {len(data['termini'])} | napake: {len(data['napake'])}")


if __name__ == "__main__":
    main()
