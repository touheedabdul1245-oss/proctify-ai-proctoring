"""Username derivation / uniquification helpers.

Usernames are the primary login identity (replacing email). They are derived
from the email local-part when not supplied explicitly, so they are always
meaningful (never random), e.g. ``admin@proctify.dev`` -> ``admin``,
``john.doe@example.com`` -> ``john.doe``. Collisions get a numeric suffix.
"""
import re

USERNAME_RE = r"^[a-z0-9._-]{1,64}$"

_SANITIZE_RE = re.compile(r"[^a-z0-9._-]")


def slugify_email(email: str) -> str:
    """Derive a meaningful username slug from an email address."""
    local = (email or "").split("@")[0].lower().strip()
    slug = _SANITIZE_RE.sub("", local)
    slug = slug.strip("._-")[:64]
    if not slug:
        slug = "user" + str(abs(sum(map(ord, local))) % 100000)
    return slug


def unique_username(db, base: str) -> str:
    """Return ``base`` if free, otherwise ``base`` + numeric suffix.

    ``db`` is a SQLAlchemy Session; uniqueness is case-insensitive.
    """
    from .models import User

    taken = {
        row[0].lower()
        for row in db.query(User.username).all()
        if row[0]
    }
    candidate = base
    i = 2
    while candidate.lower() in taken:
        candidate = f"{base}{i}"
        i += 1
    return candidate