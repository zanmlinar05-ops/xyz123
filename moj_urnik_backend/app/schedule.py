from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Semester,
    Predmet,
    Termin,
    Dodelitev,
    Student
)

def get_student_schedule(
    session: Session,
    student_id: int,
    semester_slug: str
) -> dict:

    # 1. Poiščemo študenta.
    student = session.get(Student, student_id)

    if student is None:
        raise ValueError("Študent ne obstaja.")

    # 2. Poiščemo semester.
    semester = session.scalar(
        select(Semester).where(
            Semester.slug == semester_slug
        )
    )

    if semester is None:
        raise ValueError("Semester ne obstaja.")

    # 3. Pridobimo študentove termine.
    stmt = (
        select(Termin, Predmet)
        .join(
            Dodelitev,
            Dodelitev.termin_id == Termin.id
        )
        .join(
            Predmet,
            Termin.predmet_id == Predmet.id
        )
        .where(
            Dodelitev.student_id == student_id,
            Termin.semester_id == semester.id
        )
        .options(
            selectinload(Termin.skupine)
        )
        .order_by(
            Termin.dan,
            Termin.zacetek
        )
    )

    rezultati = session.execute(stmt).all()

    # 4. Pretvorimo rezultate v slovarje.
    termini = []

    for termin, predmet in rezultati:

        termini.append({
            "termin_id": termin.id,
            "fri_allocation_id": termin.fri_allocation_id,
            "predmet_id": predmet.id,
            "predmet_sifra": predmet.sifra,
            "predmet_naziv": predmet.naziv,
            "tip": termin.tip,
            "dan": termin.dan,
            "zacetek": termin.zacetek.strftime("%H:%M"),
            "konec": termin.konec.strftime("%H:%M"),
            "ucilnica": termin.ucilnica,
            "skupine": [
                skupina.naziv
                for skupina in termin.skupine
            ],
            "kapaciteta": termin.kapaciteta,
            "zasedenost": termin.zasedenost
        })

    # 5. Vrnemo celoten urnik.
    return {
        "student_id": student.id,
        "semester": semester.slug,
        "stevilo_terminov": len(termini),
        "stevilo_predmetov": len({
            termin["predmet_id"]
            for termin in termini
        }),
        "termini": termini
    }