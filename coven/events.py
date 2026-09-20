"""Structured runtime event normalization for presentation-only effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NON_TERMINAL_REASONS = {
    "approval_pending",
    "awaiting_authorization",
    "cancelled",
    "canceled",
    "configuration_missing",
    "disconnected",
    "needs_input",
    "pending",
    "stopped",
    "tool_error",
    "transient_error",
}


@dataclass(frozen=True)
class NormalizedEvent:
    """Small immutable shape consumed by the cinematic controller."""

    event_id: str
    task_id: str
    attempt_id: str
    title: str
    assignee: str
    status: str
    outcome_kind: str
    terminal: bool
    retry_policy_exhausted: bool
    error: str
    last_successful_step: str
    timestamp: str


def normalize_runtime_event(raw: dict[str, Any]) -> NormalizedEvent:
    """Normalize an adapter event without inspecting prose log lines."""

    status = str(raw.get("status") or raw.get("state") or "").strip().lower()
    reason = str(raw.get("reason") or raw.get("category") or "").strip().lower()
    outcome = str(raw.get("outcome_kind") or raw.get("outcomeKind") or "").strip().lower()
    terminal = _strict_bool(raw.get("terminal", raw.get("is_terminal", raw.get("isTerminal"))))
    retry_exhausted = _strict_bool(
        raw.get("retry_policy_exhausted", raw.get("retryPolicyExhausted", raw.get("retries_exhausted")))
    )

    if reason in NON_TERMINAL_REASONS:
        outcome_kind = reason
    elif outcome:
        outcome_kind = outcome
    else:
        outcome_kind = status or "unknown"

    return NormalizedEvent(
        event_id=str(raw.get("id") or raw.get("event_id") or raw.get("eventId") or ""),
        task_id=str(raw.get("task_id") or raw.get("taskId") or ""),
        attempt_id=str(raw.get("attempt_id") or raw.get("attemptId") or ""),
        title=str(raw.get("title") or raw.get("task_title") or raw.get("taskTitle") or "Untitled task"),
        assignee=str(raw.get("assignee") or raw.get("profile") or "unknown"),
        status=status,
        outcome_kind=outcome_kind,
        terminal=terminal,
        retry_policy_exhausted=retry_exhausted,
        error=str(raw.get("error") or raw.get("message") or ""),
        last_successful_step=str(raw.get("last_successful_step") or raw.get("lastSuccessfulStep") or ""),
        timestamp=str(raw.get("timestamp") or ""),
    )


def should_trigger_failure_cinematic(raw: dict[str, Any], shown_event_ids: set[str]) -> bool:
    """Return true only for a unique confirmed terminal failed task outcome."""

    event = normalize_runtime_event(raw)
    if not event.event_id or event.event_id in shown_event_ids:
        return False
    return (
        event.status == "failed"
        and event.outcome_kind == "terminal_failure"
        and event.terminal
        and event.retry_policy_exhausted
    )


def _strict_bool(value: Any) -> bool:
    return value is True


def event_to_dict(event: NormalizedEvent) -> dict[str, Any]:
    return {
        "eventId": event.event_id,
        "taskId": event.task_id,
        "attemptId": event.attempt_id,
        "title": event.title,
        "assignee": event.assignee,
        "status": event.status,
        "outcomeKind": event.outcome_kind,
        "terminal": event.terminal,
        "retryPolicyExhausted": event.retry_policy_exhausted,
        "error": event.error,
        "lastSuccessfulStep": event.last_successful_step,
        "timestamp": event.timestamp,
    }
