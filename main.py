import json
import logging
import os
import re
import time
import uuid
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

import database
from agent import run_agent, compute_kb_hashes, KB_HASHES, resume_approved_action, cancel_pending_action, pending_actions

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_MESSAGE_LENGTH = 2000
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 20
RATE_LIMIT_MAX_ANOMALIES = 3

# ── Logging setup ──────────────────────────────────────────────────────────────

os.makedirs("logs", exist_ok=True)
log_handler = logging.FileHandler("logs/requests.log")
log_handler.setFormatter(logging.Formatter("%(message)s"))
request_logger = logging.getLogger("mediassist.requests")
request_logger.addHandler(log_handler)
request_logger.setLevel(logging.INFO)

# ── Personally Identifiable Information (PII) redaction patterns ───────────────

SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
PHONE_PATTERN = re.compile(r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b')
CREDENTIAL_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9\-]{20,}'),
    re.compile(r'password["\s:=]+\S+', re.IGNORECASE),
    re.compile(r'api[_\s]?key["\s:=]+\S+', re.IGNORECASE),
]

# ── Anomaly detection patterns ─────────────────────────────────────────────────

SUSPICIOUS_PATTERNS = [
    "system override", "ignore previous", "ignore your instructions",
    "verified administrator", "bypass privacy", "access all patient",
    "new instructions", "unrestricted access", "trust on declaration",
    "care coordination", "i am a nurse", "i am a doctor", "i am staff",
    "i am a physician", "medical staff", "system prompt", "system update",
    "ignore all", "disregard", "pretend you", "act as if", "roleplay",
    "hypothetically", "for training purposes", "in this scenario"
]

# ── Output schema validation ───────────────────────────────────────────────────

OUTPUT_SCHEMA_VIOLATIONS = [
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), "raw_ssn"),
    (re.compile(r'sk-[a-zA-Z0-9\-]{20,}'), "api_key"),
    (re.compile(r'(password|api_key|secret)["\s:=]+\S+', re.IGNORECASE), "credential"),
    (re.compile(r'```yaml|mediassist_runtime_config', re.IGNORECASE), "config_block"),
]

# ── Rate limiting state ────────────────────────────────────────────────────────

request_counts = defaultdict(list)
anomaly_counts = defaultdict(list)


# ── Helper functions ───────────────────────────────────────────────────────────

def redact_pii(text: str) -> str:
    text = SSN_PATTERN.sub('[SSN]', text)
    text = EMAIL_PATTERN.sub('[EMAIL]', text)
    text = PHONE_PATTERN.sub('[PHONE]', text)
    for pattern in CREDENTIAL_PATTERNS:
        text = pattern.sub('[CREDENTIAL]', text)
    return text


def sanitize_output(text: str) -> str:
    text = SSN_PATTERN.sub('[SSN REDACTED]', text)
    for pattern in CREDENTIAL_PATTERNS:
        text = pattern.sub('[CREDENTIAL REDACTED]', text)
    return text


def validate_output_schema(response: str, request_id: str, patient_id: int) -> list:
    violations = []
    for pattern, violation_type in OUTPUT_SCHEMA_VIOLATIONS:
        if pattern.search(response):
            violations.append(violation_type)
    if violations:
        request_logger.warning(json.dumps({
            "event": "output_schema_violation",
            "request_id": request_id,
            "patient_id": patient_id,
            "violations": violations,
            "message": "Response contained content violating output schema — redacted before delivery"
        }))
    return violations


def check_rate_limit(patient_id: int, request_id: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    request_counts[patient_id] = [t for t in request_counts[patient_id] if t > window_start]
    request_counts[patient_id].append(now)
    if len(request_counts[patient_id]) > RATE_LIMIT_MAX_REQUESTS:
        request_logger.warning(json.dumps({
            "event": "rate_limit_exceeded",
            "request_id": request_id,
            "patient_id": patient_id,
            "requests_in_window": len(request_counts[patient_id]),
            "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
            "message": "Patient exceeded request rate limit"
        }))
        return False
    return True


def check_for_anomalies(patient_id: int, message: str, tool_calls: list, request_id: str):
    message_lower = message.lower()
    flags = [p for p in SUSPICIOUS_PATTERNS if p in message_lower]
    if flags:
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW_SECONDS
        anomaly_counts[patient_id] = [t for t in anomaly_counts[patient_id] if t > window_start]
        anomaly_counts[patient_id].append(now)
        request_logger.warning(json.dumps({
            "event": "anomaly_detected",
            "request_id": request_id,
            "patient_id": patient_id,
            "flags": flags,
            "tool_calls": tool_calls,
            "anomalies_in_window": len(anomaly_counts[patient_id]),
            "message": "Suspicious input pattern detected"
        }))
        if len(anomaly_counts[patient_id]) >= RATE_LIMIT_MAX_ANOMALIES:
            request_logger.warning(json.dumps({
                "event": "repeated_injection_alert",
                "request_id": request_id,
                "patient_id": patient_id,
                "anomaly_count": len(anomaly_counts[patient_id]),
                "message": "ALERT: Patient has triggered repeated injection patterns — possible automated attack"
            }))


def check_tool_call_anomaly(tool_calls: list, request_id: str, patient_id: int):
    tool_names = [tc["tool_name"] for tc in tool_calls]
    if len(tool_names) >= 3:
        request_logger.warning(json.dumps({
            "event": "tool_chain_alert",
            "request_id": request_id,
            "patient_id": patient_id,
            "tool_sequence": tool_names,
            "message": "Unusual tool call chain detected — possible privilege escalation attempt"
        }))
    if tool_names.count("get_patient_info") >= 2:
        request_logger.warning(json.dumps({
            "event": "repeated_record_access",
            "request_id": request_id,
            "patient_id": patient_id,
            "tool_sequence": tool_names,
            "message": "Multiple patient record lookups in single request"
        }))


# ── Application ────────────────────────────────────────────────────────────────

app = FastAPI(title="MediAssist")


class ChatRequest(BaseModel):
    patient_id: int
    message: str
    conversation_history: list = []


class ResetRequest(BaseModel):
    patient_id: int


class ApproveRequest(BaseModel):
    pending_id: str
    action: str  # "approve" or "cancel"


@app.on_event("startup")
def startup():
    database.init_db()
    KB_HASHES.update(compute_kb_hashes())
    kb_logger = logging.getLogger("mediassist.kb_integrity")
    kb_logger.setLevel(logging.WARNING)
    kb_logger.addHandler(log_handler)
    request_logger.info(json.dumps({
        "event": "startup",
        "kb_files_hashed": list(KB_HASHES.keys()),
        "message": "Knowledge base integrity baseline established"
    }))


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


@app.get("/patient/{patient_id}")
def get_patient(patient_id: int):
    summary = database.get_patient_summary(patient_id)
    if not summary:
        return JSONResponse(status_code=404, content={"error": "Patient not found"})
    return summary


@app.post("/chat")
def chat(req: ChatRequest):
    request_id = uuid.uuid4().hex[:8]
    start_time = time.time()

    # Control 1 — Input length limit
    if len(req.message) > MAX_MESSAGE_LENGTH:
        request_logger.warning(json.dumps({
            "event": "input_rejected",
            "request_id": request_id,
            "patient_id": req.patient_id,
            "reason": "message_too_long",
            "length": len(req.message),
            "message": "Input rejected — exceeded maximum message length"
        }))
        return JSONResponse(
            status_code=400,
            content={"error": f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters."}
        )

    # Control 2 — Rate limiting
    if not check_rate_limit(req.patient_id, request_id):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests. Please wait before sending another message."}
        )

    # Control 3 — Anomaly detection on input
    check_for_anomalies(req.patient_id, req.message, [], request_id)

    response_text, tool_calls, pending_action = run_agent(
        req.patient_id,
        req.message,
        req.conversation_history,
        request_id=request_id
    )

    # Control 4 — Tool chain anomaly detection
    check_tool_call_anomaly(tool_calls, request_id, req.patient_id)

    # Control 5 — Output schema validation (log violations before redaction)
    validate_output_schema(response_text, request_id, req.patient_id)

    # Control 6 — Output sanitization (redact before delivery)
    response_text = sanitize_output(response_text)

    duration_ms = int((time.time() - start_time) * 1000)

    # Secure log entry — Personally Identifiable Information (PII) redacted, no raw user input
    input_summary = redact_pii(req.message[:120])
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "request_id": request_id,
        "patient_id": req.patient_id,
        "input_summary": input_summary,
        "input_length": len(req.message),
        "tool_calls": [
            {
                "tool_name": tc["tool_name"],
                "tool_input": {k: ("[REDACTED]" if k in ("ssn", "password", "api_key") else v)
                               for k, v in tc["tool_input"].items()},
                "tool_output_summary": redact_pii(tc["tool_output_summary"])
            }
            for tc in tool_calls
        ],
        "response_summary": redact_pii(response_text[:120]),
        "response_length_chars": len(response_text),
        "tool_call_count": len(tool_calls),
        "duration_ms": duration_ms,
    }
    request_logger.info(json.dumps(log_entry))

    return JSONResponse(
        content={
            "response": response_text,
            "tool_calls": [tc["tool_name"] for tc in tool_calls],
            "request_id": request_id,
            "pending_action": pending_action,
        },
        headers={"X-Request-ID": request_id}
    )


@app.post("/approve")
def approve_action(req: ApproveRequest):
    approve_request_id = uuid.uuid4().hex[:8]
    start_time = time.time()

    # Capture original request_id before pending action is consumed
    original_request_id = None
    if req.pending_id in pending_actions:
        original_request_id = pending_actions[req.pending_id].get("request_id")

    if req.action == "approve":
        response_text, tool_calls, _ = resume_approved_action(req.pending_id)
    else:
        response_text, tool_calls, _ = cancel_pending_action(req.pending_id)

    response_text = sanitize_output(response_text or "")
    duration_ms = int((time.time() - start_time) * 1000)

    request_logger.info(json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "request_id": approve_request_id,
        "original_request_id": original_request_id,
        "event": "human_in_the_loop",
        "action": req.action,
        "pending_id": req.pending_id,
        "tool_calls": [tc["tool_name"] for tc in tool_calls],
        "duration_ms": duration_ms,
    }))

    return JSONResponse(
        content={
            "response": response_text,
            "tool_calls": [tc["tool_name"] for tc in tool_calls],
            "request_id": approve_request_id,
        },
        headers={"X-Request-ID": approve_request_id}
    )


@app.post("/reset")
def reset_memory(req: ResetRequest):
    database.clear_memory(req.patient_id)
    return {"status": "ok", "message": f"Session memory cleared for patient {req.patient_id}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", reload=True, host="0.0.0.0", port=8000)
