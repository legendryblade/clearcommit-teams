"""Repository operations over the local SQLite workspace."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .db import Database, dumps, loads
from .errors import ConflictError, NotFoundError, ValidationError
from .models import (
    INSIGHT_TYPE_LABELS,
    ensure_reviewer,
    evidence_ref,
    elapsed_time_label,
    language_pair_label,
    new_id,
    normalize_language,
    now_utc,
    parse_playbook_overrides,
    parse_session_input,
    parse_utterance_input,
    today_local_iso,
)


def _session_payload(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "customer_name": row["customer_name"],
        "company": row["company"],
        "rep_name": row["rep_name"],
        "customer_language": row["customer_language"],
        "rep_language": row["rep_language"],
        "language_pair": language_pair_label(row["customer_language"], row["rep_language"]),
        "occurred_on": row["occurred_on"],
        "source": row["source"],
        "is_sample": bool(row["is_sample"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _utterance_payload(row) -> dict:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "seq": int(row["seq"]),
        "ref": evidence_ref(row["seq"]),
        "speaker": row["speaker"],
        "original_text": row["original_text"],
        "translation": row["translation"],
        "language": row["language"],
        "display_time": row["display_time"],
        "created_at": row["created_at"],
    }


def _evidence_payload(row) -> dict:
    return {
        "utterance_id": row["utterance_id"],
        "ref": row["ref"],
        "quote": row["quote"],
        "speaker": row["speaker"],
        "spoken_at": row["spoken_at"],
        "language": row["language"],
        "translation": row["translation"],
    }


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Sessions
    # ------------------------------------------------------------------ #
    def list_sessions(self) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT s.*, "
                "(SELECT COUNT(*) FROM utterances u WHERE u.session_id = s.id) AS utterance_count, "
                "(SELECT COUNT(*) FROM insights i WHERE i.session_id = s.id) AS insight_count, "
                "(SELECT COUNT(*) FROM playbook_entries p WHERE p.session_id = s.id) AS playbook_count, "
                "(SELECT COUNT(*) FROM playbook_entries p WHERE p.session_id = s.id AND p.status = 'approved') AS playbook_approved_count "
                "FROM sessions s ORDER BY s.occurred_on DESC, s.created_at DESC"
            ).fetchall()
        out = []
        for row in rows:
            item = _session_payload(row)
            item.update({
                "utterance_count": int(row["utterance_count"]),
                "insight_count": int(row["insight_count"]),
                "playbook_count": int(row["playbook_count"]),
                "playbook_approved_count": int(row["playbook_approved_count"]),
            })
            out.append(item)
        return out

    def create_session(self, data: Any, *, source: str = "manual", utterances: Iterable[dict] | None = None) -> dict:
        session = parse_session_input(data)
        session_id = new_id("s")
        created_at = now_utc()
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO sessions(id, title, customer_name, company, rep_name, "
                "customer_language, rep_language, occurred_on, source, is_sample, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (
                    session_id, session["title"], session["customer_name"],
                    session["company"], session["rep_name"], session["customer_language"],
                    session["rep_language"], session["occurred_on"], source,
                    created_at, created_at,
                ),
            )
            seq = 0
            for raw in utterances or []:
                parsed = parse_utterance_input(raw)
                seq += 1
                conn.execute(
                    "INSERT INTO utterances(id, session_id, seq, speaker, original_text, translation, "
                    "language, display_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id("u"), session_id, seq, parsed["speaker"],
                        parsed["original_text"], parsed["translation"], parsed["language"],
                        parsed["display_time"] or elapsed_time_label(created_at),
                        created_at,
                    ),
                )
            if seq:
                conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now_utc(), session_id))
        return self.get_session(session_id)

    def get_session(self, session_id: Any) -> dict:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValidationError("A conversation ID is required.")
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id.strip(),)).fetchone()
            if not row:
                raise NotFoundError("That conversation was not found.")
            sessions = _session_payload(row)
            utterances = [
                _utterance_payload(item)
                for item in conn.execute(
                    "SELECT * FROM utterances WHERE session_id = ? ORDER BY seq", (session_id,)
                ).fetchall()
            ]
            insight_count = int(conn.execute(
                "SELECT COUNT(*) FROM insights WHERE session_id = ?", (session_id,)
            ).fetchone()[0])
            playbook_count = int(conn.execute(
                "SELECT COUNT(*) FROM playbook_entries WHERE session_id = ?", (session_id,)
            ).fetchone()[0])
        return {
            "session": sessions,
            "utterances": utterances,
            "insight_count": insight_count,
            "playbook_count": playbook_count,
        }

    def add_utterance(self, session_id: Any, data: Any) -> dict:
        if not isinstance(session_id, str) or not session_id:
            raise ValidationError("A conversation ID is required.")
        parsed = parse_utterance_input(data)
        created_at = now_utc()
        with self.db.connection() as conn:
            session = conn.execute(
                "SELECT id, created_at FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                raise NotFoundError("That conversation was not found.")
            seq = int(conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM utterances WHERE session_id = ?", (session_id,)
            ).fetchone()[0]) + 1
            utterance_id = new_id("u")
            conn.execute(
                "INSERT INTO utterances(id, session_id, seq, speaker, original_text, translation, "
                "language, display_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    utterance_id, session_id, seq, parsed["speaker"],
                    parsed["original_text"], parsed["translation"], parsed["language"],
                    parsed["display_time"] or elapsed_time_label(session["created_at"]),
                    created_at,
                ),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (created_at, session_id))
            row = conn.execute("SELECT * FROM utterances WHERE id = ?", (utterance_id,)).fetchone()
        return _utterance_payload(row)

    def add_utterances(self, session_id: Any, rows: Iterable[Any]) -> dict:
        """Append several finalized utterances in one transaction."""
        if not isinstance(session_id, str) or not session_id:
            raise ValidationError("A conversation ID is required.")
        parsed_rows = [parse_utterance_input(row) for row in rows]
        if not parsed_rows:
            raise ValidationError("There are no transcript lines to import.")
        created_at = now_utc()
        with self.db.connection() as conn:
            session = conn.execute(
                "SELECT id, created_at FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                raise NotFoundError("That conversation was not found.")
            seq = int(conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM utterances WHERE session_id = ?", (session_id,)
            ).fetchone()[0])
            for parsed in parsed_rows:
                seq += 1
                conn.execute(
                    "INSERT INTO utterances(id, session_id, seq, speaker, original_text, translation, "
                    "language, display_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id("u"), session_id, seq, parsed["speaker"],
                        parsed["original_text"], parsed["translation"], parsed["language"],
                        parsed["display_time"] or elapsed_time_label(session["created_at"]),
                        created_at,
                    ),
                )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (created_at, session_id))
        return self.get_session(session_id)

    def list_utterances(self, session_id: str) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM utterances WHERE session_id = ? ORDER BY seq", (session_id,)
            ).fetchall()
        return [_utterance_payload(row) for row in rows]

    def resolve_evidence(self, session_id: Any, refs: list[str]) -> list[dict]:
        if not isinstance(session_id, str) or not session_id:
            raise ValidationError("A conversation ID is required.")
        if not refs:
            return []
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM utterances WHERE session_id = ? ORDER BY seq", (session_id,)
            ).fetchall()
        by_ref = {evidence_ref(row["seq"]): row for row in rows}
        missing = [ref for ref in refs if ref not in by_ref]
        if missing:
            raise ValidationError(
                "One or more selected utterances are no longer in this conversation.",
                detail={"missing": missing},
            )
        return [_utterance_payload(by_ref[ref]) for ref in refs]

    # ------------------------------------------------------------------ #
    # Analysis and insights
    # ------------------------------------------------------------------ #
    def save_analysis(
        self,
        *,
        session_id: str,
        provider_mode: str,
        provider_name: str,
        model: str,
        evidence: list[dict],
        summary: str,
        limitations: str,
        duration_ms: int,
        insights: list[dict],
    ) -> dict:
        run_id = new_id("run")
        created_at = now_utc()
        evidence_key = ",".join(item["ref"] for item in evidence)
        with self.db.connection() as conn:
            session = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not session:
                raise NotFoundError("That conversation was not found.")
            # Re-analyzing the same evidence replaces the prior run for that
            # evidence set instead of stacking duplicate insights in the queue.
            conn.execute(
                "DELETE FROM analysis_runs WHERE session_id = ? AND evidence_key = ? AND provider_mode = ?",
                (session_id, evidence_key, provider_mode),
            )
            conn.execute(
                "INSERT INTO analysis_runs(id, session_id, provider_mode, provider_name, model, "
                "evidence_key, summary, limitations, duration_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, session_id, provider_mode, provider_name, model,
                    evidence_key, summary, limitations, int(duration_ms), created_at,
                ),
            )
            by_ref = {item["ref"]: item for item in evidence}
            for order, insight in enumerate(insights):
                insight_id = new_id("ins")
                conn.execute(
                    "INSERT INTO insights(id, run_id, session_id, type, title, observation, "
                    "why_it_matters, proposed_alternative, limitations, recommended_action, "
                    "confidence, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        insight_id, run_id, session_id, insight["type"], insight["title"],
                        insight["observation"], insight["why_it_matters"],
                        insight["proposed_alternative"], insight["limitations"],
                        insight["recommended_action"], insight["confidence"], order, created_at,
                    ),
                )
                for ref in insight["evidence_refs"]:
                    item = by_ref[ref]
                    conn.execute(
                        "INSERT INTO insight_evidence(insight_id, utterance_id, ref, quote, "
                        "speaker, spoken_at, language, translation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            insight_id, item["id"], item["ref"], item["original_text"],
                            item["speaker"], item["display_time"], item["language"], item["translation"],
                        ),
                    )
        return {
            "run": {
                "id": run_id,
                "session_id": session_id,
                "provider_mode": provider_mode,
                "provider_name": provider_name,
                "model": model,
                "summary": summary,
                "limitations": limitations,
                "duration_ms": int(duration_ms),
                "evidence_refs": [item["ref"] for item in evidence],
                "created_at": created_at,
            },
            "insights": self.list_insights(session_id, run_id=run_id),
        }

    def _insight_from_row(self, conn, row) -> dict:
        evidence = [
            _evidence_payload(item)
            for item in conn.execute(
                "SELECT * FROM insight_evidence WHERE insight_id = ? ORDER BY ref", (row["id"],)
            ).fetchall()
        ]
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "session_id": row["session_id"],
            "type": row["type"],
            "type_label": INSIGHT_TYPE_LABELS.get(row["type"], row["type"]),
            "title": row["title"],
            "observation": row["observation"],
            "why_it_matters": row["why_it_matters"],
            "proposed_alternative": row["proposed_alternative"],
            "limitations": row["limitations"],
            "recommended_action": row["recommended_action"],
            "confidence": row["confidence"],
            "evidence": evidence,
            "evidence_refs": [item["ref"] for item in evidence],
            "provider_mode": row["provider_mode"],
            "provider_name": row["provider_name"],
            "model": row["model"],
            "run_summary": row["summary"],
            "run_limitations": row["limitations"],
            "created_at": row["created_at"],
        }

    def list_insights(self, session_id: str | None = None, *, run_id: str | None = None) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if session_id:
            clauses.append("i.session_id = ?")
            params.append(session_id)
        if run_id:
            clauses.append("i.run_id = ?")
            params.append(run_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT i.*, r.provider_mode, r.provider_name, r.model, r.summary, r.limitations AS run_limitations "
                f"FROM insights i JOIN analysis_runs r ON r.id = i.run_id {where} "
                "ORDER BY i.created_at DESC, i.sort_order ASC",
                params,
            ).fetchall()
            insights = [self._insight_from_row(conn, row) for row in rows]
        # Keep the newest insight when overlapping analysis runs produced the
        # same observation about the same evidence.
        deduped = []
        seen = set()
        for insight in insights:
            key = (
                insight["type"],
                tuple(sorted(insight["evidence_refs"])),
                re.sub(r"\s+", " ", insight["observation"].strip().lower()),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(insight)
        return deduped

    def get_insight(self, insight_id: Any) -> dict:
        if not isinstance(insight_id, str) or not insight_id:
            raise ValidationError("An insight ID is required.")
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT i.*, r.provider_mode, r.provider_name, r.model, r.summary, "
                "r.limitations AS run_limitations FROM insights i "
                "JOIN analysis_runs r ON r.id = i.run_id WHERE i.id = ?",
                (insight_id,),
            ).fetchone()
            if not row:
                raise NotFoundError("That coaching insight was not found.")
            return self._insight_from_row(conn, row)

    # ------------------------------------------------------------------ #
    # Grounded assistant notes
    # ------------------------------------------------------------------ #
    def save_assistant_note(
        self,
        *,
        session_id: str,
        question: str,
        answer: str,
        limitations: str,
        provider_mode: str,
        provider_name: str,
        model: str,
        evidence: list[dict],
    ) -> dict:
        note_id = new_id("note")
        created_at = now_utc()
        with self.db.connection() as conn:
            if not conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone():
                raise NotFoundError("That conversation was not found.")
            conn.execute(
                "INSERT INTO assistant_notes(id, session_id, question, answer, limitations, "
                "provider_mode, provider_name, model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note_id, session_id, question, answer, limitations,
                    provider_mode, provider_name, model, created_at,
                ),
            )
            by_ref = {item["ref"]: item for item in evidence}
            for ref in sorted(by_ref):
                item = by_ref[ref]
                conn.execute(
                    "INSERT INTO assistant_note_evidence(note_id, utterance_id, ref, quote, speaker, "
                    "spoken_at, language, translation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        note_id, item["id"], item["ref"], item["original_text"],
                        item["speaker"], item["display_time"], item["language"], item["translation"],
                    ),
                )
        return self.get_assistant_note(note_id)

    def _assistant_note_from_row(self, conn, row) -> dict:
        evidence = [
            _evidence_payload(item)
            for item in conn.execute(
                "SELECT * FROM assistant_note_evidence WHERE note_id = ? ORDER BY ref", (row["id"],)
            ).fetchall()
        ]
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "question": row["question"],
            "answer": row["answer"],
            "limitations": row["limitations"],
            "provider_mode": row["provider_mode"],
            "provider_name": row["provider_name"],
            "model": row["model"],
            "evidence": evidence,
            "evidence_refs": [item["ref"] for item in evidence],
            "created_at": row["created_at"],
        }

    def get_assistant_note(self, note_id: str) -> dict:
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM assistant_notes WHERE id = ?", (note_id,)).fetchone()
            if not row:
                raise NotFoundError("That assistant note was not found.")
            return self._assistant_note_from_row(conn, row)

    def list_assistant_notes(self, session_id: str) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM assistant_notes WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            return [self._assistant_note_from_row(conn, row) for row in rows]

    # ------------------------------------------------------------------ #
    # Playbook
    # ------------------------------------------------------------------ #
    def _playbook_row_to_payload(self, conn, row) -> dict:
        reviews = [
            {
                "id": item["id"],
                "action": item["action"],
                "reviewer": item["reviewer"],
                "note": item["note"],
                "created_at": item["created_at"],
            }
            for item in conn.execute(
                "SELECT * FROM playbook_reviews WHERE entry_id = ? ORDER BY created_at ASC",
                (row["id"],),
            ).fetchall()
        ]
        return {
            "id": row["id"],
            "insight_id": row["insight_id"],
            "session_id": row["session_id"],
            "title": row["title"],
            "scenario": row["scenario"],
            "objection": row["objection"],
            "approved_response": row["approved_response"],
            "discovery_questions": loads(row["discovery_questions"], []),
            "category": row["category"],
            "evidence_refs": loads(row["evidence_refs"], []),
            "evidence_summary": row["evidence_summary"],
            "status": row["status"],
            "created_by": row["created_by"],
            "approved_by": row["approved_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "approved_at": row["approved_at"],
            "reviews": reviews,
        }

    def create_playbook_from_insight(self, insight_id: Any, overrides: Any = None) -> dict:
        if not isinstance(insight_id, str) or not insight_id:
            raise ValidationError("An insight ID is required.")
        insight = self.get_insight(insight_id)
        with self.db.connection() as conn:
            existing = conn.execute(
                "SELECT * FROM playbook_entries WHERE insight_id = ?", (insight_id,)
            ).fetchone()
            if existing:
                payload = self._playbook_row_to_payload(conn, existing)
                payload["created"] = False
                return payload
        with self.db.connection() as conn:
            session = conn.execute(
                "SELECT title FROM sessions WHERE id = ?", (insight["session_id"],)
            ).fetchone()
        session_title = session["title"] if session else "Conversation"
        evidence = insight["evidence"]
        summary_parts = []
        for item in evidence:
            summary_parts.append(f"[{item['ref']}] {item['speaker'].title()}: {item['quote']}")
        evidence_summary = "\n".join(summary_parts)[:3000]
        questions = []
        if insight["type"] == "discovery":
            questions = [insight["proposed_alternative"]]
        base = {
            "title": insight["title"],
            "scenario": f"{session_title} — {insight['type_label']}",
            "objection": insight["observation"],
            "approved_response": insight["proposed_alternative"],
            "discovery_questions": questions,
            "category": insight["type"],
        }
        user_overrides = parse_playbook_overrides(overrides or {})
        base.update(user_overrides)
        if not base["title"]:
            base["title"] = "Untitled playbook entry"
        if not base["scenario"]:
            base["scenario"] = f"{session_title} — {INSIGHT_TYPE_LABELS.get(insight['type'], 'Coaching')}"
        if not base["objection"]:
            base["objection"] = insight["observation"]
        if not base["approved_response"]:
            base["approved_response"] = insight["proposed_alternative"]
        entry_id = new_id("pb")
        created_at = now_utc()
        with self.db.connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO playbook_entries(id, insight_id, session_id, title, scenario, objection, "
                    "approved_response, discovery_questions, category, evidence_refs, evidence_summary, "
                    "status, created_by, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)",
                    (
                        entry_id, insight_id, insight["session_id"], base["title"], base["scenario"],
                        base["objection"], base["approved_response"], dumps(base["discovery_questions"]),
                        base["category"], dumps([item["ref"] for item in evidence]),
                        evidence_summary, "Local workspace", created_at, created_at,
                    ),
                )
            except Exception:
                # A concurrent call may have created the entry; return it.
                existing = conn.execute(
                    "SELECT * FROM playbook_entries WHERE insight_id = ?", (insight_id,)
                ).fetchone()
                if existing:
                    payload = self._playbook_row_to_payload(conn, existing)
                    payload["created"] = False
                    return payload
                raise
        entry = self.get_playbook_entry(entry_id)
        entry["created"] = True
        return entry

    def update_playbook_entry(self, entry_id: Any, overrides: Any, reviewer: str = "Local editor") -> dict:
        if not isinstance(entry_id, str) or not entry_id:
            raise ValidationError("A playbook entry ID is required.")
        current = self.get_playbook_entry(entry_id)
        updates = parse_playbook_overrides(overrides or {})
        if not updates:
            return current
        changed = {key: value for key, value in updates.items() if current.get(key) != value}
        if not changed:
            return current
        merged = {**current, **changed}
        if merged["status"] == "approved":
            # Content changes reopen review; approval cannot silently persist
            # over edited guidance.
            merged["status"] = "draft"
            merged["approved_by"] = None
            merged["approved_at"] = None
            review_action = "reopened"
        else:
            review_action = "edited"
        updated_at = now_utc()
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE playbook_entries SET title = ?, scenario = ?, objection = ?, "
                "approved_response = ?, discovery_questions = ?, category = ?, status = ?, "
                "approved_by = ?, approved_at = ?, updated_at = ? WHERE id = ?",
                (
                    merged["title"], merged["scenario"], merged["objection"],
                    merged["approved_response"], dumps(merged["discovery_questions"]),
                    merged["category"], merged["status"], merged["approved_by"],
                    merged["approved_at"], updated_at, entry_id,
                ),
            )
            conn.execute(
                "INSERT INTO playbook_reviews(id, entry_id, action, reviewer, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (new_id("rev"), entry_id, review_action, (reviewer or "Local editor").strip()[:80],
                 "Content edited after review." if review_action == "reopened" else "", updated_at),
            )
        return self.get_playbook_entry(entry_id)

    def approve_playbook_entry(self, entry_id: Any, reviewer: Any, note: Any = "") -> dict:
        if not isinstance(entry_id, str) or not entry_id:
            raise ValidationError("A playbook entry ID is required.")
        reviewer_name = ensure_reviewer(reviewer)
        if note is None:
            note = ""
        if not isinstance(note, str):
            raise ValidationError("Review note must be text.")
        note = note.strip()[:1000]
        current = self.get_playbook_entry(entry_id)
        if current["status"] == "approved":
            raise ConflictError("This playbook entry is already approved.")
        required = {
            "title": "Title",
            "scenario": "Communication scenario",
            "objection": "Customer objection",
            "approved_response": "Approved response",
        }
        missing = [label for key, label in required.items() if not str(current.get(key, "")).strip()]
        if missing:
            raise ValidationError(
                "Complete the required fields before approving.",
                detail={"missing": missing},
            )
        if not current.get("discovery_questions"):
            raise ValidationError("Add at least one discovery question before approving.")
        if not current.get("evidence_refs"):
            raise ValidationError("A playbook entry needs supporting evidence before approval.")
        approved_at = now_utc()
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE playbook_entries SET status = 'approved', approved_by = ?, "
                "approved_at = ?, updated_at = ? WHERE id = ?",
                (reviewer_name, approved_at, approved_at, entry_id),
            )
            conn.execute(
                "INSERT INTO playbook_reviews(id, entry_id, action, reviewer, note, created_at) "
                "VALUES (?, ?, 'approved', ?, ?, ?)",
                (new_id("rev"), entry_id, reviewer_name, note, approved_at),
            )
        return self.get_playbook_entry(entry_id)

    def get_playbook_entry(self, entry_id: Any) -> dict:
        if not isinstance(entry_id, str) or not entry_id:
            raise ValidationError("A playbook entry ID is required.")
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM playbook_entries WHERE id = ?", (entry_id,)).fetchone()
            if not row:
                raise NotFoundError("That playbook entry was not found.")
            return self._playbook_row_to_payload(conn, row)

    def list_playbook(self, status: str | None = None) -> list[dict]:
        if status not in (None, "", "draft", "approved"):
            raise ValidationError("Choose Draft or Approved status.")
        with self.db.connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM playbook_entries WHERE status = ? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM playbook_entries ORDER BY updated_at DESC"
                ).fetchall()
            return [self._playbook_row_to_payload(conn, row) for row in rows]

    # ------------------------------------------------------------------ #
    # Settings and preview
    # ------------------------------------------------------------------ #
    def settings(self) -> dict:
        return self.db.get_settings()

    def save_settings(self, values: dict) -> dict:
        return self.db.save_settings(values)

    def preview(self) -> dict:
        counts = self.db.counts()
        with self.db.connection() as conn:
            by_category = {
                row["category"] or "uncategorized": int(row["n"])
                for row in conn.execute(
                    "SELECT category, COUNT(*) AS n FROM playbook_entries "
                    "WHERE status = 'approved' GROUP BY category"
                ).fetchall()
            }
            approved_sessions = int(conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM playbook_entries "
                "WHERE status = 'approved' AND session_id IS NOT NULL"
            ).fetchone()[0])
            insight_types = {
                row["type"]: int(row["n"])
                for row in conn.execute(
                    "SELECT type, COUNT(*) AS n FROM insights GROUP BY type"
                ).fetchall()
            }
        return {
            "counts": counts,
            "approved_by_category": by_category,
            "approved_sessions": approved_sessions,
            "insight_types": insight_types,
            "consent_note": "Team Insights is a design preview. This build does not aggregate employee performance scores.",
        }

    def rename_session(self, session_id: str, title: str) -> dict:
        """Rename a conversation. The title is the only editable metadata."""
        from .models import now_utc

        clean = (title or "").strip()
        if not clean:
            raise ValidationError("A conversation title is required.")
        if len(clean) > 120:
            raise ValidationError("That title is too long.")
        with self.db.connection() as conn:
            row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                raise NotFoundError("No conversation with that id.")
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (clean, now_utc(), session_id),
            )
        return self.get_session(session_id)["session"]

    def delete_session(self, session_id: str) -> dict:
        """Delete a conversation and everything derived from it.

        Child rows are removed explicitly so this works on SQLite and
        PostgreSQL alike; no page is left orphaned.
        """
        with self.db.connection() as conn:
            row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                raise NotFoundError("No conversation with that id.")
            for table in (
                "insight_evidence",
                "assistant_note_evidence",
                "insights",
                "assistant_notes",
                "analysis_runs",
                "utterances",
            ):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))
                except Exception:
                    # Some child tables key on insight_id rather than session_id.
                    pass
            conn.execute(
                "DELETE FROM insight_evidence WHERE insight_id IN "
                "(SELECT id FROM insights WHERE session_id = ?)",
                (session_id,),
            )
            conn.execute(
                "DELETE FROM assistant_note_evidence WHERE note_id IN "
                "(SELECT id FROM assistant_notes WHERE session_id = ?)",
                (session_id,),
            )
            conn.execute("DELETE FROM insights WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM assistant_notes WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM analysis_runs WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM utterances WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return {"session_id": session_id, "deleted": True}
