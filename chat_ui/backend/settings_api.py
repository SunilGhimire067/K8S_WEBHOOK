import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import require_auth

logger = logging.getLogger("settings-api")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEBHOOK_DIR = str(PROJECT_ROOT / "webhook")
if WEBHOOK_DIR not in sys.path:
    sys.path.insert(0, WEBHOOK_DIR)

from database import ConfigStore

_store = ConfigStore()

router = APIRouter(
    prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_auth)]
)

# Keys exposed via the settings API
LLM_KEYS = ["litellm_base_url", "litellm_model", "litellm_api_key"]


@router.get("")
async def get_settings():
    return {key: _store.get(key, "") for key in LLM_KEYS}


class UpdateSettingsRequest(BaseModel):
    litellm_base_url: str | None = None
    litellm_model: str | None = None
    litellm_api_key: str | None = None


@router.put("")
async def update_settings(body: UpdateSettingsRequest):
    updated = []
    for key in LLM_KEYS:
        value = getattr(body, key)
        if value is not None:
            _store.set(key, value)
            updated.append(key)
    return {"updated": updated}
