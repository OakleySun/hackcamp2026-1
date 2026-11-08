import os

from dotenv import load_dotenv

load_dotenv()


def get(name: str, default: str = "") -> str:
    """Read settings at call time so tests can override environment variables."""
    return os.environ.get(name, default)
