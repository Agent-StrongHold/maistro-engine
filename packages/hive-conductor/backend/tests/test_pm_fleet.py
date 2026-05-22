"""PM fleet service unit tests (no Hive auth/session deps)."""

from __future__ import annotations

from maistro.tasks.models import TaskCreate, TaskStatus
from maistro.tasks.queue import TaskQueue

from services.pm_fleet import invoke_pm_agent, is_pm_poc_mode, list_pm_agents


def test_list_pm_agents_returns_five() -> None:
    agents = list_pm_agents([])
    assert len(agents) == 5
    assert agents[0].tagline
    assert agents[0].primary_capability


def test_invoke_pm_agent_builds_description() -> None:
    task_type, description, agent_id = invoke_pm_agent(
        "intake",
        "create_initiative",
        {"title": "Q3 Platform"},
    )
    assert task_type == "intake"
    assert agent_id == "intake"
    assert "Q3 Platform" in description


def test_pm_tasks_scoped_per_user_in_queue() -> None:
    import asyncio

    async def _run() -> None:
        queue = TaskQueue()
        task_type, desc, agent_id = invoke_pm_agent(
            "reporting",
            "generate_exec_summary",
            {"title": "Weekly"},
        )
        await queue.submit(
            TaskCreate(description=desc, task_type=task_type, agent_id=agent_id),
            user_id="alice",
        )
        alice_items, _ = queue.list_tasks(user_id="alice")
        bob_items, _ = queue.list_tasks(user_id="bob")
        assert len(alice_items) == 1
        assert len(bob_items) == 0

    asyncio.run(_run())


def test_is_pm_poc_mode_reads_env(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("MAISTRO_POC_MODE", raising=False)
    monkeypatch.delenv("HIVE_POC_MODE", raising=False)
    assert is_pm_poc_mode() is False
    monkeypatch.setenv("MAISTRO_POC_MODE", "pm")
    assert is_pm_poc_mode() is True
