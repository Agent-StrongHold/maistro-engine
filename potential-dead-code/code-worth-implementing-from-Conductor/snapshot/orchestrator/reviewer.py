"""Reviewer agent — evaluates coder candidates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from orchestrator.coder import CoderCandidate
from orchestrator.gateway_client import GatewayClient
from orchestrator.planner import Subtask
from orchestrator.utils import LLMParseError, clamp, parse_json_response

logger = logging.getLogger(__name__)


@dataclass
class ReviewScore:
    correctness: float = 0.0
    style: float = 0.0
    robustness: float = 0.0
    simplicity: float = 0.0
    testability: float = 0.0

    @property
    def overall(self) -> float:
        return (
            self.correctness * 0.35
            + self.style * 0.15
            + self.robustness * 0.20
            + self.simplicity * 0.15
            + self.testability * 0.15
        )


@dataclass
class ReviewResult:
    candidate_id: str
    scores: ReviewScore
    verdict: str  # accept, revise, reject
    feedback: str
    concerns: list[str] = field(default_factory=list)


@dataclass
class ReviewSummary:
    results: list[ReviewResult]
    best_candidate: CoderCandidate | None
    best_score: float
    feedback_for_retry: str


class ReviewerAgent:
    """Evaluates coder candidates independently."""

    SYSTEM_PROMPT = """You are a code reviewer. You did NOT write this code. Evaluate it objectively.

## Evaluation Criteria
Score each dimension 0-10:
1. **Correctness**: Does it actually solve the task? Handle edge cases?
2. **Style**: Does it follow the project's conventions from the constraints?
3. **Robustness**: Error handling, input validation, failure modes?
4. **Simplicity**: Is it the simplest solution that works? Over-engineered?
5. **Testability**: Can this be tested? Are tests included if required?

## Output Format
Respond ONLY with valid JSON (no markdown fences):
{
  "scores": {"correctness": N, "style": N, "robustness": N, "simplicity": N, "testability": N},
  "verdict": "accept" | "revise" | "reject",
  "feedback": "specific actionable feedback for the coder if revise/reject",
  "concerns": ["list of specific issues found"]
}"""

    def __init__(self, gateway: GatewayClient, layer0_content: str) -> None:
        self._gateway = gateway
        self._layer0 = layer0_content

    async def evaluate(
        self,
        subtask: Subtask,
        candidates: list[CoderCandidate],
    ) -> ReviewSummary:
        """Review all candidates and pick the best.

        Selection logic:
        - Best candidate is the one with highest overall score
        - We return it regardless of verdict (verdict is advisory)
        - The caller decides whether to use it based on score threshold
        """
        if not candidates:
            logger.warning("No candidates to review for %s", subtask.subtask_id)
            return ReviewSummary(
                results=[],
                best_candidate=None,
                best_score=0.0,
                feedback_for_retry="No candidates were generated",
            )

        results: list[ReviewResult] = []

        for candidate in candidates:
            try:
                result = await self._review_one(subtask, candidate)
                results.append(result)
            except LLMParseError as e:
                logger.warning("Failed to parse review for %s: %s", candidate.candidate_id, e)
                # Create a neutral review so we don't lose the candidate
                results.append(
                    ReviewResult(
                        candidate_id=candidate.candidate_id,
                        scores=ReviewScore(
                            correctness=5, style=5, robustness=5, simplicity=5, testability=5
                        ),
                        verdict="revise",
                        feedback="Review parsing failed; manual inspection recommended",
                    )
                )

        # Find best candidate by overall score (regardless of verdict)
        best_result = max(results, key=lambda r: r.scores.overall)
        best_score = best_result.scores.overall

        # Find the matching candidate object
        best_candidate = None
        for c in candidates:
            if c.candidate_id == best_result.candidate_id:
                best_candidate = c
                break

        # Aggregate feedback from all reviews for retry guidance
        feedback_parts = [r.feedback for r in results if r.feedback]
        feedback_for_retry = "; ".join(feedback_parts[:3]) if feedback_parts else ""

        logger.info(
            "Review: best score %.1f, verdict %s, %d candidates reviewed",
            best_score,
            best_result.verdict,
            len(results),
        )

        return ReviewSummary(
            results=results,
            best_candidate=best_candidate,
            best_score=best_score,
            feedback_for_retry=feedback_for_retry,
        )

    async def _review_one(self, subtask: Subtask, candidate: CoderCandidate) -> ReviewResult:
        """Review a single candidate."""
        user_content = f"""## Task That Was Assigned
{subtask.description}

## Candidate Implementation
{candidate.content}"""

        messages = [
            {"role": "system", "content": self._layer0 + "\n\n" + self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        result = await self._gateway.chat(messages, max_tokens=1024)
        data = parse_json_response(result.content)

        scores_raw = data.get("scores", {})
        scores = ReviewScore(
            correctness=clamp(float(scores_raw.get("correctness", 5)), 0, 10),
            style=clamp(float(scores_raw.get("style", 5)), 0, 10),
            robustness=clamp(float(scores_raw.get("robustness", 5)), 0, 10),
            simplicity=clamp(float(scores_raw.get("simplicity", 5)), 0, 10),
            testability=clamp(float(scores_raw.get("testability", 5)), 0, 10),
        )

        return ReviewResult(
            candidate_id=candidate.candidate_id,
            scores=scores,
            verdict=data.get("verdict", "revise"),
            feedback=data.get("feedback", ""),
            concerns=data.get("concerns", []),
        )
