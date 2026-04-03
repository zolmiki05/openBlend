import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.auth import generate_temp_password, hash_password, verify_password


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def change_user_password(db: Session, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.is_temp_password = False
    db.commit()


def reset_user_password(db: Session, username: str, log_path: str) -> str | None:
    """Generate a new temp password for the user and write it to the reset log."""
    user = get_user_by_username(db, username)
    if not user:
        return None

    temp_password = generate_temp_password()
    user.password_hash = hash_password(temp_password)
    user.is_temp_password = True
    db.commit()

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(log_path, "a") as f:
        f.write(f"{timestamp} | {username} | {temp_password}\n")

    return temp_password
