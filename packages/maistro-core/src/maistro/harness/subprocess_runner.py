"""Sandbox-friendly subprocess HarnessRunner provider.

This provider is a real process-backed adapter for JSON-line harness binaries.
It deliberately avoids a shell and validates binary presence in healthcheck();
callers can run it inside the existing sandbox/microVM layer by selecting the
appropriate executable/profile outside this class.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from maistro.capabilities.types import ProviderHealth
from maistro.types.config import AgentConfig


@dataclass
class SubprocessHarnessRunner:
    provider_name: str
    executable: str
    argv: tuple[str, ...] = ()
    sandbox_profile: str = "default"
    _sessions: dict[str, asyncio.subprocess.Process] = field(default_factory=dict, init=False)

    @property
    def name(self) -> str:
        return self.provider_name

    @property
    def slot(self) -> str:
        return "harness_runner"

    @property
    def trust_tier(self) -> str:
        return "t2"

    def requires(self) -> tuple[str, ...]:
        return (self.executable, f"sandbox:{self.sandbox_profile}")

    async def healthcheck(self) -> ProviderHealth:
        if shutil.which(self.executable) is None:
            return ProviderHealth(False, f"missing executable: {self.executable}")
        return ProviderHealth(True, f"executable present; sandbox={self.sandbox_profile}")

    async def start_session(self, agent_spec: AgentConfig, *, workdir: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            self.executable,
            *self.argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = proc
        await self._write_json(proc, {"op": "start", "agent": agent_spec.model_dump(mode="json")})
        return session_id

    async def send(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        proc = self._require_session(session_id)
        await self._write_json(proc, {"op": "send", "session_id": session_id, "messages": messages})
        assert proc.stdout is not None
        line = await proc.stdout.readline()
        if not line:
            raise RuntimeError("harness process exited without a response")
        response = json.loads(line.decode())
        if not isinstance(response, dict):
            raise RuntimeError("harness response must be a JSON object")
        return response

    async def stream(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        proc = self._require_session(session_id)
        assert proc.stdout is not None
        while proc.returncode is None:
            line = await proc.stdout.readline()
            if not line:
                break
            event = json.loads(line.decode())
            if isinstance(event, dict):
                yield event

    async def stop(self, session_id: str) -> None:
        proc = self._sessions.pop(session_id, None)
        if proc is None:
            return
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except TimeoutError:
                proc.kill()
                await proc.wait()

    async def _write_json(self, proc: asyncio.subprocess.Process, payload: dict[str, Any]) -> None:
        if proc.stdin is None:
            raise RuntimeError("harness process stdin is unavailable")
        proc.stdin.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        await proc.stdin.drain()

    def _require_session(self, session_id: str) -> asyncio.subprocess.Process:
        proc = self._sessions.get(session_id)
        if proc is None:
            raise KeyError(f"unknown harness session: {session_id}")
        return proc
