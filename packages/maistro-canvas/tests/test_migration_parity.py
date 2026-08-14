"""Migration-parity tests for Canvas product behavior.

These tests intentionally span the current Canvas domain/lifecycle seam.  They
pin behavior that must survive when the private generation-job lifecycle moves
to canonical Run/NodeRun/Attempt execution.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from maistro_canvas.canvas.runner import CanvasJobRunner
from maistro_canvas.types import BookLayer, GenerationJobRecord, JobAction, JobStatus


class _SingleJobStore:
    """Minimal store implementing the runner contract for one logical job."""

    def __init__(self, job: GenerationJobRecord) -> None:
        self.job = job

    async def claim_next_pending(
        self, worker_id: str, lease_seconds: int
    ) -> GenerationJobRecord | None:
        if self.job.status != JobStatus.PENDING:
            return None
        self.job.status = JobStatus.RUNNING
        self.job.leased_by = worker_id
        self.job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
        self.job.attempts += 1
        return self.job

    async def update_job(self, job: GenerationJobRecord) -> GenerationJobRecord:
        self.job = job
        return job


class _FailOnceExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def _execute_claimed(self, job: GenerationJobRecord) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient provider failure")
        job.result_paths = ["artifacts/canvas-7/layer-3/final.png"]


@pytest.mark.asyncio
async def test_retry_preserves_one_logical_generation_job_and_domain_request() -> None:
    """A physical retry must not become a new logical Canvas generation job.

    Canonical migration target: one logical NodeRun/job with multiple Attempts.
    Canvas-specific request identity and generation parameters must survive the
    retry unchanged.
    """

    job = GenerationJobRecord(
        id="job-17",
        layer_id="layer-3",
        canvas_id="canvas-7",
        action=JobAction.REFINE,
        status=JobStatus.PENDING,
        model_id="proof-model",
        prompt="keep the character pose; improve lighting",
        params={"count": 1, "seed": 421, "strength": 0.35},
        max_attempts=3,
    )
    store = _SingleJobStore(job)
    executor = _FailOnceExecutor()
    runner = CanvasJobRunner(store=store, executor=executor)  # type: ignore[arg-type]

    await runner.tick_once()
    assert job.status == JobStatus.PENDING
    assert job.attempts == 1

    await runner.tick_once()

    assert job.status == JobStatus.DONE
    assert job.attempts == 2
    assert job.id == "job-17"
    assert job.canvas_id == "canvas-7"
    assert job.layer_id == "layer-3"
    assert job.action == JobAction.REFINE
    assert job.model_id == "proof-model"
    assert job.prompt == "keep the character pose; improve lighting"
    assert job.params == {"count": 1, "seed": 421, "strength": 0.35}
    assert job.result_paths == ["artifacts/canvas-7/layer-3/final.png"]
    assert job.leased_by is None
    assert job.lease_expires_at is None


def test_layer_retry_and_upgrade_preserve_canvas_domain_state_and_image_history() -> None:
    """Lifecycle convergence must not flatten Canvas' version-history semantics."""

    original = BookLayer(
        name="hero",
        layer_type="character",
        image_url="images/hero-v1.png",
        prompt="hero looking left",
        z_index=4,
        visible=True,
        quality="draft",
        history=["images/hero-v0.png"],
        slot={"x": 0.35, "y": 0.62, "width": 0.4, "height": 0.7},
        pose={"body": "three-quarter", "gaze": "left"},
        face_mask="masks/hero-face.png",
        head_region={"x": 0.2, "y": 0.08, "width": 0.22, "height": 0.2},
    )

    retried = original.retry("images/hero-v2.png")
    upgraded = retried.upgrade("images/hero-final.png")

    assert original.image_url == "images/hero-v1.png"
    assert original.history == ["images/hero-v0.png"]

    assert retried.image_url == "images/hero-v2.png"
    assert retried.history == ["images/hero-v0.png", "images/hero-v1.png"]
    assert retried.quality == "draft"

    assert upgraded.image_url == "images/hero-final.png"
    assert upgraded.history == [
        "images/hero-v0.png",
        "images/hero-v1.png",
        "images/hero-v2.png",
    ]
    assert upgraded.quality == "final"

    for layer in (retried, upgraded):
        assert layer.name == original.name
        assert layer.layer_type == original.layer_type
        assert layer.prompt == original.prompt
        assert layer.z_index == original.z_index
        assert layer.visible == original.visible
        assert layer.slot == original.slot
        assert layer.pose == original.pose
        assert layer.face_mask == original.face_mask
        assert layer.head_region == original.head_region
