"""Instance settings: GitHub App credentials and the docs repository."""

from ohara import db


def load() -> dict:
    return db.all("settings")


def save(settings: dict) -> None:
    with db.connect() as conn:
        db.delete_kind("settings", conn)
        for key, value in settings.items():
            db.put("settings", key, value, conn=conn)


def update(**values: object) -> dict:
    with db.connect() as conn:
        for key, value in values.items():
            db.put("settings", key, value, conn=conn)
    return load()


def configured(settings: dict | None = None) -> bool:
    settings = load() if settings is None else settings
    return bool(settings.get("app") and settings.get("repo"))
