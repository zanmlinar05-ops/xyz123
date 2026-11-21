"""Idempotentni uvoz globalnega JSON-a v PostgreSQL/SQLite (za testiranje)."""
from __future__ import annotations
import argparse
import json
import re
from datetime import datetime, time, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import engine_from_env
from .models import (
    Semester, Predmet, Termin, Skupina, Izvajalec, TerminSkupina,
    TerminIzvajalec, Sinhronizacija
)

SLUG_PATTERN = re.compile(r"fri-(\d{4})_(\d{4})-(zimski|poletni)")


def import_data(session: Session, data: dict) -> dict:
    if data.get("nepopolno") or data.get("napake"):
        raise ValueError("Uvoz preklican: scraper poroča o nepopolnem prenosu ali napakah.")
    match = SLUG_PATTERN.search(data.get("vir", ""))
    if not match:
        raise ValueError("Ni mogoče razbrati semestra iz polja 'vir'.")
    slug = match.group(0)
    semester = session.scalar(select(Semester).where(Semester.slug == slug))
    if semester is None:
        semester = Semester(slug=slug, leto=f"{match[1]}/{match[2]}", obdobje=match[3], vir=data['vir'])
        session.add(semester)
        session.flush()

    subject_rows = data["predmeti"]
    term_rows = data["termini"]
    if not subject_rows or not term_rows:
        raise ValueError("Uvoz preklican: prazen seznam predmetov ali terminov.")

    subjects = {x.sifra: x for x in session.scalars(select(Predmet).where(Predmet.semester_id == semester.id))}
    groups = {x.fri_group_id: x for x in session.scalars(select(Skupina).where(Skupina.semester_id == semester.id))}
    teachers = {x.fri_teacher_id: x for x in session.scalars(select(Izvajalec))}
    terms = {x.fri_allocation_id: x for x in session.scalars(select(Termin).where(Termin.semester_id == semester.id))}

    # Mark inactive only after verifying this is a complete snapshot.
    for p in subjects.values():
        p.aktiven = False
    for t in terms.values():
        t.aktiven = False

    for p in subject_rows:
        code = str(p["sifra"])
        obj = subjects.get(code)
        if obj is None:
            obj = Predmet(semester_id=semester.id, sifra=code, naziv=p["naziv"])
            session.add(obj)
            subjects[code] = obj
        obj.naziv, obj.url, obj.aktiven = p["naziv"], p.get("url"), True
    session.flush()

    seen_ids = set()
    for t in term_rows:
        aid = str(t["fri_allocation_id"])
        if aid in seen_ids:
            raise ValueError(f"Podvojen ID termina v JSON: {aid}")
        seen_ids.add(aid)
        pcode = str(t["predmet_sifra"])
        if pcode not in subjects:
            raise ValueError(f"Termin {aid} kaže na neznan predmet {pcode}")
        obj = terms.get(aid)
        if obj is None:
            obj = Termin(semester_id=semester.id, predmet_id=subjects[pcode].id,
                         fri_allocation_id=aid, tip=t["tip"], dan=t["dan"],
                         zacetek=time.fromisoformat(t["zacetek"]), konec=time.fromisoformat(t["konec"]))
            session.add(obj)
            terms[aid] = obj
        obj.predmet_id = subjects[pcode].id
        obj.fri_activity_id = t.get("fri_activity_id")
        obj.tip, obj.dan = t["tip"], t["dan"]
        obj.zacetek, obj.konec = time.fromisoformat(t["zacetek"]), time.fromisoformat(t["konec"])
        obj.ucilnica, obj.fri_ucilnica_id = t.get("ucilnica"), t.get("fri_ucilnica_id")
        obj.zasedenost, obj.kapaciteta = t.get("zasedenost"), t.get("kapaciteta")
        obj.aktiven = True
        obj.zadnja_osvezitev = datetime.now(timezone.utc)

        active_groups = []
        for g in t.get("skupine", []):
            gid = str(g["fri_group_id"])
            group = groups.get(gid)
            if group is None:
                group = Skupina(semester_id=semester.id, fri_group_id=gid, naziv=g["naziv"])
                session.add(group)
                groups[gid] = group
            group.naziv = g["naziv"]
            active_groups.append(group)
        active_teachers = []
        for te in t.get("izvajalci", []):
            tid = str(te["fri_teacher_id"])
            teacher = teachers.get(tid)
            if teacher is None:
                teacher = Izvajalec(fri_teacher_id=tid, ime=te["ime"])
                session.add(teacher)
                teachers[tid] = teacher
            teacher.ime = te["ime"]
            active_teachers.append(teacher)
        obj.skupine = list({g.fri_group_id: g for g in active_groups}.values())
        obj.izvajalci = list({te.fri_teacher_id: te for te in active_teachers}.values())

    # Record distinct successful import types: subject list and allocations.
    for kind in ("predmeti", "termini"):
        sync = session.scalar(select(Sinhronizacija).where(
            Sinhronizacija.semester_id == semester.id, Sinhronizacija.tip == kind))
        if sync is None:
            sync = Sinhronizacija(semester_id=semester.id, tip=kind)
            session.add(sync)
        sync.zadnja_uspesna = datetime.now(timezone.utc)
    session.flush()
    return {"semester": slug, "predmeti": len(subject_rows), "termini": len(term_rows),
            "skupine": len(groups), "izvajalci": len(teachers)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="Pot do globalnega JSON-a")
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    engine = engine_from_env()
    with Session(engine) as session, session.begin():
        result = import_data(session, data)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
