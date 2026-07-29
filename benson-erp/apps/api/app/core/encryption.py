from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def encrypt_secret(value: str) -> str:
    return Fernet(settings.encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return Fernet(settings.encryption_key.encode()).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Encrypted value could not be decrypted") from exc
