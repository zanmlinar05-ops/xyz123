"""Uvoz uradnega FRI urnika študenta, ko študent poda vpisno številko.

To NI optimizirani urnik. Neprepoznanih ID-jev ne dodajamo avtomatsko.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from urllib.parse import urljoin
import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .db import engine_from_env
from .models import Dodelitev, Semester, Student, Termin
from .scraper import parse_allocations


def parse_student_html(html: str) -> set[str]:
    return {str(t["fri_allocation_id"]) for t in parse_allocations(html)}


def fetch_student_ids(student_number: str, semester: Semester) -> set[str]:
    if not student_number.isdigit() or len(student_number) > 32:
        raise ValueError("Neveljavna vpisna številka")
    
    url = urljoin(
        semester.vir.rstrip("/") + "/", "allocations")
    
    with httpx.Client(timeout=25, follow_redirects=True) as client:

        response = client.get(
            url, 
            params={"student": student_number}
            )
        response.raise_for_status()
        
        if "html" not in response.headers.get("content-type", "").lower():
            raise ValueError("FRI ni vrnil HTML-ja")
        return parse_student_html(response.text)


def import_student_allocations(session: Session, semester_slug: str, student_number: str, ids: set[str]) -> dict:
    semester = session.scalar(select(Semester).where(Semester.slug == semester_slug))
    if semester is None:
        raise ValueError(f"Semester {semester_slug} ni v bazi")
    terms = {t.fri_allocation_id: t for t in session.scalars(select(Termin).where(
        Termin.semester_id == semester.id, Termin.fri_allocation_id.in_(ids)))} if ids else {}
    missing = sorted(ids - set(terms))
    if missing:
        raise ValueError(f"Manjkajoči globalni termini: {missing}. Najprej osveži globalni scraper.")
    student = session.scalar(select(Student).where(Student.vpisna_stevilka == student_number))
    if student is None:
        student = Student(vpisna_stevilka=student_number)
        session.add(student)
        session.flush()
    # Menjamo samo dodelitve za izbrani semester; drugi ostanejo.
    existing = session.scalars(select(Dodelitev).join(Termin).where(
        Dodelitev.student_id == student.id, Termin.semester_id == semester.id)).all()
    existing_ids = {d.termin_id for d in existing}
    new_ids = {term.id for term in terms.values()}
    for old in existing:
        if old.termin_id not in new_ids:
            session.delete(old)
    for term_id in new_ids - existing_ids:
        session.add(Dodelitev(student_id=student.id, termin_id=term_id))
    student.zadnji_uvoz = datetime.now(timezone.utc)
    return {"student_id": student.id, "semester": semester_slug, "dodelitve": len(ids)}

def uvozi_urnik_studenta(session: Session, vpisna_stevilka: str, semester_slug: str) -> dict:
    # 1. Preverimo vpisno številko.
    if not vpisna_stevilka.isdigit():
        raise ValueError("Neveljavna vpisna številka.")

    # 2. Poiščemo semester.
    semester = session.scalar(
        select(Semester).where(
            Semester.slug == semester_slug
        )
    )

    if semester is None:
        raise ValueError("Semester ne obstaja.")

    # 3. Pridobimo ID-je terminov s FRI.
    ids = fetch_student_ids(
        vpisna_stevilka,
        semester
    )
    print("Število najdenih terminov:", len(ids))
    print("FRI ID-ji:", sorted(ids))

    # 4. Preverimo, ali smo dobili termine.
    if not ids:
        raise ValueError(
            "Za študenta ni bilo najdenih terminov. "
            "Uvoz je prekinjen."
        )

    # 5. Podatke shranimo v PostgreSQL.
    rezultat = import_student_allocations(
        session=session,
        semester_slug=semester_slug,
        student_number=vpisna_stevilka,
        ids=ids
    )

    return rezultat

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("semester_slug", help="npr. fri-2026_2027-zimski")
    parser.add_argument("vpisna", help="Uporabi samo svojo številko oziroma z dovoljenjem študenta")
    args = parser.parse_args()
    engine = engine_from_env()
    with Session(engine) as session:
        semester = session.scalar(select(Semester).where(Semester.slug == args.semester_slug))
        if semester is None:
            raise SystemExit("Semester ne obstaja v bazi")
        ids = fetch_student_ids(args.vpisna, semester)
        if not ids:
            raise SystemExit("Ni najdenih terminov; uvoz je zaustavljen, da ne izbriše dodelitev")
        with session.begin_nested():
            result = import_student_allocations(session, args.semester_slug, args.vpisna, ids)
        session.commit()
    print(result)


if __name__ == "__main__":
    main()
