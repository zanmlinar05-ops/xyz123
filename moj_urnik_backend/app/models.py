"""MojUrnik: modeli, ločeni po semestru. FRI ID je izvorni identifikator."""
from __future__ import annotations
from datetime import datetime, timezone, time
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Integer, PrimaryKeyConstraint, String, Text, Time, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Semester(Base):
    __tablename__ = "semester"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    leto: Mapped[str] = mapped_column(String(9), nullable=False)
    obdobje: Mapped[str] = mapped_column(String(20), nullable=False)
    vir: Mapped[str] = mapped_column(Text, nullable=False)
    predmeti: Mapped[list[Predmet]] = relationship(back_populates="semester")


class Predmet(Base):
    __tablename__ = "predmet"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semester.id"), nullable=False)
    sifra: Mapped[str] = mapped_column(String(32), nullable=False)
    naziv: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    aktiven: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    semester: Mapped[Semester] = relationship(back_populates="predmeti")
    __table_args__ = (UniqueConstraint("semester_id", "sifra", name="uq_predmet_sem_sifra"),)


class Skupina(Base):
    __tablename__ = "skupina"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semester.id"), nullable=False)
    fri_group_id: Mapped[str] = mapped_column(String(32), nullable=False)
    naziv: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("semester_id", "fri_group_id", name="uq_skupina_sem_fri"),)


class Izvajalec(Base):
    __tablename__ = "izvajalec"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fri_teacher_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    ime: Mapped[str] = mapped_column(Text, nullable=False)


class Termin(Base):
    __tablename__ = "termin"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semester.id"), nullable=False)
    predmet_id: Mapped[int] = mapped_column(ForeignKey("predmet.id"), nullable=False)
    fri_allocation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    fri_activity_id: Mapped[str | None] = mapped_column(String(32))
    tip: Mapped[str] = mapped_column(String(12), nullable=False)
    dan: Mapped[str] = mapped_column(String(3), nullable=False)
    zacetek: Mapped[time] = mapped_column(Time, nullable=False)
    konec: Mapped[time] = mapped_column(Time, nullable=False)
    ucilnica: Mapped[str | None] = mapped_column(String(50))
    fri_ucilnica_id: Mapped[str | None] = mapped_column(String(32))
    zasedenost: Mapped[int | None] = mapped_column(Integer)
    kapaciteta: Mapped[int | None] = mapped_column(Integer)
    aktiven: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    zadnja_osvezitev: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    skupine: Mapped[list[Skupina]] = relationship(secondary="termin_skupina")
    izvajalci: Mapped[list[Izvajalec]] = relationship(secondary="termin_izvajalec")
    __table_args__ = (
        UniqueConstraint("semester_id", "fri_allocation_id", name="uq_termin_sem_fri"),
        CheckConstraint("kapaciteta IS NULL OR kapaciteta >= 0", name="ck_kapaciteta"),
        CheckConstraint("zasedenost IS NULL OR zasedenost >= 0", name="ck_zasedenost"),
    )


class TerminSkupina(Base):
    __tablename__ = "termin_skupina"
    termin_id: Mapped[int] = mapped_column(ForeignKey("termin.id", ondelete="CASCADE"), primary_key=True)
    skupina_id: Mapped[int] = mapped_column(ForeignKey("skupina.id", ondelete="CASCADE"), primary_key=True)


class TerminIzvajalec(Base):
    __tablename__ = "termin_izvajalec"
    termin_id: Mapped[int] = mapped_column(ForeignKey("termin.id", ondelete="CASCADE"), primary_key=True)
    izvajalec_id: Mapped[int] = mapped_column(ForeignKey("izvajalec.id", ondelete="CASCADE"), primary_key=True)


class Student(Base):
    __tablename__ = "student"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vpisna_stevilka: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # Povezavo z računom v FastAPI Users določi član ekipe za avtentikacijo.
    zadnji_uvoz: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Dodelitev(Base):
    """Uradna FRI dodelitev, ne izbrani/optimizirani termin v aplikaciji."""
    __tablename__ = "dodelitev"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    termin_id: Mapped[int] = mapped_column(ForeignKey("termin.id"), nullable=False)
    __table_args__ = (UniqueConstraint("student_id", "termin_id", name="uq_dodelitev_student_termin"),)


class Zaklep(Base):
    """Obvezen termin: globalen (student_id NULL) ali vezan na študenta."""
    __tablename__ = "zaklep"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    termin_id: Mapped[int] = mapped_column(ForeignKey("termin.id"), nullable=False)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("student.id"))
    razlog: Mapped[str | None] = mapped_column(Text)
    ustvarjen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Sinhronizacija(Base):
    __tablename__ = "sinhronizacija"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semester.id"), nullable=False)
    tip: Mapped[str] = mapped_column(String(30), nullable=False)
    zadnja_uspesna: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("semester_id", "tip", name="uq_sync_sem_tip"),)
