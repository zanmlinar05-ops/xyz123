import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def engine_from_env():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Nastavi DATABASE_URL (npr. postgresql+psycopg://mojurnik:mojurnik@localhost:5432/mojurnik)")
    return create_engine(url, pool_pre_ping=True)


def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
