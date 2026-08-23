"""
QR code token/URL generation and PNG rendering.
"""
import base64
import secrets
from io import BytesIO

import qrcode

from app.core.config import get_settings

settings = get_settings()


def generate_token() -> str:
    return secrets.token_urlsafe(8)


def build_scan_url(dealer_id: str, token: str) -> str:
    base = settings.frontend_public_base_url.rstrip("/")
    return f"{base}/d/{dealer_id}?code={token}"


def render_qr_png_data_url(content: str) -> str:
    img = qrcode.make(content)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
