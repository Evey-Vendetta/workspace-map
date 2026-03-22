"""Task service — dispatches AI task requests and caches results."""

import os

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30
CACHE_TTL = 3600


class TaskService:
    """Handles task generation via LLM."""

    def __init__(self, client):
        self.client = client

    def run_task(self, image_path: str) -> str:
        return ""

    def get_cached(self, key: str):
        return None

    def _build_prompt(self, template: str) -> str:
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
