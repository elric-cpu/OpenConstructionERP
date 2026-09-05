from pathlib import PurePosixPath


def validate_object_key(key: str) -> str:
    if (
        not key
        or key.startswith(("/", "\\"))
        or "\\" in key
        or "\x00" in key
        or "//" in key
    ):
        raise ValueError("Invalid storage key")
    path = PurePosixPath(key)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Invalid storage key")
    return key
