from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine_from_env
from app.models import Sinhronizacija, Semester
from app.scraper import scrape_all
from app.import_json import import_data

from urllib.parse import urlparse

import httpx

from app.scraper import BASE_URL, scrape_all
from app.import_json import SLUG_PATTERN, import_data


def pridobi_semester_slug(url: str) -> str:

    pot = urlparse(url).path.strip("/")

    deli = pot.split("/")

    if len(deli) < 2 or deli[0] != "timetable":
        raise ValueError("Neveljaven URL semestra.")

    return deli[1]


def pridobi_aktualni_semester() -> str:

    with httpx.Client(
        timeout=25,
        follow_redirects=True
    ) as client:

        response = client.get(BASE_URL)
        response.raise_for_status()

        pot = response.url.path.strip("/").split("/")

        if len(pot) != 2 or pot[0] != "timetable":
            raise ValueError("FRI ni vrnil URL-ja semestra.")

        slug = pot[1]

        if SLUG_PATTERN.fullmatch(slug) is None:
            raise ValueError(f"Neznana oznaka semestra: {slug}")

        return slug


def pridobi_zadnjo_osvezitev(
    session: Session,
    semester_id: int,
    vrsta: str
) -> datetime | None:

    stmt = select(Sinhronizacija).where(
        Sinhronizacija.semester_id == semester_id,
        Sinhronizacija.tip == vrsta
    )

    sinhronizacija = session.scalar(stmt)

    if sinhronizacija is None:
        return None

    return sinhronizacija.zadnja_uspesna

def potrebuje_osvezitev(zadnja_uspesna, interval_dni):
    if zadnja_uspesna is None:
        return True

    zdaj = datetime.now(timezone.utc)

    if zadnja_uspesna.tzinfo is None:
        zadnja_uspesna = zadnja_uspesna.replace(
            tzinfo=timezone.utc
        )

    naslednja_osvezitev = zadnja_uspesna + timedelta(
        days=interval_dni
    )

    return zdaj >= naslednja_osvezitev

def preveri_osvezitve(
    session: Session,
    semester_slug: str
) -> dict:

    semester = session.scalar(
        select(Semester).where(
            Semester.slug == semester_slug
        )
    )

    if semester is None:
        return {
            "predmeti": True,
            "termini": True
        }

    zadnji_predmeti = pridobi_zadnjo_osvezitev(
        session,
        semester.id,
        "predmeti"
    )

    zadnji_termini = pridobi_zadnjo_osvezitev(
        session,
        semester.id,
        "termini"
    )

    return {
        "predmeti": potrebuje_osvezitev(zadnji_predmeti, 30),
        "termini": potrebuje_osvezitev(zadnji_termini, 1)
    }


def izvedi_osvezitev(session: Session, force: bool = False):

    # 1. Samodejno pridobimo aktualni semester.
    semester_slug = pridobi_aktualni_semester()

    print("Aktualni semester:", semester_slug)

    # 2. Preverimo, ali je potrebna osvežitev.
    stanje = preveri_osvezitve(session, semester_slug)

    if not force and not stanje["predmeti"] and not stanje["termini"]:
        print("Podatki so že posodobljeni.")
        return None

    # 3. Pridobimo podatke s FRI.
    print("Pridobivam podatke s FRI ...")

    podatki = scrape_all()

    # 4. Osnovno preverjanje.
    if podatki.get("nepopolno") or podatki.get("napake"):
        raise RuntimeError("Prenos podatkov ni uspel.")

    if not podatki.get("predmeti") or not podatki.get("termini"):
        raise RuntimeError("Scraper je vrnil prazne podatke.")

    # 5. Preverimo, da scraper ni prešel na drug semester.
    if SLUG_PATTERN.search(podatki["vir"]).group(0) != semester_slug:
        raise RuntimeError("Semester se je med prenosom spremenil.")

    # 6. Shranimo podatke v PostgreSQL.
    rezultat = import_data(session, podatki)

    return rezultat

def main():

    engine = engine_from_env()

    with Session(engine) as session:
        with session.begin():
            rezultat = izvedi_osvezitev(session)

    if rezultat is not None:
        print("Sinhronizacija uspešna!")
        print(rezultat)


if __name__ == "__main__":
    main()