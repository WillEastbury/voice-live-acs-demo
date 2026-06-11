from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


DISCLAIMER = (
    "Demo-only fake data. This is not medical advice, not a real clinical system, "
    "and no patient data is stored."
)


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_doctor_calendar",
        "description": "Find fake available doctor appointment slots for a demo patient.",
        "parameters": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Doctor specialty, for example GP, cardiology, dermatology.",
                },
                "preferred_date": {
                    "type": "string",
                    "description": "Preferred appointment date or natural date phrase.",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["routine", "soon", "urgent"],
                },
            },
            "required": ["specialty"],
        },
    },
    {
        "type": "function",
        "name": "get_medical_results",
        "description": "Return fake medical test results for a demo patient.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_reference": {
                    "type": "string",
                    "description": "Demo patient name or reference. Never use real patient identifiers.",
                },
                "result_type": {
                    "type": "string",
                    "description": "Requested result type, for example bloods, cholesterol, xray.",
                },
            },
            "required": ["result_type"],
        },
    },
    {
        "type": "function",
        "name": "escalate_to_person",
        "description": "Create a fake callback/escalation ticket to a human staff member.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "urgency": {
                    "type": "string",
                    "enum": ["routine", "soon", "urgent"],
                },
                "callback_number": {
                    "type": "string",
                    "description": "Optional demo callback number supplied by the user.",
                },
            },
            "required": ["reason"],
        },
    },
    {
        "type": "function",
        "name": "request_prescription",
        "description": "Create a fake prescription request that requires clinician review.",
        "parameters": {
            "type": "object",
            "properties": {
                "medication": {"type": "string"},
                "dosage": {"type": "string"},
                "pharmacy": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["medication"],
        },
    },
]


def get_doctor_calendar(
    specialty: str,
    preferred_date: str | None = None,
    urgency: str = "routine",
) -> dict[str, Any]:
    specialty_label = specialty.strip().title() if specialty else "Gp"
    slots = {
        "urgent": [
            {"doctor": "Dr Patel", "time": "Today 16:20", "mode": "phone"},
            {"doctor": "Dr Morgan", "time": "Tomorrow 09:10", "mode": "clinic"},
        ],
        "soon": [
            {"doctor": "Dr Jones", "time": "Tomorrow 11:30", "mode": "video"},
            {"doctor": "Dr Patel", "time": "Friday 14:00", "mode": "clinic"},
        ],
        "routine": [
            {"doctor": "Dr Morgan", "time": "Monday 10:15", "mode": "clinic"},
            {"doctor": "Dr Jones", "time": "Tuesday 15:45", "mode": "phone"},
        ],
    }.get(urgency, [])
    return {
        "disclaimer": DISCLAIMER,
        "specialty": specialty_label,
        "preferred_date": preferred_date or "first available",
        "urgency": urgency,
        "available_slots": slots,
        "booking_policy": "Ask the user which slot they prefer before confirming a booking.",
    }


def get_medical_results(
    result_type: str,
    patient_reference: str | None = None,
) -> dict[str, Any]:
    result_key = result_type.strip().lower()
    examples = {
        "bloods": [
            {"name": "Haemoglobin", "value": "142 g/L", "status": "within demo range"},
            {"name": "White cell count", "value": "6.2 x10^9/L", "status": "within demo range"},
        ],
        "cholesterol": [
            {"name": "Total cholesterol", "value": "4.8 mmol/L", "status": "within demo range"},
            {"name": "HDL", "value": "1.4 mmol/L", "status": "within demo range"},
        ],
        "xray": [
            {"name": "Chest X-ray", "value": "No acute demo abnormality reported", "status": "reviewed"},
        ],
    }
    return {
        "disclaimer": DISCLAIMER,
        "patient_reference": patient_reference or "demo-patient",
        "result_type": result_type,
        "results": examples.get(
            result_key,
            [{"name": result_type.title(), "value": "Demo result pending review", "status": "pending"}],
        ),
        "safety_note": "If symptoms are severe or worsening, advise urgent local care rather than relying on demo results.",
    }


def escalate_to_person(
    reason: str,
    urgency: str = "routine",
    callback_number: str | None = None,
) -> dict[str, Any]:
    ticket_id = "ESC-" + uuid.uuid4().hex[:8].upper()
    return {
        "disclaimer": DISCLAIMER,
        "ticket_id": ticket_id,
        "reason": reason,
        "urgency": urgency,
        "callback_number": callback_number or "not provided",
        "created_at": datetime.now(UTC).isoformat(),
        "next_step": "A demo staff member would call back; no real escalation has been sent.",
    }


def request_prescription(
    medication: str,
    dosage: str | None = None,
    pharmacy: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    request_id = "RX-" + uuid.uuid4().hex[:8].upper()
    return {
        "disclaimer": DISCLAIMER,
        "request_id": request_id,
        "medication": medication,
        "dosage": dosage or "not specified",
        "pharmacy": pharmacy or "not specified",
        "reason": reason or "not specified",
        "status": "queued for fake clinician review",
        "next_step": "Tell the user this is only a demo request and would require clinician approval in a real system.",
    }


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "get_doctor_calendar":
        return get_doctor_calendar(**arguments)
    if name == "get_medical_results":
        return get_medical_results(**arguments)
    if name == "escalate_to_person":
        return escalate_to_person(**arguments)
    if name == "request_prescription":
        return request_prescription(**arguments)
    return {
        "disclaimer": DISCLAIMER,
        "error": f"Unknown demo tool: {name}",
    }


def call_tool_json(name: str, arguments_json: str | None) -> str:
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as exc:
        return json.dumps(
            {
                "disclaimer": DISCLAIMER,
                "error": f"Invalid tool arguments JSON: {exc}",
            }
        )
    return json.dumps(call_tool(name, arguments))
