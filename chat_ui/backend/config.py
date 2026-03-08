import sys
from pathlib import Path

# Ensure shared modules (webhook/) are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEBHOOK_DIR = str(PROJECT_ROOT / "webhook")
if WEBHOOK_DIR not in sys.path:
    sys.path.insert(0, WEBHOOK_DIR)

from database import ConfigStore

_store = ConfigStore()


def get_litellm_base_url() -> str:
    return _store.get("litellm_base_url", "http://localhost:4000/v1")


def get_litellm_model() -> str:
    return _store.get("litellm_model", "gpt-4o")


def get_litellm_api_key() -> str:
    return _store.get("litellm_api_key", "sk-placeholder")
