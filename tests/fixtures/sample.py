"""Roast service — dispatches AI roast requests and caches results."""

import os

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30
CACHE_TTL = 3600


class RoastService:
    """Handles roast generation via Vertex AI."""

    def __init__(self, client):
        self.client = client

    def generate_roast(self, image_path: str) -> str:
        return ""

    def get_cached(self, key: str):
        return None

    def _build_prompt(self, persona: str) -> str:
        return ""


class CacheService:
    """Simple in-memory cache."""

    def get(self, key: str):
        return None

    def set(self, key: str, value) -> None:
        pass


def build_index(paths: list) -> dict:
    return {}


def normalize_path(path: str) -> str:
    return os.path.realpath(path)
