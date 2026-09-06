from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().master_key.encode())


def encrypt_secret(plain_text: str) -> str:
    return _fernet().encrypt(plain_text.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def mask_secret(plain_text: str, visible_suffix: int = 4) -> str:
    if len(plain_text) <= visible_suffix:
        return "*" * len(plain_text)
    return "*" * (len(plain_text) - visible_suffix) + plain_text[-visible_suffix:]
