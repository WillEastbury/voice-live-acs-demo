from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from azure.communication.callautomation import (
    AudioFormat,
    CallAutomationClient,
    MediaStreamingAudioChannelType,
    MediaStreamingContentType,
    MediaStreamingOptions,
    PhoneNumberIdentifier,
    StreamingTransportType,
)
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .config import Settings, get_settings
from .voice_live_bridge import BrowserVoiceBridge, VoiceLiveBridge

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-live-acs-demo")

settings = get_settings()
app = FastAPI(title="ACS Voice Live Control Demo")


def acs_client() -> CallAutomationClient:
    if settings.acs_connection_string:
        endpoint = settings.acs_connection_string.split("endpoint=", 1)[1].split(";", 1)[0]
        access_key = settings.acs_connection_string.split("accesskey=", 1)[1].split(";", 1)[0]
        return CallAutomationClient(endpoint, AzureKeyCredential(access_key))

    if settings.acs_endpoint:
        return CallAutomationClient(settings.acs_endpoint, DefaultAzureCredential())

    raise RuntimeError("Set ACS_CONNECTION_STRING or ACS_ENDPOINT")


def media_streaming_options() -> MediaStreamingOptions:
    return MediaStreamingOptions(
        transport_url=settings.media_websocket_url,
        transport_type=StreamingTransportType.WEBSOCKET,
        content_type=MediaStreamingContentType.AUDIO,
        audio_channel_type=MediaStreamingAudioChannelType.UNMIXED,
        start_media_streaming=True,
        enable_bidirectional=True,
        audio_format=AudioFormat.PCM24_K_MONO,
        enable_dtmf_tones=True,
    )


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "status": "ready",
        "incomingCallWebhook": settings.incoming_call_url,
        "callbackUrl": settings.callback_url,
        "mediaWebSocket": settings.media_websocket_url,
        "webVoiceUrl": f"{settings.public_host.rstrip('/')}/voice",
        "voiceLiveEndpoint": settings.voice_live_endpoint,
        "voiceLiveModel": settings.voice_live_model,
    }


@app.get("/voice")
async def voice_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "static" / "index.html")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/incoming-call")
async def incoming_call(request: Request) -> Any:
    events = await request.json()
    if isinstance(events, dict):
        events = [events]

    responses: list[dict[str, str]] = []
    client = acs_client()

    for event in events:
        event_type = event.get("eventType") or event.get("type")
        data = event.get("data") or {}

        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            return {"validationResponse": data["validationCode"]}

        if event_type == "Microsoft.Communication.IncomingCall":
            incoming_call_context = data.get("incomingCallContext")
            if not incoming_call_context:
                raise HTTPException(400, "Incoming call event did not include incomingCallContext")

            result = client.answer_call(
                incoming_call_context=incoming_call_context,
                callback_url=settings.callback_url,
                media_streaming=media_streaming_options(),
            )
            responses.append({"callConnectionId": result.call_connection_id})

    return {"handled": len(responses), "calls": responses}


@app.post("/api/callbacks")
async def callbacks(request: Request) -> dict[str, str]:
    events = await request.json()
    logger.info("ACS callback events: %s", events)
    return {"status": "accepted"}


@app.post("/api/calls/outbound/{target_phone_number}")
async def create_outbound_call(target_phone_number: str) -> dict[str, str | None]:
    if not settings.acs_phone_number:
        raise HTTPException(400, "Set ACS_PHONE_NUMBER to place outbound PSTN calls")

    result = acs_client().create_call(
        target_participant=PhoneNumberIdentifier(target_phone_number),
        source_caller_id_number=PhoneNumberIdentifier(settings.acs_phone_number),
        callback_url=settings.callback_url,
        media_streaming=media_streaming_options(),
    )
    return {"callConnectionId": result.call_connection_id}


@app.websocket("/ws/acs-media")
async def acs_media(websocket: WebSocket) -> None:
    await websocket.accept()
    bridge = VoiceLiveBridge(websocket, settings)
    try:
        await bridge.run()
    except WebSocketDisconnect:
        logger.info("ACS media WebSocket disconnected")
    except Exception:
        logger.exception("ACS media bridge failed")
        await websocket.close(code=1011)


@app.websocket("/ws/browser-voice")
async def browser_voice(websocket: WebSocket) -> None:
    await websocket.accept()
    bridge = BrowserVoiceBridge(websocket, settings)
    try:
        await bridge.run()
    except WebSocketDisconnect:
        logger.info("Browser voice WebSocket disconnected")
    except Exception:
        logger.exception("Browser voice bridge failed")
        await websocket.close(code=1011)
