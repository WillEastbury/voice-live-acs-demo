from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any


DISCLAIMER = (
    "Demo-only fake data. This is not medical advice, not a real clinical system, "
    "and no patient data is stored."
)


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "authenticate_patient",
        "description": "Verify a fake patient auth record using the caller's captured name, date of birth, and postcode before linking medical records.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Full name captured from the caller.",
                },
                "date_of_birth": {
                    "type": "string",
                    "description": "Date of birth in YYYY-MM-DD format.",
                },
                "postcode": {
                    "type": "string",
                    "description": "UK postcode captured from the caller.",
                },
            },
            "required": ["name", "date_of_birth", "postcode"],
        },
    },
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
                "patient_reference": {
                    "type": "string",
                    "description": "Demo patient reference if the caller has linked records.",
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
        "name": "book_appointment",
        "description": "Book a fake appointment for a linked demo patient and write it into the fake system.",
        "parameters": {
            "type": "object",
            "properties": {
                "slot_id": {
                    "type": "string",
                    "description": "ID of an available slot returned by get_doctor_calendar.",
                },
                "patient_reference": {
                    "type": "string",
                    "description": "Demo patient reference if linked.",
                },
                "reason": {
                    "type": "string",
                    "description": "Brief fake appointment reason.",
                },
            },
            "required": ["slot_id"],
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
                "patient_reference": {
                    "type": "string",
                    "description": "Demo patient reference if linked.",
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
                "patient_reference": {
                    "type": "string",
                    "description": "Demo patient reference if linked.",
                },
            },
            "required": ["medication"],
        },
    },
]


DEFAULT_DEMO_STATE: dict[str, Any] = {
    "demo_config": {
        "greeting": "Hello, you're through to the demo healthcare assistant. I can help with fake appointment availability, fake test results, callback escalation, and prescription request demos. How can I help?",
        "context": "Demo clinic context:\n- Patient is using fake demo data only.\n- Available departments: GP, cardiology, dermatology, pharmacy.\n- Do not give real medical advice.\n- For urgent or worsening symptoms, advise local urgent care/emergency services.\n\nIf asked to use tools, call the fake healthcare APIs and explain that results are synthetic demo data.",
    },
    "patients": [
        {"id": "demo-patient", "name": "Alex Demo", "date_of_birth": "1984-04-12", "postcode": "SW1A 1AA", "nhs_number": "DEMO-0001", "notes": "Default demo patient."},
        {"id": "pat-amelia", "name": "Amelia Green", "date_of_birth": "1978-09-03", "postcode": "BS1 4ST", "nhs_number": "DEMO-0002", "notes": "Prefers morning calls."},
        {"id": "pat-oliver", "name": "Oliver Brown", "date_of_birth": "1991-01-22", "postcode": "M1 1AE", "nhs_number": "DEMO-0003", "notes": "Uses Riverside Pharmacy."},
    ],
    "calendar_slots": [
        {"id": "slot-urgent-1", "specialty": "GP", "doctor": "Dr Patel", "time": "Today 16:20", "mode": "phone", "urgency": "urgent", "status": "available"},
        {"id": "slot-urgent-2", "specialty": "GP", "doctor": "Dr Morgan", "time": "Tomorrow 09:10", "mode": "clinic", "urgency": "urgent", "status": "available"},
        {"id": "slot-soon-1", "specialty": "GP", "doctor": "Dr Jones", "time": "Tomorrow 11:30", "mode": "video", "urgency": "soon", "status": "available"},
        {"id": "slot-soon-2", "specialty": "Cardiology", "doctor": "Dr Patel", "time": "Friday 14:00", "mode": "clinic", "urgency": "soon", "status": "available"},
        {"id": "slot-routine-1", "specialty": "Dermatology", "doctor": "Dr Morgan", "time": "Monday 10:15", "mode": "clinic", "urgency": "routine", "status": "available"},
    ],
    "medical_results": [
        {"id": "res-bloods-hb", "patient_reference": "demo-patient", "result_type": "bloods", "name": "Haemoglobin", "value": "142 g/L", "status": "within demo range"},
        {"id": "res-bloods-wcc", "patient_reference": "demo-patient", "result_type": "bloods", "name": "White cell count", "value": "6.2 x10^9/L", "status": "within demo range"},
        {"id": "res-chol-total", "patient_reference": "demo-patient", "result_type": "cholesterol", "name": "Total cholesterol", "value": "4.8 mmol/L", "status": "within demo range"},
        {"id": "res-xray", "patient_reference": "demo-patient", "result_type": "xray", "name": "Chest X-ray", "value": "No acute demo abnormality reported", "status": "reviewed"},
        {"id": "res-amelia-bp", "patient_reference": "pat-amelia", "result_type": "bloods", "name": "HbA1c", "value": "38 mmol/mol", "status": "within demo range"},
        {"id": "res-oliver-lipids", "patient_reference": "pat-oliver", "result_type": "cholesterol", "name": "LDL", "value": "2.1 mmol/L", "status": "within demo range"},
    ],
    "current_prescriptions": [
        {"id": "med-amelia-inhaler", "patient_reference": "pat-amelia", "medication": "Salbutamol demo inhaler", "dosage": "Two puffs when required", "pharmacy": "Riverside Pharmacy", "status": "active"},
        {"id": "med-oliver-statins", "patient_reference": "pat-oliver", "medication": "Atorvastatin demo tablets", "dosage": "20 mg once daily", "pharmacy": "Riverside Pharmacy", "status": "active"},
        {"id": "med-demo-vitd", "patient_reference": "demo-patient", "medication": "Vitamin D demo capsules", "dosage": "One daily", "pharmacy": "Demo Pharmacy", "status": "active"},
    ],
    "appointments": [],
    "escalations": [],
    "prescription_requests": [],
}


DEMO_STATE: dict[str, Any] = deepcopy(DEFAULT_DEMO_STATE)


def demo_state() -> dict[str, Any]:
    return {"disclaimer": DISCLAIMER, **deepcopy(DEMO_STATE)}


def reset_demo_state() -> dict[str, Any]:
    DEMO_STATE.clear()
    DEMO_STATE.update(deepcopy(DEFAULT_DEMO_STATE))
    return demo_state()


def update_demo_config(config: dict[str, Any]) -> dict[str, Any]:
    demo_config = DEMO_STATE.setdefault("demo_config", {})
    if "greeting" in config:
        demo_config["greeting"] = str(config.get("greeting") or "")
    if "context" in config:
        demo_config["context"] = str(config.get("context") or "")
    return {"disclaimer": DISCLAIMER, "demo_config": deepcopy(demo_config)}


def get_patient(patient_reference: str) -> dict[str, Any] | None:
    patient_key = patient_reference.strip().lower()
    for patient in DEMO_STATE["patients"]:
        if patient.get("id", "").lower() == patient_key or patient.get("name", "").lower() == patient_key:
            return deepcopy(patient)
    return None


def _normalize_postcode(postcode: str) -> str:
    return "".join(ch for ch in postcode.upper() if ch.isalnum())


def verify_patient_identity(name: str, date_of_birth: str, postcode: str) -> dict[str, Any] | None:
    normalized_name = " ".join(name.strip().lower().split())
    normalized_dob = date_of_birth.strip()
    normalized_postcode = _normalize_postcode(postcode)
    for patient in DEMO_STATE["patients"]:
        if (
            " ".join(patient.get("name", "").lower().split()) == normalized_name
            and patient.get("date_of_birth") == normalized_dob
            and _normalize_postcode(patient.get("postcode", "")) == normalized_postcode
        ):
            return deepcopy(patient)
    return None


def authenticate_patient(name: str, date_of_birth: str, postcode: str) -> dict[str, Any]:
    patient = verify_patient_identity(name, date_of_birth, postcode)
    if not patient:
        return {
            "disclaimer": DISCLAIMER,
            "authenticated": False,
            "error": "No matching fake auth record found.",
            "next_step": "Ask the caller to repeat their name, date of birth, and postcode, or escalate to a person.",
        }
    return {
        "disclaimer": DISCLAIMER,
        "authenticated": True,
        "patient_reference": patient["id"],
        "patient": patient,
        "next_step": "The fake patient record is linked for this session. You may now use patient-scoped tools.",
    }


def add_patient(patient: dict[str, Any]) -> dict[str, Any]:
    patient_id = str(patient.get("id") or "pat-" + uuid.uuid4().hex[:8]).strip()
    record = {
        "id": patient_id,
        "name": str(patient.get("name") or patient_id),
        "date_of_birth": str(patient.get("date_of_birth") or "not specified"),
        "postcode": str(patient.get("postcode") or "ZZ1 1ZZ").upper(),
        "nhs_number": str(patient.get("nhs_number") or "DEMO-" + uuid.uuid4().hex[:4].upper()),
        "notes": str(patient.get("notes") or ""),
    }
    DEMO_STATE["patients"].append(record)
    return {"disclaimer": DISCLAIMER, "patient": deepcopy(record)}


def patient_view(patient_reference: str) -> dict[str, Any] | None:
    patient = get_patient(patient_reference)
    if not patient:
        return None
    patient_id = patient["id"].lower()
    return {
        "disclaimer": DISCLAIMER,
        "patient": patient,
        "medical_results": [
            deepcopy(result)
            for result in DEMO_STATE["medical_results"]
            if result.get("patient_reference", "").lower() == patient_id
        ],
        "appointments": [
            deepcopy(appointment)
            for appointment in DEMO_STATE["appointments"]
            if appointment.get("patient_reference", "").lower() == patient_id
        ],
        "current_prescriptions": [
            deepcopy(prescription)
            for prescription in DEMO_STATE["current_prescriptions"]
            if prescription.get("patient_reference", "").lower() == patient_id
        ],
        "escalations": [
            deepcopy(escalation)
            for escalation in DEMO_STATE["escalations"]
            if escalation.get("patient_reference", "").lower() == patient_id
        ],
        "prescription_requests": [
            deepcopy(request)
            for request in DEMO_STATE["prescription_requests"]
            if request.get("patient_reference", "").lower() == patient_id
        ],
        "available_calendar_slots": deepcopy(DEMO_STATE["calendar_slots"]),
    }


def add_calendar_slot(slot: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": slot.get("id") or "slot-" + uuid.uuid4().hex[:8],
        "specialty": str(slot.get("specialty") or "GP"),
        "doctor": str(slot.get("doctor") or "Dr Demo"),
        "time": str(slot.get("time") or "Next available"),
        "mode": str(slot.get("mode") or "phone"),
        "urgency": str(slot.get("urgency") or "routine"),
        "status": str(slot.get("status") or "available"),
    }
    DEMO_STATE["calendar_slots"].append(record)
    return {"disclaimer": DISCLAIMER, "slot": deepcopy(record)}


def add_medical_result(result: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": result.get("id") or "res-" + uuid.uuid4().hex[:8],
        "patient_reference": str(result.get("patient_reference") or "demo-patient"),
        "result_type": str(result.get("result_type") or "bloods"),
        "name": str(result.get("name") or "Demo result"),
        "value": str(result.get("value") or "Pending"),
        "status": str(result.get("status") or "pending"),
    }
    DEMO_STATE["medical_results"].append(record)
    return {"disclaimer": DISCLAIMER, "result": deepcopy(record)}


def add_current_prescription(prescription: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": prescription.get("id") or "med-" + uuid.uuid4().hex[:8],
        "patient_reference": str(prescription.get("patient_reference") or "demo-patient"),
        "medication": str(prescription.get("medication") or "Demo medication"),
        "dosage": str(prescription.get("dosage") or "not specified"),
        "pharmacy": str(prescription.get("pharmacy") or "Demo Pharmacy"),
        "status": str(prescription.get("status") or "active"),
    }
    DEMO_STATE["current_prescriptions"].append(record)
    return {"disclaimer": DISCLAIMER, "prescription": deepcopy(record)}


def update_record(collection: str, record_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    if collection not in DEMO_STATE:
        return {"disclaimer": DISCLAIMER, "error": f"Unknown fake system collection: {collection}"}
    for record in DEMO_STATE[collection]:
        if record.get("id") == record_id:
            for key, value in updates.items():
                if key != "id" and value is not None:
                    record[key] = value
            return {"disclaimer": DISCLAIMER, "record": deepcopy(record)}
    return {"disclaimer": DISCLAIMER, "error": f"Record not found: {record_id}"}


def get_doctor_calendar(
    specialty: str,
    preferred_date: str | None = None,
    urgency: str = "routine",
    patient_reference: str | None = None,
) -> dict[str, Any]:
    specialty_label = specialty.strip().title() if specialty else "Gp"
    slots = [
        slot
        for slot in DEMO_STATE["calendar_slots"]
        if slot.get("status") == "available"
        and slot.get("specialty", "").lower() == specialty_label.lower()
        and (urgency == "routine" or slot.get("urgency") in {urgency, "urgent"})
    ]
    return {
        "disclaimer": DISCLAIMER,
        "specialty": specialty_label,
        "preferred_date": preferred_date or "first available",
        "patient_reference": patient_reference or "not linked",
        "urgency": urgency,
        "available_slots": deepcopy(slots),
        "booking_policy": "Ask the user which slot they prefer before confirming a booking.",
    }


def get_medical_results(
    result_type: str,
    patient_reference: str | None = None,
) -> dict[str, Any]:
    result_key = result_type.strip().lower()
    patient = patient_reference or "demo-patient"
    results = [
        result
        for result in DEMO_STATE["medical_results"]
        if result.get("result_type", "").lower() == result_key
        and result.get("patient_reference", "demo-patient").lower() == patient.lower()
    ]
    return {
        "disclaimer": DISCLAIMER,
        "patient_reference": patient,
        "result_type": result_type,
        "results": deepcopy(results) or [{"name": result_type.title(), "value": "Demo result pending review", "status": "pending"}],
        "safety_note": "If symptoms are severe or worsening, advise urgent local care rather than relying on demo results.",
    }


def book_appointment(
    slot_id: str,
    patient_reference: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    slot = next((slot for slot in DEMO_STATE["calendar_slots"] if slot.get("id") == slot_id), None)
    if not slot:
        return {
            "disclaimer": DISCLAIMER,
            "error": f"Appointment slot not found: {slot_id}",
        }
    if slot.get("status") != "available":
        return {
            "disclaimer": DISCLAIMER,
            "error": f"Appointment slot is not available: {slot_id}",
            "slot": deepcopy(slot),
        }

    appointment_id = "APT-" + uuid.uuid4().hex[:8].upper()
    slot["status"] = "booked"
    record = {
        "id": appointment_id,
        "appointment_id": appointment_id,
        "slot_id": slot_id,
        "patient_reference": patient_reference or "not linked",
        "specialty": slot.get("specialty"),
        "doctor": slot.get("doctor"),
        "time": slot.get("time"),
        "mode": slot.get("mode"),
        "reason": reason or "not specified",
        "status": "booked",
        "created_at": datetime.now(UTC).isoformat(),
    }
    DEMO_STATE["appointments"].append(record)
    return {
        "disclaimer": DISCLAIMER,
        "appointment": deepcopy(record),
        "updated_slot": deepcopy(slot),
        "next_step": "Tell the user the fake appointment has been recorded in the demo system.",
    }


def escalate_to_person(
    reason: str,
    urgency: str = "routine",
    callback_number: str | None = None,
    patient_reference: str | None = None,
) -> dict[str, Any]:
    ticket_id = "ESC-" + uuid.uuid4().hex[:8].upper()
    record = {
        "id": ticket_id,
        "disclaimer": DISCLAIMER,
        "ticket_id": ticket_id,
        "reason": reason,
        "patient_reference": patient_reference or "not linked",
        "urgency": urgency,
        "callback_number": callback_number or "not provided",
        "created_at": datetime.now(UTC).isoformat(),
        "next_step": "A demo staff member would call back; no real escalation has been sent.",
    }
    DEMO_STATE["escalations"].append({k: v for k, v in record.items() if k != "disclaimer"})
    return record


def request_prescription(
    medication: str,
    dosage: str | None = None,
    pharmacy: str | None = None,
    reason: str | None = None,
    patient_reference: str | None = None,
) -> dict[str, Any]:
    request_id = "RX-" + uuid.uuid4().hex[:8].upper()
    patient = patient_reference or "not linked"
    current = next(
        (
            item
            for item in DEMO_STATE["current_prescriptions"]
            if item.get("patient_reference") == patient
            and item.get("medication", "").lower() == medication.lower()
        ),
        None,
    )
    record = {
        "id": request_id,
        "disclaimer": DISCLAIMER,
        "request_id": request_id,
        "medication": medication,
        "patient_reference": patient,
        "dosage": dosage or (current or {}).get("dosage") or "not specified",
        "pharmacy": pharmacy or (current or {}).get("pharmacy") or "not specified",
        "reason": reason or "not specified",
        "matched_current_prescription_id": (current or {}).get("id", "none"),
        "status": "queued for fake clinician review",
        "next_step": "Tell the user this is only a demo request and would require clinician approval in a real system.",
    }
    DEMO_STATE["prescription_requests"].append({k: v for k, v in record.items() if k != "disclaimer"})
    return record


def _with_patient_default(arguments: dict[str, Any], patient_reference: str | None) -> dict[str, Any]:
    if patient_reference and not arguments.get("patient_reference"):
        return {**arguments, "patient_reference": patient_reference}
    return arguments


def call_tool(name: str, arguments: dict[str, Any], patient_reference: str | None = None) -> dict[str, Any]:
    if name == "authenticate_patient":
        return authenticate_patient(**arguments)
    arguments = _with_patient_default(arguments, patient_reference)
    if name == "get_doctor_calendar":
        return get_doctor_calendar(**arguments)
    if name == "get_medical_results":
        return get_medical_results(**arguments)
    if name == "book_appointment":
        return book_appointment(**arguments)
    if name == "escalate_to_person":
        return escalate_to_person(**arguments)
    if name == "request_prescription":
        return request_prescription(**arguments)
    return {
        "disclaimer": DISCLAIMER,
        "error": f"Unknown demo tool: {name}",
    }


def call_tool_json(name: str, arguments_json: str | None, patient_reference: str | None = None) -> str:
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as exc:
        return json.dumps(
            {
                "disclaimer": DISCLAIMER,
                "error": f"Invalid tool arguments JSON: {exc}",
            }
        )
    return json.dumps(call_tool(name, arguments, patient_reference))
