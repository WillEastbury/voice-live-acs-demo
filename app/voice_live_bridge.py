from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
from typing import Any

import websockets
from azure.identity.aio import DefaultAzureCredential
from starlette.websockets import WebSocket

from .config import Settings
from .demo_medical_tools import TOOL_DEFINITIONS, call_tool, get_patient

logger = logging.getLogger("voice-live-acs-demo.bridge")

BRITISH_VOICES = [
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-GB-LibbyNeural",
    "en-GB-AbbiNeural",
    "en-GB-AlfieNeural",
    "en-GB-OliverNeural",
    "en-GB-MaisieNeural",
]


class VoiceLiveBridge:
    def __init__(self, acs_websocket: WebSocket, settings: Settings):
        self.acs_websocket = acs_websocket
        self.settings = settings
        self.credential: DefaultAzureCredential | None = None
        self.voice_live = None
        self.completed_tool_calls: set[str] = set()
        self.patient_reference: str | None = None
        self.session_voice = random.choice(BRITISH_VOICES)

    async def run(self) -> None:
        headers = await self._auth_headers()
        self.voice_live = await self._connect_voice_live(headers)
        await self._configure_session()

        try:
            await asyncio.gather(
                self._acs_to_voice_live(),
                self._voice_live_to_acs(),
            )
        finally:
            if self.voice_live:
                await self.voice_live.close()
            if self.credential:
                await self.credential.close()

    async def _auth_headers(self) -> dict[str, str]:
        if self.settings.voice_live_api_key:
            return {"api-key": self.settings.voice_live_api_key}

        self.credential = DefaultAzureCredential()
        token = await self.credential.get_token("https://ai.azure.com/.default")
        return {"Authorization": f"Bearer {token.token}"}

    async def _connect_voice_live(self, headers: dict[str, str]):
        try:
            return await websockets.connect(
                self.settings.voice_live_ws_url,
                additional_headers=headers,
                max_size=None,
                ping_interval=20,
                ping_timeout=20,
            )
        except TypeError:
            return await websockets.connect(
                self.settings.voice_live_ws_url,
                extra_headers=headers,
                max_size=None,
                ping_interval=20,
                ping_timeout=20,
            )

    async def _configure_session(self) -> None:
        instructions = (
            f"{self.settings.voice_live_instructions}\n\n"
            "Healthcare demo flow:\n"
            "- Before appointment lookup or booking, medical result lookup, prescription requests, "
            "or record access, collect the caller's full name, date of birth, and postcode, then call "
            "authenticate_patient.\n"
            "- Do not use patient-scoped tools until authenticate_patient succeeds.\n"
            "- The only tool you may use before authentication succeeds is escalate_to_person.\n"
            "- If the caller asks for a person, sounds frustrated, objects to the authentication flow, "
            "or wants to stop, call escalate_to_person.\n"
            "- For urgent or worsening symptoms, advise local urgent care or emergency services."
        )
        await self._send_voice_live(
            {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": instructions,
                    "input_audio_sampling_rate": 24000,
                    "input_audio_transcription": {"model": "azure-speech", "language": "en"},
                    "turn_detection": {
                        "type": "azure_semantic_vad",
                        "silence_duration_ms": 500,
                        "interrupt_response": True,
                    },
                    "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
                    "tools": TOOL_DEFINITIONS,
                    "tool_choice": "auto",
                    "voice": {
                        "name": self.session_voice,
                        "type": "azure-standard",
                    },
                },
            }
        )

    async def _acs_to_voice_live(self) -> None:
        while True:
            raw = await self.acs_websocket.receive_text()
            message = json.loads(raw)
            kind = message.get("kind")

            if kind == "AudioMetadata":
                logger.info("ACS audio metadata: %s", message.get("audioMetadata", {}))
                continue

            if kind == "AudioData":
                audio = message.get("audioData") or {}
                if audio.get("silent"):
                    continue
                chunk = audio.get("data")
                if chunk:
                    await self._send_voice_live(
                        {"type": "input_audio_buffer.append", "audio": chunk}
                    )
                continue

            if kind == "DtmfData":
                digit = (message.get("dtmfData") or {}).get("data")
                if digit:
                    await self._send_dtmf_command(digit)
                continue

            logger.debug("Unhandled ACS media message kind=%s", kind)

    async def _voice_live_to_acs(self) -> None:
        async for raw in self.voice_live:
            event = json.loads(raw)
            event_type = event.get("type", "")

            if event_type.endswith("audio.delta"):
                delta = event.get("delta")
                if delta:
                    await self._send_acs_audio(delta)
                continue

            if await self._handle_tool_call_event(event):
                continue

            if event_type in {"input_audio_buffer.speech_started", "conversation.interrupted"}:
                await self._send_acs_stop_audio()
                continue

            if event_type == "error":
                logger.error("Voice Live error: %s", event)
                continue

            logger.debug("Voice Live event: %s", event_type)

    async def _send_voice_live(self, payload: dict[str, Any]) -> None:
        await self.voice_live.send(json.dumps(payload))

    async def _handle_tool_call_event(self, event: dict[str, Any]) -> bool:
        event_type = event.get("type", "")
        call_id = event.get("call_id")
        name = event.get("name")
        arguments = event.get("arguments")

        item = event.get("item") or {}
        if item.get("type") == "function_call":
            call_id = call_id or item.get("call_id")
            name = name or item.get("name")
            arguments = arguments or item.get("arguments")

        if event_type not in {"response.function_call_arguments.done", "response.output_item.done"}:
            return False
        if not call_id or not name:
            return False
        if call_id in self.completed_tool_calls:
            return True

        self.completed_tool_calls.add(call_id)
        try:
            parsed_arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            result = {
                "error": f"Invalid tool arguments JSON: {exc}",
            }
        else:
            result = call_tool(name, parsed_arguments, self.patient_reference)
        if name == "authenticate_patient" and result.get("authenticated"):
            self.patient_reference = result.get("patient_reference")
            await self._configure_session()
        output = json.dumps(result)
        logger.info("Voice Live tool call: %s(%s) -> %s", name, arguments, output)
        await self._send_voice_live(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                },
            }
        )
        await self._send_voice_live({"type": "response.create"})
        return True

    async def _send_dtmf_command(self, digit: str) -> None:
        await self._send_voice_live(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"The caller pressed DTMF {digit}. Treat this as a voice control shortcut.",
                        }
                    ],
                },
            }
        )
        await self._send_voice_live({"type": "response.create"})

    async def _send_acs_audio(self, base64_pcm: str) -> None:
        await self.acs_websocket.send_text(
            json.dumps(
                {
                    "kind": "AudioData",
                    "audioData": {
                        "data": base64_pcm,
                    },
                }
            )
        )

    async def _send_acs_stop_audio(self) -> None:
        await self.acs_websocket.send_text(json.dumps({"kind": "StopAudio"}))


class BrowserVoiceBridge(VoiceLiveBridge):
    def __init__(self, acs_websocket: WebSocket, settings: Settings):
        super().__init__(acs_websocket, settings)
        self.demo_context = ""

    async def run(self) -> None:
        headers = await self._auth_headers()
        self.voice_live = await self._connect_voice_live(headers)
        await self._configure_session()
        await self._safe_browser_send(
            {"type": "event", "event": "voice.selected", "voice": self.session_voice}
        )

        try:
            browser_task = asyncio.create_task(self._browser_to_voice_live())
            voice_task = asyncio.create_task(self._voice_live_to_browser())
            done, pending = await asyncio.wait(
                {browser_task, voice_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                exc = None if task.cancelled() else task.exception()
                if exc:
                    logger.exception("Browser bridge task failed", exc_info=exc)
                    await self._safe_browser_send({"type": "error", "error": str(exc)})
                else:
                    await self._safe_browser_send({"type": "event", "event": "bridge.completed"})
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        finally:
            if self.voice_live:
                await self.voice_live.close()
            if self.credential:
                await self.credential.close()

    async def _browser_to_voice_live(self) -> None:
        while True:
            raw = await self.acs_websocket.receive_text()
            message = json.loads(raw)
            message_type = message.get("type")

            if message_type == "input_audio":
                chunk = message.get("audio")
                if chunk and is_base64_audio(chunk):
                    await self._send_voice_live(
                        {"type": "input_audio_buffer.append", "audio": chunk}
                    )
                continue

            if message_type == "context_update":
                self.demo_context = str(message.get("context") or "").strip()
                await self._configure_session()
                await self.acs_websocket.send_text(
                    json.dumps({"type": "event", "event": "context.updated"})
                )
                continue

            if message_type == "patient_identity":
                patient_reference = str(message.get("patient_reference") or "").strip()
                self.patient_reference = patient_reference or None
                await self._configure_session()
                await self.acs_websocket.send_text(
                    json.dumps(
                        {
                            "type": "event",
                            "event": "patient.linked" if self.patient_reference else "patient.cleared",
                            "patient": get_patient(self.patient_reference) if self.patient_reference else None,
                        }
                    )
                )
                continue

            if message_type == "greeting":
                greeting = str(message.get("text") or "").strip()
                if greeting:
                    patient_name = None
                    if self.patient_reference:
                        patient = get_patient(self.patient_reference)
                        patient_name = (patient or {}).get("name")
                    personalized = greeting
                    if patient_name:
                        personalized = f"Address the caller as {patient_name}. {greeting}"
                    await self._send_voice_live(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_text",
                                        "text": (
                                            "Use the following as your opening greeting. "
                                            "Speak it naturally and do not mention that it came from a control panel: "
                                            f"{personalized}"
                                        ),
                                    }
                                ],
                            },
                        }
                    )
                    await self._send_voice_live({"type": "response.create"})
                continue

            if message_type == "simulated_tool_result":
                tool_name = str(message.get("toolName") or "demo_context_lookup").strip()
                output = str(message.get("output") or "").strip()
                if output:
                    await self._send_voice_live(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_text",
                                        "text": (
                                            f"Simulated tool result from {tool_name}: {output}\n"
                                            "Use this as fresh external state for the next response."
                                        ),
                                    }
                                ],
                            },
                        }
                    )
                    await self._send_voice_live({"type": "response.create"})
                continue

            if message_type == "text":
                text = message.get("text")
                if text:
                    await self._send_voice_live(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": text}],
                            },
                        }
                    )
                    await self._send_voice_live({"type": "response.create"})
                continue

            if message_type == "clear":
                await self._send_voice_live({"type": "input_audio_buffer.clear"})

    async def _configure_session(self) -> None:
        instructions = (
            f"{self.settings.voice_live_instructions}\n\n"
            "Healthcare demo flow:\n"
            "- Before appointment lookup or booking, medical result lookup, prescription requests, "
            "or record access, collect the caller's full name, date of birth, and postcode, then call "
            "authenticate_patient.\n"
            "- Do not use patient-scoped tools until authenticate_patient succeeds.\n"
            "- The only tool you may use before authentication succeeds is escalate_to_person.\n"
            "- If the caller asks for a person, sounds frustrated, objects to the authentication flow, "
            "or wants to stop, call escalate_to_person.\n"
            "- For urgent or worsening symptoms, advise local urgent care or emergency services."
        )
        if self.demo_context:
            instructions = (
                f"{instructions}\n\n"
                "Presenter-supplied live demo context. Treat this as current, authoritative "
                f"state for this session:\n{self.demo_context}"
            )
        if self.patient_reference:
            patient = get_patient(self.patient_reference)
            patient_context = patient or {"id": self.patient_reference, "name": self.patient_reference}
            instructions = (
                f"{instructions}\n\n"
                "The caller has identified themselves and linked the following synthetic demo medical record. "
                "Use this patient_reference for tool calls unless the user explicitly chooses another demo patient. "
                f"Patient link: {json.dumps(patient_context)}"
            )

        await self._send_voice_live(
            {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": instructions,
                    "input_audio_sampling_rate": 24000,
                    "input_audio_transcription": {"model": "azure-speech", "language": "en"},
                    "turn_detection": {
                        "type": "azure_semantic_vad",
                        "silence_duration_ms": 500,
                        "interrupt_response": True,
                    },
                    "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
                    "tools": TOOL_DEFINITIONS,
                    "tool_choice": "auto",
                    "voice": {
                        "name": self.session_voice,
                        "type": "azure-standard",
                    },
                },
            }
        )

    async def _voice_live_to_browser(self) -> None:
        async for raw in self.voice_live:
            event = json.loads(raw)
            event_type = event.get("type", "")

            if event_type.endswith("audio.delta"):
                delta = event.get("delta")
                if delta:
                    await self.acs_websocket.send_text(
                        json.dumps({"type": "audio", "audio": delta})
                    )
                continue

            if await self._handle_tool_call_event(event):
                await self.acs_websocket.send_text(
                    json.dumps(
                        {
                            "type": "tool_call",
                            "name": event.get("name") or (event.get("item") or {}).get("name"),
                        }
                    )
                )
                continue

            if event_type.endswith("audio_transcript.delta"):
                delta = event.get("delta")
                if delta:
                    await self.acs_websocket.send_text(
                        json.dumps({"type": "transcript_delta", "text": delta})
                    )
                continue

            if event_type in {"response.done", "session.updated", "session.created"}:
                await self.acs_websocket.send_text(
                    json.dumps({"type": "event", "event": event_type})
                )
                continue

            if event_type == "error":
                logger.error("Voice Live browser error: %s", event)
                await self._safe_browser_send({"type": "error", "error": event})

    async def _safe_browser_send(self, payload: dict[str, Any]) -> None:
        try:
            await self.acs_websocket.send_text(json.dumps(payload))
        except Exception:
            logger.debug("Could not send browser WebSocket payload", exc_info=True)


def pcm24k_to_wav_bytes(pcm: bytes) -> bytes:
    header = bytearray()
    header.extend(b"RIFF")
    header.extend((36 + len(pcm)).to_bytes(4, "little"))
    header.extend(b"WAVEfmt ")
    header.extend((16).to_bytes(4, "little"))
    header.extend((1).to_bytes(2, "little"))
    header.extend((1).to_bytes(2, "little"))
    header.extend((24000).to_bytes(4, "little"))
    header.extend((24000 * 2).to_bytes(4, "little"))
    header.extend((2).to_bytes(2, "little"))
    header.extend((16).to_bytes(2, "little"))
    header.extend(b"data")
    header.extend(len(pcm).to_bytes(4, "little"))
    return bytes(header) + pcm


def is_base64_audio(value: str) -> bool:
    try:
        base64.b64decode(value, validate=True)
        return True
    except Exception:
        return False
