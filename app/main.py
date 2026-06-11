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
from .fake_medical_tools import (
    DISCLAIMER,
    add_calendar_slot,
    add_current_prescription,
    add_medical_result,
    add_patient,
    book_appointment,
    demo_state,
    escalate_to_person,
    get_doctor_calendar,
    get_medical_results,
    get_patient,
    patient_view,
    request_prescription,
    reset_demo_state,
    update_demo_config,
    update_record,
    verify_patient_identity,
)
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
async def console_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "static" / "index.html")


@app.get("/voice")
async def voice_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "static" / "index.html")


@app.get("/api/routes")
async def routes() -> dict[str, Any]:
    return {
        "status": "ready",
        "consoleUrl": settings.public_host.rstrip("/"),
        "incomingCallWebhook": settings.incoming_call_url,
        "callbackUrl": settings.callback_url,
        "mediaWebSocket": settings.media_websocket_url,
        "webVoiceUrl": f"{settings.public_host.rstrip('/')}/voice",
        "fakeSystemsUrl": f"{settings.public_host.rstrip('/')}/systems",
        "fakeMedicalApis": [
            "/api/fake/state",
            "/api/fake/patients",
            "/api/fake/verify-patient",
            "/api/fake/doctor-calendar",
            "/api/fake/appointments",
            "/api/fake/medical-results",
            "/api/fake/current-prescriptions",
            "/api/fake/escalate",
            "/api/fake/prescription-request",
        ],
        "voiceLiveEndpoint": settings.voice_live_endpoint,
        "voiceLiveModel": settings.voice_live_model,
    }


@app.get("/systems")
async def systems_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "static" / "systems.html")


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


@app.get("/api/fake/doctor-calendar")
async def fake_doctor_calendar(
    specialty: str = "GP",
    preferred_date: str | None = None,
    urgency: str = "routine",
) -> dict[str, Any]:
    return get_doctor_calendar(specialty, preferred_date, urgency)


@app.post("/api/fake/doctor-calendar")
async def fake_add_doctor_calendar_slot(payload: dict[str, Any]) -> dict[str, Any]:
    return add_calendar_slot(payload)


@app.post("/api/fake/appointments")
async def fake_book_appointment(payload: dict[str, Any]) -> dict[str, Any]:
    slot_id = str(payload.get("slot_id") or "").strip()
    if not slot_id:
        raise HTTPException(400, "slot_id is required")
    result = book_appointment(
        slot_id=slot_id,
        patient_reference=payload.get("patient_reference"),
        reason=payload.get("reason"),
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.get("/api/fake/patients")
async def fake_patients() -> dict[str, Any]:
    state = demo_state()
    return {"disclaimer": DISCLAIMER, "patients": state["patients"]}


@app.post("/api/fake/patients")
async def fake_add_patient(payload: dict[str, Any]) -> dict[str, Any]:
    return add_patient(payload)


@app.post("/api/fake/verify-patient")
async def fake_verify_patient(payload: dict[str, Any]) -> dict[str, Any]:
    patient = verify_patient_identity(
        name=str(payload.get("name") or ""),
        date_of_birth=str(payload.get("date_of_birth") or ""),
        phone_last4=str(payload.get("phone_last4") or ""),
    )
    if not patient:
        raise HTTPException(404, "No matching fake patient found")
    return {"disclaimer": DISCLAIMER, "patient": patient}


@app.get("/api/fake/patients/{patient_reference}")
async def fake_patient(patient_reference: str) -> dict[str, Any]:
    view = patient_view(patient_reference)
    if not view:
        raise HTTPException(404, "patient not found")
    return view


@app.get("/api/fake/medical-results")
async def fake_medical_results(
    result_type: str = "bloods",
    patient_reference: str | None = None,
) -> dict[str, Any]:
    return get_medical_results(result_type, patient_reference)


@app.post("/api/fake/medical-results")
async def fake_add_medical_result(payload: dict[str, Any]) -> dict[str, Any]:
    return add_medical_result(payload)


@app.post("/api/fake/current-prescriptions")
async def fake_add_current_prescription(payload: dict[str, Any]) -> dict[str, Any]:
    medication = str(payload.get("medication") or "").strip()
    if not medication:
        raise HTTPException(400, "medication is required")
    return add_current_prescription(payload)


@app.post("/api/fake/escalate")
async def fake_escalate(payload: dict[str, Any]) -> dict[str, Any]:
    return escalate_to_person(
        reason=str(payload.get("reason") or "Requested human callback"),
        urgency=str(payload.get("urgency") or "routine"),
        callback_number=payload.get("callback_number"),
        patient_reference=payload.get("patient_reference"),
    )


@app.post("/api/fake/prescription-request")
async def fake_prescription_request(payload: dict[str, Any]) -> dict[str, Any]:
    medication = str(payload.get("medication") or "").strip()
    if not medication:
        raise HTTPException(400, "medication is required")
    return request_prescription(
        medication=medication,
        dosage=payload.get("dosage"),
        pharmacy=payload.get("pharmacy"),
        reason=payload.get("reason"),
        patient_reference=payload.get("patient_reference"),
    )


@app.get("/api/fake")
async def fake_api_index() -> dict[str, Any]:
    return {
        "disclaimer": DISCLAIMER,
        "endpoints": {
            "doctorCalendar": "/api/fake/doctor-calendar?specialty=GP&urgency=soon",
            "addDoctorCalendarSlot": "POST /api/fake/doctor-calendar",
            "bookAppointment": "POST /api/fake/appointments",
            "medicalResults": "/api/fake/medical-results?result_type=bloods",
            "addMedicalResult": "POST /api/fake/medical-results",
            "addCurrentPrescription": "POST /api/fake/current-prescriptions",
            "escalate": "POST /api/fake/escalate",
            "prescriptionRequest": "POST /api/fake/prescription-request",
            "state": "/api/fake/state",
            "reset": "POST /api/fake/reset",
            "patients": "/api/fake/patients",
            "verifyPatient": "POST /api/fake/verify-patient",
        },
    }


@app.get("/api/fake/state")
async def fake_state() -> dict[str, Any]:
    return demo_state()


@app.patch("/api/fake/config")
async def fake_update_config(payload: dict[str, Any]) -> dict[str, Any]:
    return update_demo_config(payload)


@app.post("/api/fake/reset")
async def fake_reset() -> dict[str, Any]:
    return reset_demo_state()


@app.patch("/api/fake/{collection}/{record_id}")
async def fake_update_record(collection: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = update_record(collection, record_id, payload)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


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
