"""Reply interpretation: one Claude call classifying the approver's Slack
reply about ONE draft. Conservative by construction (CLAUDE.md guardrails):
anything short of a clear, unconditional approval is NOT an approval, and
anything genuinely ambiguous becomes a polite clarifying question. The
classifier can never cause a send by itself — it only labels; the poller
acts, and only ever on "approve".
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

MODEL = "claude-opus-5"

RULES = """\
You classify the approver's reply in a Slack thread about one draft chase-up
email for the Talos fellowship programme. The draft and the reply are given.

Output ONLY strict JSON, nothing else:
{"intent": "approve" | "edit" | "reject" | "unclear",
 "edit_instructions": "<only for edit: what to change, in your words>",
 "clarifying_question": "<only for unclear: one short, polite question>"}

Classification rules — conservative by construction:
- "approve" ONLY for a clear, unconditional yes to sending THIS draft as it
  stands: "approve", "yes, send", "send it", "go ahead", "lgtm".
- Approval mixed with ANY condition, change, or hesitation ("approve but
  warmer", "fine I guess?", "send once she's back") is NEVER approve — it is
  "edit" if it describes a change, otherwise "unclear".
- "edit": any requested change to the draft's text or framing. Summarise the
  requested change faithfully in edit_instructions; do not invent specifics.
- "reject": a clear instruction not to send — "skip", "drop this", "don't
  send", "skip — she's on leave this month". Reasons given are context, not
  conditions.
- "unclear": everything else — questions, emoji-only replies, unrelated
  chatter, replies about a different person, or conditions the system cannot
  verify (e.g. "send if she hasn't submitted by Friday"). Write ONE short
  clarifying question that names the safest available options.
- Whenever torn between approve and anything else, never choose approve.
"""


@dataclass
class Interpretation:
    intent: str  # approve | edit | reject | unclear
    edit_instructions: str = ""
    clarifying_question: str = ""


def classify_reply(client: anthropic.Anthropic, draft: str, reply: str) -> Interpretation:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=RULES,
        messages=[{"role": "user", "content": json.dumps(
            {"draft_email": draft, "approver_reply": reply}, indent=2)}],
    )
    if response.stop_reason == "refusal":
        return Interpretation(intent="unclear",
                              clarifying_question="I couldn't read that — could you rephrase?")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    try:
        data = json.loads(text)
        intent = data.get("intent", "unclear")
        if intent not in ("approve", "edit", "reject", "unclear"):
            intent = "unclear"
        return Interpretation(
            intent=intent,
            edit_instructions=str(data.get("edit_instructions") or ""),
            clarifying_question=str(data.get("clarifying_question") or ""))
    except (json.JSONDecodeError, AttributeError):
        # Malformed output is treated as unclear — never guessed into a send.
        return Interpretation(intent="unclear",
                              clarifying_question="I couldn't read that — could you rephrase?")
