"""Deterministic, offline demonstration coach.

This is deliberately labelled rule-based. It reads the same evidence the real
provider would receive and produces the same validated schema, but it makes no
network calls and never pretends to be a language model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .base import AssistantRequest, CoachRequest, EvidenceItem, ProviderDescriptor

DEMO_LIMITATION = (
    "Demo coach: deterministic text patterns, not a language model. It reads only "
    "the selected text, cannot hear tone, and cannot establish the customer's intent."
)


@dataclass(frozen=True)
class _Turn:
    item: EvidenceItem
    text: str


def _turn(item: EvidenceItem) -> _Turn:
    combined = item.original_text
    if item.translation:
        combined += " " + item.translation
    return _Turn(item=item, text=re.sub(r"\s+", " ", combined.lower()))


def _snippet(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


def _quoted(text: str) -> str:
    snippet = _snippet(text)
    if snippet.endswith((".", "?", "!", "\u2026")):
        return snippet
    return snippet + "."


_CATEGORY_CUES = (
    ("security", (
        "security review", "security", "data residency", "soc 2", "soc2",
        "data processing agreement", "dpa", "sso", "compliance",
    )),
    ("billing", (
        "mid-cycle", "invoice", "contract", "billing", "proration", "prorated",
    )),
    ("price", (
        "price", "pricing", "expensive", "cost", "budget", "precio", "cuesta",
        "prix", "co\u00fbt", "discount", "better price",
    )),
    ("adoption", (
        "team will use", "nobody logged", "logged into", "adoption", "use it",
        "usage", "not sure the team", "confusing for", "onboarding was confusing",
    )),
    ("training", (
        "deployment", "deploy", "training", "rollout", "onboarding", "stores",
        "store managers",
    )),
    ("integration", (
        "integration", "integrate", "billing system", "still included",
        "not clear",
    )),
)


def _category_for(text: str) -> str | None:
    for category, cues in _CATEGORY_CUES:
        if any(cue in text for cue in cues):
            return category
    return None


def _is_question(turn: _Turn) -> bool:
    if "?" in turn.item.original_text or (turn.item.translation and "?" in turn.item.translation):
        return True
    text = turn.text
    if re.match(r"^(what|how|when|where|who|why|can|could|would|will|do|does|is|are|should|pouvez|pourriez|qu\u00e9|que|cu\u00e1ndo|qui\u00e9n)\b", text):
        return True
    return any(piece in text for piece in (
        "need to know", "we need details", "need details", "not clear",
        "can you confirm", "can you send", "could you", "can you share",
    ))


_DEFERRAL_MARKERS = (
    "looking at it", "figure something out", "let me check", "i'd have to check",
    "have to check", "not sure", "probably", "i'll try", "i'll ask", "ask around",
    "behind", "soon", "something", "depending", "i believe", "pretty sure",
    "we'll get back", "get back to you", "ask the team",
)
_VAGUE_MARKERS = (
    "soon", "some materials", "something", "stuff", "a few weeks", "probably",
    "pretty sure", "i believe", "maybe", "around", "depending", "figure something out",
    "looking at it", "a lot", "asap", "later", "big number", "worth it", "i'll try",
    "get back", "set it up",
)
_OVERCLAIM_MARKERS = (
    "we're aligned", "we are aligned", "so we're aligned", "perfect", "sounds good",
    "you'll agree", "you will agree",
)
_CONCRETE_MARKERS = (
    "by monday", "by tuesday", "by wednesday", "by thursday", "by friday",
    "by end of day", "by tomorrow", "send you the", "i will send", "i'll send the",
    "i'll send a", "i'll send an", "named owner", "signed", "attached",
)


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _evidence_refs(items) -> list[str]:
    return [item.ref for item in items]


def _objection_text(category: str) -> tuple[str, str, str]:
    if category == "price":
        return (
            "The customer names the annual price as a concern before discussing anything else.",
            "An unaddressed price concern can stall the decision even when the proposal is strong.",
            "Acknowledge the concern before defending value: \"The annual number is a real commitment. "
            "Which part is hardest to justify for finance: the total, the timing, or the comparison to "
            "what you use today?\"",
        )
    if category == "adoption":
        return (
            "The customer says the team may not use the product and points to low adoption last time.",
            "Adoption risk is a delivery objection; promising materials without understanding the "
            "previous rollout may not reduce it.",
            "Ask about the previous rollout before proposing training: \"Last time, what got in the way "
            "of people logging in, and which team would need to see value first?\"",
        )
    if category == "security":
        return (
            "The customer asks for security-review specifics such as data residency, SSO, or documents.",
            "Security review is often a gating workstream; an informal answer can leave the customer "
            "unable to move forward.",
            "Treat the review as a concrete workstream: \"I'll confirm the data-residency and SSO answers "
            "in writing and send the SOC 2 report and DPA by [specific date]. Who on your security team "
            "should I coordinate with?\"",
        )
    if category == "billing":
        return (
            "The customer asks how the current contract and next invoice are affected by a switch.",
            "Billing mechanics can block finance approval even when the product decision is positive.",
            "Confirm the commercial detail in writing: \"I don't want to guess about mid-cycle billing. "
            "I'll confirm the proration and invoice timing before you take this to finance.\"",
        )
    if category == "integration":
        return (
            "The customer asks whether the billing-system integration is still included and says the "
            "previous proposal was unclear.",
            "An unresolved scope question can turn into a delivery dispute after signature.",
            "Make the scope explicit: \"I'll send the current scope section that names the billing "
            "integration, and flag anything that changed since the last proposal.\"",
        )
    if category == "training":
        return (
            "The customer raises onboarding, training, or deployment as a practical concern.",
            "A deployment concern needs a plan the customer can review, not a general reassurance.",
            "Replace the general answer with a reviewable plan: \"I'll map the rollout, including training "
            "time and store-manager responsibilities, so your operations lead can review it.\"",
        )
    return (
        "The customer raises a concern in this utterance.",
        "An unclear concern is hard to resolve; the representative may solve the wrong problem.",
        "Ask one open question before responding to the concern.",
    )


def _question_alternative(text: str) -> str:
    if any(word in text for word in ("security", "soc", "dpa", "residency", "sso", "documents")):
        return ("I'll own this: I'll send the SOC 2 report and DPA by [specific date], or tell you clearly "
                "that we cannot. Who is the named security contact on your side?")
    if any(word in text for word in ("integration", "billing system", "still included", "not clear")):
        return ("I'll resolve the scope question in writing: I'll send the current scope section that "
                "names the billing integration by [specific date], and flag anything that changed since "
                "the last proposal.")
    if any(word in text for word in ("deployment", "training", "onboarding", "stores", "rollout")):
        return ("I'll send a deployment plan for [number] stores by [specific date], covering training and "
                "store-manager responsibilities, and we'll review it with your operations lead.")
    if any(word in text for word in ("contract", "invoice", "billing", "mid-cycle", "proration")):
        return ("I don't want to leave this as \"the team is looking at it.\" I'll confirm the proration "
                "and invoice timing in writing and send it by [specific date]. Who on your side should "
                "receive it?")
    if any(word in text for word in ("date", "when", "contact", "owner")):
        return ("I'll confirm the named owner and the date in writing today. If I cannot confirm the date, "
                "I'll say so and give you the next checkpoint.")
    return ("Let me answer that directly instead of deferring: [the answer]. I'll confirm it in writing "
            "by [specific date].")


def _vague_alternative(text: str) -> str:
    if any(word in text for word in ("materials", "adoption", "training")):
        return ("Name the deliverable, owner, and date: \"I'll send the onboarding plan and adoption "
                "checklist by [specific date]. I'll own it, and we'll review it on a 15-minute call.\"")
    if any(word in text for word in ("contract", "invoice", "billing", "proration")):
        return ("I'll send the written proration terms and invoice timing by [specific date], with the "
                "exact effective date.")
    if any(word in text for word in ("security", "soc", "dpa", "documents")):
        return ("I'll send the SOC 2 report and DPA by [specific date], and name the security contact in "
                "the same message.")
    if any(word in text for word in ("deployment", "stores", "rollout", "plan")):
        return ("I'll send a dated deployment plan for [number] stores by [specific date], including "
                "training and owner responsibilities.")
    return ("Replace the vague phrase with a deliverable, an owner, and a date: \"I'll send [specific "
            "deliverable] by [specific date].\"")


def _discovery_alternative(category: str | None) -> str:
    if category == "price":
        return ("Before defending value, ask what is behind the price concern: \"Which part is hardest to "
                "justify for finance: the total, the timing, or the comparison to what you use today?\"")
    if category == "adoption":
        return ("Ask what happened in the previous rollout: \"What made it hard for people to log in last "
                "time, and which team needs to see value first this time?\"")
    if category == "security":
        return ("Ask what the security review needs to clear: \"Which documents or controls are gating "
                "your review, and who signs off?\"")
    if category == "billing":
        return ("Ask which billing detail matters most: \"Is the concern the effective date, the invoice "
                "timing, or how the remaining contract value is handled?\"")
    if category == "training":
        return ("Ask what a workable rollout looks like: \"What would store managers need to see in the "
                "first two weeks for this to feel manageable?\"")
    if category == "integration":
        return ("Ask which system and scope must be confirmed: \"Which billing workflow are you checking, "
                "and what would 'included' need to cover?\"")
    return "Ask one open question about the concern before offering a solution."


def _next_step_alternative(text: str) -> str:
    if "aligned" in text or "value" in text:
        return ("Close with a precise recap and one owned action: \"To be precise, I'll send [deliverable] "
                "by [specific date]. You'll review it with [name/team], and we have not treated that as "
                "approval yet.\"")
    return ("Close with a recap and one owned action: \"I'll send [deliverable] by [specific date]. "
            "You'll review it with [name/team], and we'll confirm the next checkpoint then.\"")


class MockCoachProvider:
    descriptor = ProviderDescriptor(
        mode="mock",
        name="Demo coach (rule-based)",
        model="rules-v1",
    )

    def _insight(
        self,
        *,
        kind: str,
        title: str,
        refs: list[str],
        observation: str,
        why: str,
        alternative: str,
        limitations: str,
        action: str,
        confidence: str,
    ) -> dict:
        return {
            "type": kind,
            "title": title,
            "evidence_refs": refs,
            "observation": observation,
            "why_it_matters": why,
            "proposed_alternative": alternative,
            "limitations": limitations,
            "recommended_action": action,
            "confidence": confidence,
        }

    def generate_coaching(self, request: CoachRequest) -> str:
        turns = [_turn(item) for item in request.evidence]
        customers = [turn for turn in turns if turn.item.speaker == "customer"]
        reps = [turn for turn in turns if turn.item.speaker == "rep"]
        insights: list[dict] = []
        used_rep_refs: set[str] = set()

        objections: list[tuple[_Turn, str]] = []
        seen_categories: set[str] = set()
        for turn in customers:
            category = _category_for(turn.text)
            if not category or category in seen_categories:
                continue
            if _is_question(turn) and category not in ("security", "training", "integration"):
                continue
            objections.append((turn, category))
            seen_categories.add(category)
            if len(objections) >= 2:
                break

        for turn, category in objections:
            observation, why, alternative = _objection_text(category)
            insights.append(self._insight(
                kind="objection",
                title=f"{category.capitalize()} concern raised",
                refs=[turn.item.ref],
                observation=observation,
                why=why,
                alternative=alternative,
                limitations=(
                    "The concern is explicit in the words shown; its relative importance to the "
                    "customer is not established."
                ),
                action="Ask one open question about this concern before presenting a solution.",
                confidence="high" if category != "general" else "medium",
            ))

        unanswered = 0
        for index, turn in enumerate(turns):
            if turn.item.speaker != "customer" or not _is_question(turn):
                continue
            next_rep = next(
                (candidate for candidate in turns[index + 1:] if candidate.item.speaker == "rep"),
                None,
            )
            if next_rep is not None and not _has_any(next_rep.text, _DEFERRAL_MARKERS):
                continue
            refs = [turn.item.ref] + ([next_rep.item.ref] if next_rep else [])
            if next_rep:
                used_rep_refs.add(next_rep.item.ref)
            observation = "The customer's question is left without a clear answer in this selected segment."
            if next_rep:
                observation = (
                    "The customer asks a direct question, and the next response defers rather than "
                    f"answers it: \"{_quoted(next_rep.item.original_text)}\""
                )
            insights.append(self._insight(
                kind="unanswered_question",
                title="Question left open",
                refs=refs,
                observation=observation,
                why=(
                    "An open question becomes a blocker the customer has to chase. A dated commitment "
                    "is easier to trust than a promise to look into it."
                ),
                alternative=_question_alternative(turn.text),
                limitations=(
                    "The question appears unanswered within this selected segment; an answer may exist "
                    "elsewhere in the call."
                ),
                action="Answer the question or give a dated commitment before moving on.",
                confidence="high",
            ))
            unanswered += 1
            if unanswered >= 3:
                break

        if objections:
            first_customer, first_category = objections[0]
            try:
                customer_index = turns.index(first_customer)
            except ValueError:
                customer_index = -1
            next_rep = next(
                (candidate for candidate in turns[customer_index + 1:] if candidate.item.speaker == "rep"),
                None,
            ) if customer_index >= 0 else None
            if next_rep is not None and "?" not in next_rep.item.original_text:
                insights.append(self._insight(
                    kind="discovery",
                    title="Concern met with a statement, not a question",
                    refs=[first_customer.item.ref, next_rep.item.ref],
                    observation=(
                        "The representative responds to the customer's concern with a statement rather "
                        f"than a question: \"{_quoted(next_rep.item.original_text)}\""
                    ),
                    why=(
                        "A value claim or reassurance can miss the actual priority behind the concern. "
                        "One discovery question would show what the customer is evaluating."
                    ),
                    alternative=_discovery_alternative(first_category),
                    limitations=(
                        "This is a coaching hypothesis about the response, not a claim about the "
                        "customer's motive."
                    ),
                    action="Ask one open question before presenting the value case.",
                    confidence="medium",
                ))
                used_rep_refs.add(next_rep.item.ref)

        vague_candidates = []
        for turn in reps:
            if turn.item.ref in used_rep_refs:
                continue
            score = sum(1 for marker in _VAGUE_MARKERS if marker in turn.text)
            if score:
                vague_candidates.append((score, turn))
        vague_candidates.sort(key=lambda pair: -pair[0])
        for _, turn in vague_candidates[:2]:
            insights.append(self._insight(
                kind="ambiguity",
                title="Vague commitment",
                refs=[turn.item.ref],
                observation=(
                    f"The response leaves the deliverable or timing unspecified: "
                    f"\"{_quoted(turn.item.original_text)}\""
                ),
                why=(
                    "Vague commitments are difficult for the customer to plan around and can sound "
                    "evasive even when the intent is helpful."
                ),
                alternative=_vague_alternative(turn.text),
                limitations=(
                    "The vagueness is visible in the words; the customer's interpretation of it is not known."
                ),
                action="Name the deliverable, the owner, and a date before ending the point.",
                confidence="high",
            ))
            used_rep_refs.add(turn.item.ref)

        if reps:
            last_rep = reps[-1]
            last_text = last_rep.text
            already_used = last_rep.item.ref in used_rep_refs
            if (_has_any(last_text, _OVERCLAIM_MARKERS) or _has_any(last_text, _VAGUE_MARKERS)) and (
                not already_used or _has_any(last_text, _OVERCLAIM_MARKERS)
            ):
                overclaimed = _has_any(last_text, _OVERCLAIM_MARKERS)
                observation = (
                    "The segment closes with a general promise rather than a named deliverable, owner, "
                    f"and date: \"{_quoted(last_rep.item.original_text)}\""
                )
                if overclaimed:
                    observation = (
                        "The representative uses alignment language while the customer has not approved "
                        f"anything: \"{_quoted(last_rep.item.original_text)}\""
                    )
                insights.append(self._insight(
                    kind="next_step",
                    title="Close needs a precise next step",
                    refs=[last_rep.item.ref],
                    observation=observation,
                    why=(
                        "A vague close lets the next step slip. Claiming alignment too early can also "
                        "close off concerns the customer has not resolved."
                    ),
                    alternative=_next_step_alternative(last_text),
                    limitations=(
                        "This checks the wording of the close, not whether an agreement exists."
                    ),
                    action="Send a written recap with the action, owner, and date; do not record approval.",
                    confidence="high",
                ))

        order = {item.ref: index for index, item in enumerate(request.evidence)}
        type_order = {"objection": 0, "unanswered_question": 1, "ambiguity": 2, "discovery": 3, "next_step": 4}
        insights.sort(key=lambda insight: (
            order.get(insight["evidence_refs"][0], 999),
            type_order.get(insight["type"], 9),
        ))
        insights = insights[:8]

        if not insights:
            summary = (
                "No coaching issue crossed the demo rules' thresholds in this selection. That is not "
                "proof the exchange was effective; it means the rule-based demo found nothing to flag."
            )
        else:
            parts = []
            if objections:
                parts.append(f"{len(objections)} explicit concern(s)")
            if unanswered:
                parts.append(f"{unanswered} question(s) left without a clear answer")
            if any(item["type"] == "ambiguity" for item in insights):
                count = sum(1 for item in insights if item["type"] == "ambiguity")
                parts.append(f"{count} vague commitment(s)")
            if any(item["type"] == "discovery" for item in insights):
                parts.append("at least one response that would benefit from discovery")
            if any(item["type"] == "next_step" for item in insights):
                parts.append("a close that needs a concrete owner and date")
            summary = "In this segment, the demo rules found " + ", ".join(parts) + "."

        return json.dumps({
            "summary": summary,
            "limitations": DEMO_LIMITATION,
            "insights": insights,
        }, ensure_ascii=False)

    def generate_answer(self, request: AssistantRequest) -> str:
        question = request.question.lower()
        evidence = request.evidence
        customer = next((item for item in evidence if item.speaker == "customer"), None)
        primary = customer or evidence[0]
        category = _category_for(
            (primary.original_text + " " + (primary.translation or "")).lower()
        )
        ref = primary.ref
        limitation = (
            "The assistant sees only the selected text. It cannot establish tone, emotion, hidden "
            "intent, or what happened outside the selected evidence."
        )

        if any(word in question for word in ("mean", "intent", "understand", "interpret")):
            answer = (
                f'The transcript records the customer saying: "{primary.original_text}" '
                f"[{ref}]. The text alone does not establish what they intended; treat this as a "
                "stated concern to verify, not a confirmed motive."
            )
            refs = [ref]
        elif any(word in question for word in ("ask", "question", "discover", "clarify")):
            answer = (
                "A useful discovery question here would be: "
                f"{_discovery_alternative(category)} [{ref}]"
            )
            refs = [ref]
        elif any(word in question for word in ("next", "step", "follow", "close")):
            answer = (
                "Do not treat this as agreement. Close with one owned action: "
                f"{_next_step_alternative('')} [{ref}]"
            )
            refs = [ref]
        elif any(word in question for word in ("say", "respond", "reply", "phrase", "alternative", "better")):
            if category:
                _, _, alternative = _objection_text(category)
            else:
                alternative = _vague_alternative(primary.text)
            answer = (
                f"A clearer response would be: {alternative} [{ref}] It addresses the wording in the "
                "evidence without inventing a commitment."
            )
            refs = [ref]
        elif "summar" in question:
            lines = []
            for item in evidence:
                speaker = "Customer" if item.speaker == "customer" else "Representative"
                lines.append(f"{speaker}: \"{_snippet(item.original_text)}\" [{item.ref}]")
            answer = "Selected evidence: " + " ".join(lines) + (
                " This is a transcript summary, not a conclusion about intent."
            )
            refs = [item.ref for item in evidence]
        else:
            answer = (
                f"The selected evidence says: \"{primary.original_text}\" [{ref}]. I can only ground "
                "an answer in those words. A useful next question would be: "
                f"{_discovery_alternative(category)}"
            )
            refs = [ref]

        return json.dumps({
            "answer": answer,
            "evidence_refs": refs,
            "limitations": limitation,
        }, ensure_ascii=False)

    def test_connection(self) -> dict:
        return {
            "ok": True,
            "message": "Demo coach is local and ready. No network request was made.",
            "network": False,
        }



