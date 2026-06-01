"""Conductor — main orchestration loop.

The Conductor decomposes tasks, dispatches to agents, verifies outputs,
and records training data. It NEVER executes code directly.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from dataclasses import asdict

from orchestrator.coder import CoderAgent, CoderCandidate
from orchestrator.config import ConductorConfig
from orchestrator.gateway_client import GatewayClient
from orchestrator.interfaces.obsidian_watcher import ObsidianWatcher
from orchestrator.memory.changelog import Changelog, ChangelogEntry
from orchestrator.memory.knowledge_graph import KnowledgeGraph
from orchestrator.memory.layer0 import Layer0
from orchestrator.memory.layer1 import Layer1
from orchestrator.memory.layer2 import Layer2
from orchestrator.planner import PlannerAgent, Subtask
from orchestrator.reviewer import ReviewerAgent
from orchestrator.tools.file_ops import FileOps
from orchestrator.tools.shell import Shell
from orchestrator.tools.test_runner import TestRunner, TestResult
from orchestrator.training.data_collector import (
    CandidateRecord,
    ReviewerScoreRecord,
    TestResultRecord,
    TrainingDataCollector,
    TrainingRecord,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class Conductor:
    """Main orchestration loop."""

    def __init__(self, config: ConductorConfig) -> None:
        self._config = config
        self._gateway = GatewayClient(config.gateway_url)

        # Memory stack
        self._layer0 = Layer0(config.layer0_path)
        self._layer1 = Layer1(config.max_working_memory_tokens)
        self._layer2 = Layer2()
        self._changelog = Changelog(config.project_id, config.training_data_dir)
        self._kg = KnowledgeGraph()

        # Tools
        self._file_ops = FileOps(config.project_dir)
        self._shell = Shell(config.project_dir)
        self._test_runner = TestRunner(self._shell, config.tests.command)

        # Training
        self._data_collector = TrainingDataCollector(config.project_id, config.training_data_dir)

    async def close(self) -> None:
        await self._gateway.close()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def handle_task(self, task_id: str, task: str) -> str:
        """Process a single user task. Returns result markdown."""
        logger.info("=== Task %s: %s", task_id, task[:80])
        self._layer1.reset()
        self._layer1.add("Original request", task)

        # 1. Load project context into gateway
        await self._gateway.load_project(
            project_id=self._config.project_id,
            layer0_text=self._layer0.content,
            knowledge_context=self._kg.content,
        )

        # 2. Plan
        planner = PlannerAgent(self._gateway, self._layer0.content)
        plan = await planner.decompose(task)
        self._layer1.add("Plan", plan.summary)

        # 3. Execute subtasks
        results: list[dict] = []
        all_files_modified: list[str] = []
        total_attempts = 0
        max_tier = 1
        final_score = 0.0
        tests_passed = False

        for subtask in plan.subtasks:
            result = await self._execute_subtask(subtask)
            results.append(result)
            all_files_modified.extend(result.get("files", []))
            total_attempts += result.get("attempts", 0)
            max_tier = max(max_tier, result.get("tier", 1))
            final_score = max(final_score, result.get("score", 0))
            if result.get("tests_passed"):
                tests_passed = True

        # 4. Record changelog
        self._changelog.record(
            ChangelogEntry(
                timestamp=time.time(),
                task_id=task_id,
                original_request=task,
                plan_summary=plan.summary,
                files_modified=all_files_modified,
                test_passed=tests_passed,
                attempts=total_attempts,
                tier_used=max_tier,
                reviewer_score=final_score,
            )
        )

        # 5. Build result summary
        status = "completed" if any(r.get("accepted") for r in results) else "failed"
        summary_lines = [f"## Status: {status}", f"**Plan:** {plan.summary}", ""]
        for r in results:
            st = r.get("subtask_id", "?")
            summary_lines.append(
                f"- **{st}**: {'accepted' if r.get('accepted') else 'failed'} "
                f"(score {r.get('score', 0):.1f}, tier {r.get('tier', 0)}, {r.get('attempts', 0)} attempts)"
            )
        summary_lines.append("")
        summary_lines.append(f"**Files modified:** {', '.join(all_files_modified) or 'none'}")

        return "\n".join(summary_lines)

    # ------------------------------------------------------------------
    # Subtask execution
    # ------------------------------------------------------------------

    async def _execute_subtask(self, subtask: Subtask) -> dict:
        """Execute a single subtask through the generate-review-test loop."""
        tier = self._estimate_tier(subtask)
        accepted = False
        best_candidate: CoderCandidate | None = None
        best_score = 0.0
        test_result: TestResult | None = None
        files_modified: list[str] = []
        actual_attempts = 0

        # Training data accumulation
        all_candidates: list[CandidateRecord] = []
        all_reviewer_scores: list[ReviewerScoreRecord] = []
        all_test_results: list[TestResultRecord] = []

        # Create agents once (reused across attempts)
        coder = CoderAgent(
            self._gateway,
            self._config.project_id,
            self._layer0.content,
            self._layer1.content,
        )
        reviewer = ReviewerAgent(self._gateway, self._layer0.content)

        for attempt in range(self._config.max_retries):
            actual_attempts = attempt + 1

            # Generate candidates
            candidates = await coder.generate(subtask, tier=tier, attempt=attempt)

            if not candidates:
                logger.warning("No candidates generated for %s", subtask.subtask_id)
                subtask.add_feedback("Generation produced no candidates")
                continue

            # Track for training
            for c in candidates:
                all_candidates.append(
                    CandidateRecord(
                        candidate_id=c.candidate_id,
                        content_hash=TrainingDataCollector.hash_content(c.content),
                        sampling_params={},
                        tokens_generated=c.tokens_generated,
                        generation_time_ms=c.generation_time_ms,
                    )
                )

            # Review candidates
            review = await reviewer.evaluate(subtask, candidates)

            for r in review.results:
                all_reviewer_scores.append(
                    ReviewerScoreRecord(
                        candidate_id=r.candidate_id,
                        scores=asdict(r.scores),
                        overall=r.scores.overall,
                        verdict=r.verdict,
                    )
                )

            if review.best_candidate and review.best_score >= self._config.accept_threshold:
                # Apply the candidate's file operations
                for op in review.best_candidate.file_ops:
                    try:
                        if op.action in ("CREATE", "MODIFY"):
                            self._file_ops.write(op.path, op.content)
                            files_modified.append(op.path)
                        elif op.action == "DELETE":
                            if self._file_ops.exists(op.path):
                                # For safety, we don't actually delete in Phase 0
                                # Just log it as a pending deletion
                                logger.info("DELETE requested (deferred): %s", op.path)
                                files_modified.append(f"(delete){op.path}")
                    except (PermissionError, ValueError) as e:
                        logger.error("File operation failed for %s: %s", op.path, e)
                        subtask.add_feedback(f"File operation failed: {op.path}: {e}")
                        continue

                # Run tests
                test_result = await self._test_runner.run()
                all_test_results.append(
                    TestResultRecord(
                        candidate_id=review.best_candidate.candidate_id,
                        passed=test_result.passed,
                        summary=test_result.summary[:500],
                    )
                )

                if test_result.passed:
                    accepted = True
                    best_candidate = review.best_candidate
                    best_score = review.best_score
                    break
                else:
                    subtask.add_feedback(f"Tests failed: {test_result.summary[:300]}")
            else:
                subtask.add_feedback(review.feedback_for_retry)

            # Tier escalation after first failed attempt
            if attempt >= 1 and tier < 3:
                tier += 1
                logger.info("Escalating tier to %d for %s", tier, subtask.subtask_id)

        # Record training data
        self._data_collector.record(
            TrainingRecord(
                task_id=subtask.subtask_id,
                timestamp=time.time(),
                prompt_hash=TrainingDataCollector.hash_content(subtask.description),
                tier=tier,
                candidates=all_candidates,
                reviewer_scores=all_reviewer_scores,
                test_results=all_test_results,
                accepted_candidate_id=best_candidate.candidate_id if best_candidate else None,
            )
        )

        # Update working memory
        self._layer1.update_subtask(
            subtask.subtask_id,
            f"{'accepted' if accepted else 'failed'}, score {best_score:.1f}",
        )

        return {
            "subtask_id": subtask.subtask_id,
            "accepted": accepted,
            "score": best_score,
            "tier": tier,
            "attempts": actual_attempts,
            "files": files_modified,
            "tests_passed": test_result.passed if test_result else False,
        }

    def _estimate_tier(self, subtask: Subtask) -> int:
        """Heuristic difficulty estimation for Phase 0."""
        complexity = subtask.estimated_complexity
        if complexity == "trivial":
            return 1
        elif complexity in ("simple", "medium"):
            return 2
        elif complexity == "complex":
            return 3
        else:
            return 4


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(description="Conductor orchestrator")
    parser.add_argument("--project", required=True, help="Project ID")
    parser.add_argument("--config", required=True, help="Path to conductor.yaml")
    args = parser.parse_args()

    config = ConductorConfig.from_yaml(args.config)
    config.project_id = args.project  # override from CLI

    conductor = Conductor(config)

    # Start Obsidian watcher
    async def on_task(task_id: str, content: str) -> str:
        return await conductor.handle_task(task_id, content)

    watcher = ObsidianWatcher(config.obsidian_vault, on_task)
    loop = asyncio.get_running_loop()
    watcher.start(loop)

    logger.info("Conductor running for project %s", config.project_id)
    logger.info("Drop task files in: %s/conductor/inbox/", config.obsidian_vault)

    try:
        # Run until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        await conductor.close()


if __name__ == "__main__":
    asyncio.run(main())
