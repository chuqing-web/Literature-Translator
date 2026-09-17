from __future__ import annotations

from cryptography.fernet import Fernet

from app.config import settings


def _load_fernet() -> Fernet:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = settings.secret_key_path
    if path.exists():
        key = path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        path.write_bytes(key)
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    return _load_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    return _load_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
