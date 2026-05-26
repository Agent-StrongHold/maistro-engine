"""Per-user program context — projects, interview state, learned guidance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InterviewTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str  # agent | user
    text: str
    at: str = ""


class ProgramProject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    status: str = "active"


class ProgramContext(BaseModel):
    """What the PM fleet knows about a user's program — grows via interview + guidance."""

    model_config = ConfigDict(extra="ignore")

    user_id: str
    program_name: str = ""
    summary: str = ""
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    projects: list[ProgramProject] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    interview_complete: bool = False
    interview_step: int = 0
    interview_transcript: list[InterviewTurn] = Field(default_factory=list)
    guidance_log: list[str] = Field(default_factory=list)
    last_pulse_at: str | None = None
    updated_at: str = ""

    @staticmethod
    def empty(user_id: str) -> ProgramContext:
        now = datetime.now(UTC).isoformat()
        return ProgramContext(user_id=user_id, updated_at=now)


# Intake-led interview — one question at a time until complete.
INTERVIEW_STEPS: tuple[dict[str, str], ...] = (
    {
        "field": "program_name",
        "agent": "intake",
        "question": "What program or initiative are you accountable for? Name it in one line.",
    },
    {
        "field": "goals",
        "agent": "intake",
        "question": "What outcomes must be true in the next 90 days? List the top 2–3.",
    },
    {
        "field": "tools",
        "agent": "intake",
        "question": "Which systems does the team use daily? (e.g. Jira, GitHub, Confluence, Slack)",
    },
    {
        "field": "constraints",
        "agent": "risk_dependency",
        "question": "What constraints or dependencies worry you most right now?",
    },
    {
        "field": "stakeholders",
        "agent": "program_manager",
        "question": "Who are the key stakeholders you report to or coordinate with?",
    },
)


def current_interview_question(ctx: ProgramContext) -> dict[str, str] | None:
    if ctx.interview_complete:
        return None
    if ctx.interview_step >= len(INTERVIEW_STEPS):
        return None
    return INTERVIEW_STEPS[ctx.interview_step]


def apply_interview_answer(ctx: ProgramContext, answer: str) -> ProgramContext:
    """Record an interview answer and advance the script."""
    answer = answer.strip()
    if not answer or ctx.interview_complete:
        return ctx

    step_idx = ctx.interview_step
    if step_idx >= len(INTERVIEW_STEPS):
        return ctx.model_copy(update={"interview_complete": True})

    step = INTERVIEW_STEPS[step_idx]
    field = step["field"]
    now = datetime.now(UTC).isoformat()
    transcript = [
        *ctx.interview_transcript,
        InterviewTurn(role="agent", text=step["question"], at=now),
        InterviewTurn(role="user", text=answer, at=now),
    ]

    updates: dict[str, Any] = {
        "interview_transcript": transcript,
        "interview_step": step_idx + 1,
        "updated_at": now,
        "facts": [*ctx.facts, f"Interview ({field}): {answer}"],
    }

    if field == "program_name":
        updates["program_name"] = answer
        updates["projects"] = [
            *ctx.projects,
            ProgramProject(name=answer, description="Primary program from intake interview"),
        ]
    elif field == "goals":
        updates["goals"] = _split_lines(answer)
    elif field == "tools":
        updates["tools"] = _split_lines(answer)
    elif field == "constraints":
        updates["constraints"] = _split_lines(answer)
    elif field == "stakeholders":
        updates["stakeholders"] = _split_lines(answer)

    next_ctx = ctx.model_copy(update=updates)
    if next_ctx.interview_step >= len(INTERVIEW_STEPS):
        summary = (
            f"Program: {next_ctx.program_name}. "
            f"Goals: {', '.join(next_ctx.goals[:3])}. "
            f"Tools: {', '.join(next_ctx.tools[:4])}."
        )
        next_ctx = next_ctx.model_copy(
            update={
                "interview_complete": True,
                "summary": summary.strip(),
                "open_questions": [
                    "What is the single highest-risk dependency this month?",
                    "Which milestone should we protect first?",
                ],
            }
        )
    return next_ctx


def apply_guidance(ctx: ProgramContext, text: str) -> ProgramContext:
    """Learn from human guidance — append facts and open questions for the hyperagent."""
    text = text.strip()
    if not text:
        return ctx
    now = datetime.now(UTC).isoformat()
    facts = [*ctx.facts, f"Guidance: {text}"]
    open_q = list(ctx.open_questions)
    lowered = text.lower()
    if "?" in text:
        open_q.append(text)
    if any(w in lowered for w in ("risk", "blocker", "dependency")):
        open_q.append("Validate RAID entries against latest guidance")
    return ctx.model_copy(
        update={
            "guidance_log": [*ctx.guidance_log, text],
            "facts": facts[-50:],  # cap growth
            "open_questions": open_q[-20:],
            "updated_at": now,
        }
    )


def context_for_task(ctx: ProgramContext) -> dict[str, Any]:
    """Compact dict injected into PM task payloads."""
    return {
        "program_name": ctx.program_name,
        "summary": ctx.summary,
        "goals": ctx.goals,
        "constraints": ctx.constraints,
        "stakeholders": ctx.stakeholders,
        "tools": ctx.tools,
        "recent_guidance": ctx.guidance_log[-3:],
        "open_questions": ctx.open_questions[:5],
    }


def _split_lines(text: str) -> list[str]:
    parts: list[str] = []
    for line in text.replace(",", "\n").split("\n"):
        s = line.strip().lstrip("-•* ")
        if s:
            parts.append(s)
    return parts
