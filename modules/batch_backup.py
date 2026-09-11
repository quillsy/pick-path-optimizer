import os

def read_batch_backup(file_path: str) -> bytes:
    """Reads the specified file entirely in binary mode and returns its bytes."""
    with open(file_path, "rb") as f:
        return f.read()
