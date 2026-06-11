from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    acs_connection_string: str | None
    acs_endpoint: str | None
    public_host: str
    app_port: int
    voice_live_endpoint: str
    voice_live_api_key: str | None
    voice_live_model: str
    voice_live_voice: str
    voice_live_instructions: str
    acs_phone_number: str | None

    @property
    def callback_url(self) -> str:
        return f"{self.public_host.rstrip('/')}/api/callbacks"

    @property
    def incoming_call_url(self) -> str:
        return f"{self.public_host.rstrip('/')}/api/incoming-call"

    @property
    def media_websocket_url(self) -> str:
        public = self.public_host.rstrip("/")
        if public.startswith("https://"):
            return "wss://" + public.removeprefix("https://") + "/ws/acs-media"
        if public.startswith("http://"):
            return "ws://" + public.removeprefix("http://") + "/ws/acs-media"
        raise RuntimeError("PUBLIC_HOST must start with https:// or http://")

    @property
    def voice_live_ws_url(self) -> str:
        base = self.voice_live_endpoint.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base.removeprefix("https://")
        elif base.startswith("http://"):
            ws_base = "ws://" + base.removeprefix("http://")
        else:
            ws_base = base
        return f"{ws_base}/voice-live/realtime?api-version=2026-04-10&model={self.voice_live_model}"


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        acs_connection_string=os.getenv("ACS_CONNECTION_STRING"),
        acs_endpoint=os.getenv("ACS_ENDPOINT"),
        public_host=required("PUBLIC_HOST"),
        app_port=int(os.getenv("APP_PORT", "8080")),
        voice_live_endpoint=required("VOICE_LIVE_ENDPOINT"),
        voice_live_api_key=os.getenv("VOICE_LIVE_API_KEY"),
        voice_live_model=os.getenv("VOICE_LIVE_MODEL", "gpt-realtime-mini"),
        voice_live_voice=os.getenv("VOICE_LIVE_VOICE", "en-US-AvaNeural"),
        voice_live_instructions=os.getenv(
            "VOICE_LIVE_INSTRUCTIONS",
            "You are a concise demo voice control agent.",
        ),
        acs_phone_number=os.getenv("ACS_PHONE_NUMBER"),
    )
