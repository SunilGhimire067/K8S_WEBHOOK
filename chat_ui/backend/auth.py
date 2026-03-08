import base64
import io
import secrets
import sys
from pathlib import Path

import bcrypt
import pyotp
import qrcode
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

# Ensure shared modules (webhook/) are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEBHOOK_DIR = str(PROJECT_ROOT / "webhook")
if WEBHOOK_DIR not in sys.path:
    sys.path.insert(0, WEBHOOK_DIR)

from database import (
    create_session,
    delete_session,
    get_session,
    get_user,
    update_user_totp,
)

APP_NAME = "Sentinel K8s"

# In-memory pending secret for TOTP setup flow (not persisted until verified)
_pending_secrets: dict[str, str] = {}  # temp_token -> pending_totp_secret

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _generate_qr_base64(uri: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ── Request / Response models ──

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    temp_token: str
    requires_totp: bool = True
    setup_required: bool = False
    qr_image: str | None = None   # base64 PNG — only on first-time setup
    secret: str | None = None     # plain-text key for manual Authenticator entry


class VerifyTotpRequest(BaseModel):
    temp_token: str
    code: str


class VerifyTotpResponse(BaseModel):
    token: str


# ── Endpoints ──

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    # Look up user in DB
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password with bcrypt
    if not bcrypt.checkpw(req.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    verified_secret = user.get("totp_secret")
    setup_required = not verified_secret

    # Create a temporary session (5 min TTL) for the TOTP verification step
    temp_token = secrets.token_hex(32)
    create_session(temp_token, req.username, is_temp=True, ttl_seconds=300)

    if setup_required:
        # Generate a fresh pending secret; store keyed by temp_token
        pending = pyotp.random_base32()
        _pending_secrets[temp_token] = pending
        totp = pyotp.TOTP(pending)
        uri = totp.provisioning_uri(name=req.username, issuer_name=APP_NAME)
        qr_image = _generate_qr_base64(uri)
        return LoginResponse(
            temp_token=temp_token,
            requires_totp=True,
            setup_required=True,
            qr_image=qr_image,
            secret=pending,
        )

    return LoginResponse(
        temp_token=temp_token,
        requires_totp=True,
        setup_required=False,
    )


@router.post("/verify-totp", response_model=VerifyTotpResponse)
async def verify_totp(req: VerifyTotpRequest):
    # Validate temp session from DB
    session = get_session(req.temp_token, temp_only=True)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    username = session["username"]
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Determine which TOTP secret to verify against
    verified_secret = user.get("totp_secret")
    pending = _pending_secrets.get(req.temp_token)
    secret = verified_secret or pending
    if not secret:
        raise HTTPException(status_code=500, detail="TOTP not configured")

    totp = pyotp.TOTP(secret)
    # valid_window=1 accepts codes from ±30 seconds to tolerate clock skew
    if not totp.verify(req.code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid authenticator code")

    # First-time setup: persist the verified TOTP secret to DB
    if not verified_secret and pending:
        update_user_totp(username, pending)
        _pending_secrets.pop(req.temp_token, None)

    # Delete the temp session
    delete_session(req.temp_token)

    # Create a full session (24h TTL)
    token = secrets.token_hex(32)
    create_session(token, username, is_temp=False, ttl_seconds=86400)
    return VerifyTotpResponse(token=token)


def require_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = auth[7:]
    # Validate against sessions table (non-temp, not expired)
    session = get_session(token, temp_only=False)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid auth token")
    return token
