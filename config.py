"""Local application settings. Never commit real secrets."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
database_path = Path(os.getenv("STUDYHUB_DB", str(BASE_DIR / "studyhub.db")))
secret_key = os.getenv("STUDYHUB_SECRET_KEY") or secrets.token_hex(32)
secure_cookies = os.getenv("STUDYHUB_HTTPS") == "1"
