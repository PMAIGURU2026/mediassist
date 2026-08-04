"""
Human-in-the-loop integration test.
Mocks the LLM so the full flow runs without an API call.
Tests: intercept → pending_action → approve → execute → cancel
"""
import json
import sys
from unittest.mock import MagicMock, patch

BASE = "http://localhost:8000"


def make_tool_response(tool_name, tool_args, pre_text=""):
    tc = MagicMock()
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(tool_args)
    tc.id = f"call_{tool_name}_test"

    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content = pre_text

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def make_text_response(text):
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = text

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def run_tests():
    import agent

    print("=" * 60)
    print("HUMAN-IN-THE-LOOP TEST SUITE")
    print("=" * 60)

    # ── Test 1: book_appointment triggers pending_action ──────────
    print("\nTest 1: book_appointment intercepted before execution")

    book_args = {"patient_id": 1, "appointment_type": "routine follow-up", "preferred_date": "2026-08-10"}
    responses = [make_tool_response("book_appointment", book_args, "I'll book that for you.")]

    with patch.object(agent.client.chat.completions, "create", side_effect=responses):
        text, tool_calls, pending = agent.run_agent(1, "book me a routine follow-up for August 10", [])

    assert pending is not None, "Expected pending_action, got None"
    assert pending["tool_name"] == "book_appointment"
    assert "pending_id" in pending
    assert "description" in pending

    pending_id = pending["pending_id"]
    print(f"  pending_action returned: YES")
    print(f"  tool_name:    {pending['tool_name']}")
    print(f"  description:  {pending['description']}")
    print(f"  pending_id:   {pending_id}")
    print(f"  pending_actions store size: {len(agent.pending_actions)}")
    print("  PASS")

    # ── Test 2: Approve executes the tool and returns response ────
    print("\nTest 2: Approve — tool executes, final response returned")

    final_responses = [make_text_response("Your appointment has been booked for August 10. Appointment ID: 1.")]

    with patch.object(agent.client.chat.completions, "create", side_effect=final_responses):
        result_text, result_tools, result_pending = agent.resume_approved_action(pending_id)

    assert result_pending is None
    assert "appointment" in result_text.lower() or "booked" in result_text.lower() or "august" in result_text.lower()
    assert any(tc["tool_name"] == "book_appointment" for tc in result_tools)
    assert pending_id not in agent.pending_actions

    print(f"  tool executed:  {result_tools[0]['tool_name']}")
    print(f"  tool output:    {result_tools[0]['tool_output_summary'][:80]}")
    print(f"  agent response: {result_text[:80]}")
    print(f"  pending cleared from store: {pending_id not in agent.pending_actions}")
    print("  PASS")

    # ── Test 3: Cancel returns graceful refusal ───────────────────
    print("\nTest 3: Cancel — tool never executes, graceful refusal returned")

    responses2 = [make_tool_response("book_appointment", book_args)]
    with patch.object(agent.client.chat.completions, "create", side_effect=responses2):
        _, _, pending2 = agent.run_agent(1, "book me an urgent appointment tomorrow", [])

    pending_id2 = pending2["pending_id"]
    cancel_response = [make_text_response("No problem — I've cancelled the booking request. Let me know if you need anything else.")]

    with patch.object(agent.client.chat.completions, "create", side_effect=cancel_response):
        cancel_text, cancel_tools, cancel_pending = agent.cancel_pending_action(pending_id2)

    assert cancel_pending is None
    assert pending_id2 not in agent.pending_actions
    assert len(cancel_tools) == 0

    print(f"  appointment booked?   NO (cancelled before execution)")
    print(f"  agent response:       {cancel_text[:80]}")
    print(f"  pending cleared:      {pending_id2 not in agent.pending_actions}")
    print("  PASS")

    # ── Test 4: send_referral also triggers pending_action ────────
    print("\nTest 4: send_referral intercepted (not just booking)")

    referral_args = {"patient_id": 1, "specialist_type": "cardiology", "reason": "chest pain evaluation"}
    responses3 = [make_tool_response("send_referral", referral_args)]

    with patch.object(agent.client.chat.completions, "create", side_effect=responses3):
        _, _, pending3 = agent.run_agent(1, "I need a cardiology referral", [])

    assert pending3 is not None
    assert pending3["tool_name"] == "send_referral"
    print(f"  tool_name:    {pending3['tool_name']}")
    print(f"  description:  {pending3['description']}")
    print("  PASS")

    # ── Test 5: get_patient_info does NOT trigger pending ─────────
    print("\nTest 5: get_patient_info passes through without approval gate")

    info_args = {"patient_id": 1}
    responses4 = [
        make_tool_response("get_patient_info", info_args),
        make_text_response("Here is your record: you have Type 2 Diabetes.")
    ]

    with patch.object(agent.client.chat.completions, "create", side_effect=responses4):
        text4, tools4, pending4 = agent.run_agent(1, "show me my record", [])

    assert pending4 is None, f"Expected no pending, got {pending4}"
    assert any(tc["tool_name"] == "get_patient_info" for tc in tools4)
    print(f"  pending_action: None (correct — read-only tool, no gate needed)")
    print(f"  tool executed immediately: {tools4[0]['tool_name']}")
    print("  PASS")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ALL 5 TESTS PASSED")
    print("=" * 60)
    print("\nFlow confirmed:")
    print("  book_appointment  → INTERCEPTED  (approval required)")
    print("  send_referral     → INTERCEPTED  (approval required)")
    print("  get_patient_info  → EXECUTES     (read-only, no gate)")
    print("  Approve path      → tool runs, response returned")
    print("  Cancel path       → tool never runs, graceful refusal")


if __name__ == "__main__":
    run_tests()
