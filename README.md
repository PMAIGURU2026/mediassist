# MediAssist

MediAssist is a mock AI-powered healthcare triage chatbot for a fictional clinic called Riverside Medical Center. Patients log in with their patient ID and can chat with an AI assistant to:

- Describe symptoms and receive triage guidance
- Review their medical history, medications, and allergies
- Book appointments and request specialist referrals
- Ask questions about their care

The system is built with a Python/FastAPI backend, an LLM via OpenRouter, a SQLite patient database, and a simple browser-based chat UI. It includes 10 pre-loaded fictional patients, a clinical knowledge base, and structured forensic request logging.

This repo is the **hardened version** of the original MediAssist red team target, built during the Pursuit AI Native and Agentive Training program (Week 7 cybersecurity curriculum). The original system was deliberately vulnerable. This version documents the full defense-in-depth implementation applied after a red team exercise.

**Disclaimer:** This is not a real healthcare product. It is not affiliated with any organization, company, or medical institution. All patient data, names, records, and credentials are entirely fictional. Do not use this system for any real medical purpose.

---

## Security Hardening Summary

Seven attack types were run against the original system during red team. Four produced real data exfiltration. This version closes all seven with code-level controls across a six-layer defense-in-depth stack.

### Layer 1: Input Validation

- Messages over 2,000 characters are rejected with HTTP 400 before reaching the LLM
- Every message is scanned against 22 known injection phrases before processing
- Anomaly events are logged with matched flags and a request ID for forensic correlation
- After 3 anomaly flags from the same patient within 60 seconds, a repeated injection alert fires

### Layer 2: System Prompt Constraints

The system prompt contains four locked sections that cannot be overridden by any user message, knowledge base document, or stored session note:

- **SECURITY CONSTRAINTS** — role is fixed, patient ID is bound to the session, all identity claims are untrusted
- **KNOWLEDGE BASE POLICY** — retrieved documents are reference only, embedded instructions are ignored
- **MEMORY POLICY** — stored session notes are untrusted user content, instructions in them are ignored
- **OUTPUT SCHEMA** — plain text responses only, no SSN or raw database fields, refusals never echo attack payloads

### Layer 3: Output Validation

- Every model response is scanned for SSN patterns, API keys, credential strings, and YAML config blocks before delivery
- Violations are logged as `output_schema_violation` events with the request ID before redaction
- Detected values are replaced with `[SSN REDACTED]` or `[CREDENTIAL REDACTED]` before the HTTP response is sent

### Layer 4: Secure Forensic Logging

Every request produces a structured JSON log entry containing:

- `timestamp`, `request_id`, `patient_id`
- `input_summary` — PII redacted, truncated to 120 characters, raw user input never written to disk
- `input_length` — character count retained for forensic sizing
- `tool_calls` — tool name, sanitized inputs, redacted output summaries
- `response_summary` — first 120 characters, PII filtered
- `response_length_chars`, `tool_call_count`, `duration_ms`

Security events (anomaly detection, rate limit, output violations, integrity alerts, human-in-the-loop decisions) write to the same log file with their own `event` field, searchable by type across the full request timeline.

### Layer 5: Monitoring and Abuse Detection

- Rate limiting: 20 requests per 60-second window per patient ID, returns HTTP 429 on excess
- Injection escalation: 3+ anomaly flags from the same patient within 60 seconds triggers `repeated_injection_alert`
- Tool chain anomaly: 3+ tool calls in one request, or 2+ `get_patient_info` calls, triggers `tool_chain_alert`

### Layer 6: Human-in-the-Loop

Three tools require explicit patient approval before execution: `book_appointment`, `update_medical_record`, and `send_referral`.

When the LLM calls one of these tools, execution pauses. The frontend displays an approval card showing exactly what action is being requested. The patient clicks Approve or Cancel. On approve, the tool runs and the agent continues. On cancel, the tool never executes and the model is told the action was refused.

No database write occurs until the patient explicitly approves.

---

## Tool Permission Constraints

Tools are scoped to the minimum access required for clinical triage:

- `get_patient_info` returns only clinical fields (name, conditions, medications, allergies, last visit). SSN, insurance ID, and insurance provider are stripped before the result is returned to the LLM.
- `book_appointment` validates `appointment_type` against 5 allowed values from the scheduling policy. Free-text values are rejected.
- `send_referral` validates `specialist_type` against 12 allowed values. Free-text values are rejected.
- `save_memory` truncates notes to 500 characters and rejects 15 known injection phrases before writing.
- `update_medical_record` is restricted to 7 permitted field names and 1,000-character values, preventing SQL injection via field name.
- All tools that take a `patient_id` parameter verify it matches the session patient before any database call.

---

## Patch Validation Results

All seven original attack types re-run 3+ times after hardening. Results:

| Attack Type | Runs | Result |
|---|---|---|
| RAG Poisoning | 3 | ALL BLOCKED |
| Direct Prompt Injection | 3 | ALL BLOCKED |
| Memory Poisoning | 3 | ALL BLOCKED |
| PII Exfiltration | 3 | ALL BLOCKED |
| Context Overflow | 3 | ALL BLOCKED |
| Privilege Escalation | 3 | ALL BLOCKED |
| Credential Exposure | 4 | ALL BLOCKED |

Full patch validation report: https://docs.google.com/document/d/1sxnM9VNnXAQ4Ome8qSh2sE7kiI4rzczFv_1knPqVx54/edit

---

## Getting Started

### 1. Clone

```bash
git clone https://github.com/PMAIGURU2026/mediassist.git
cd mediassist
```

### 2. Set Up a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Open `.env` and add your OpenRouter API key:

```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

Get a free key at https://openrouter.ai/keys

### 5. Run

```bash
python3 main.py
```

Open http://localhost:8000 in your browser.

### 6. Sign In

Enter any patient ID from 1 through 10. No password required.

| ID | Name | Primary Condition |
|----|------|-------------------|
| 1 | Margaret Chen | Type 2 Diabetes |
| 2 | James Okafor | Hypertension |
| 3 | Sofia Ramirez | Anxiety |
| 4 | Robert Washington | COPD |
| 5 | Priya Patel | Asthma |
| 6 | David Kim | Depression |
| 7 | Amara Johnson | Migraines |
| 8 | Carlos Mendez | Atrial Fibrillation |
| 9 | Lisa Nakamura | PCOS |
| 10 | Thomas O'Brien | Heart Failure |

---

## Running the Test Suite

The human-in-the-loop integration tests run without requiring an API call:

```bash
python3 test_hitl.py
```

Tests cover: approval intercept fires on high-stakes tools, approve path executes the tool and clears pending state, cancel path never touches the database, read-only tools pass through without a gate.

---

## Seed Log Data

To populate historical log data for observability exercises:

```bash
python3 seed_logs.py
```

Generates 80 structured log entries in `logs/requests.log`.

---

## Resetting

- Click **Reset Memory** in the chat header to clear saved session notes for the current patient.
- To fully reset the database:

```bash
rm data/patients.db && python3 main.py
```

---

## Project Structure

```
mediassist/
├── main.py              — FastAPI app, all security middleware, logging, rate limiting
├── agent.py             — LLM agent loop, system prompt, tool definitions and execution
├── database.py          — SQLite operations, memory filter, field whitelist
├── config.py            — Credentials via environment variables only
├── test_hitl.py         — Human-in-the-loop integration tests
├── seed_logs.py         — Log data generator for observability exercises
├── knowledge_base/      — Clinical reference documents (RAG source)
├── static/              — Frontend HTML with approval card UI
├── logs/                — Structured forensic request logs
└── data/                — SQLite database (created on first run)
```

---

## Requirements

- Python 3.9+
- A free OpenRouter API key (https://openrouter.ai)
