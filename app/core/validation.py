import re

from fastapi import HTTPException, status


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email address")
    return email


def validate_choice(value: str, allowed: set[str], field_name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name}; expected one of: {allowed_values}")
    return normalized
