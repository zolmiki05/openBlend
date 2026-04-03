"""
Reads users_config.json and provisions any missing users on startup.
If a user already exists, it is left untouched.
New users get a random temporary password written to the reset log.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.services.auth import generate_temp_password, hash_password


def provision():
    config_path = settings.users_config_path
    if not os.path.exists(config_path):
        print(f"[provision] No config file found at {config_path}, skipping.")
        return

    with open(config_path) as f:
        config = json.load(f)

    users_cfg = config.get("users", [])
    if not users_cfg:
        print("[provision] No users defined in config, skipping.")
        return

    log_path = settings.password_reset_log_path
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    db = SessionLocal()
    try:
        for user_cfg in users_cfg:
            username = user_cfg["username"]
            platform = user_cfg["platform"]

            existing = db.query(User).filter(User.username == username).first()
            if existing:
                print(f"[provision] User '{username}' already exists, skipping.")
                continue

            temp_password = generate_temp_password()
            user = User(
                username=username,
                password_hash=hash_password(temp_password),
                is_temp_password=True,
                platform=platform,
            )
            db.add(user)
            db.commit()

            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).isoformat()
            with open(log_path, "a") as log:
                log.write(f"{timestamp} | {username} | {temp_password} | [initial]\n")

            print(f"[provision] Created user '{username}' (platform: {platform}). "
                  f"Temp password written to {log_path}")
    finally:
        db.close()


if __name__ == "__main__":
    provision()
