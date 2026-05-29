"""Agent base class and handle() pipeline.

An agent is data, not a process. The runtime is shared.
handle() runs: Warden scan -> build context -> strategy.reason() -> post-turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maistro.types.agent import AgentResponse

_TOOL_SCHEMAS: dict[str, dict[str, object]] = {
    "read_file": {
        "description": "Read the contents of a file. Returns the file content as a string.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace root"},
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "description": "Create or overwrite a file with the given content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace root"},
                "content": {"type": "string", "description": "The full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    "list_files": {
        "description": "List files and directories at the given path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (default: '.')",
                    "default": ".",
                },
            },
        },
    },
    "run_pytest": {
        "description": "Run the pytest test suite. Returns pass/fail with details.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Test path (default: 'tests/')",
                    "default": "tests/",
                },
            },
        },
    },
    "run_ruff_check": {
        "description": "Run ruff linter. Returns violations with file:line:rule.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to check", "default": "src/"},
            },
        },
    },
    "run_mypy": {
        "description": "Run mypy type checker in strict mode. Returns type errors.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to check", "default": "src/"},
            },
        },
    },
    "run_bandit": {
        "description": "Run bandit security scanner. Returns security findings.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to scan", "default": "src/"},
            },
        },
    },
    "run_ruff_format": {
        "description": "Check code formatting with ruff. Returns formatting issues.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to check", "default": "src/"},
            },
        },
    },
    "git_commit": {
        "description": "Stage all changes and create a git commit.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message"},
            },
            "required": ["message"],
        },
    },
}


def _build_tool_schema(name: str, *, registry: Any = None) -> dict[str, object]:
    if registry is not None:
        defn = registry.get(name)
        if defn is not None:
            return {
                "type": "function",
                "function": {
                    "name": defn.name,
                    "description": defn.description,
                    "parameters": defn.parameters,
                },
            }

    schema = _TOOL_SCHEMAS.get(name)
    if schema:
        return {
            "type": "function",
            "function": {"name": name, **schema},
        }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Run {name}",
            "parameters": {"type": "object", "properties": {}},
        },
    }


if TYPE_CHECKING:
    from maistro.agents.context_builder import ContextBuilder
    from maistro.protocols.llm import LLMClient
    from maistro.protocols.memory import LearningStore, OutcomeStore, SessionStore
    from maistro.protocols.prompts import PromptManager
    from maistro.protocols.quota import QuotaTracker
    from maistro.protocols.tracing import TracingBackend
    from maistro.types.agent import AgentIdentity


class Agent:
    """A running agent instance. All behavior determined by identity + strategy."""

    def __init__(
        self,
        identity: AgentIdentity,
        strategy: Any,
        *,
        llm: LLMClient,
        context_builder: ContextBuilder,
        prompt_manager: PromptManager,
        warden: Any,
        learning_store: LearningStore | None = None,
        learning_extractor: Any = None,
        rca_extractor: Any = None,
        learning_promoter: Any = None,
        sentinel: Any = None,
        outcome_store: OutcomeStore | None = None,
        session_store: SessionStore | None = None,
        quota_tracker: QuotaTracker | None = None,
        coin_ledger: Any = None,
        tracer: TracingBackend | None = None,
        tool_executor: Any = None,
        tool_registry: Any = None,
        agent_resolver: Any = None,
    ) -> None:
        self.identity = identity
        self._strategy = strategy
        self._llm = llm
        self._context_builder = context_builder
        self._prompt_manager = prompt_manager
        self._warden = warden
        self._learning_store = learning_store
        self._learning_extractor = learning_extractor
        self._rca_extractor = rca_extractor
        self._learning_promoter = learning_promoter
        self._sentinel = sentinel
        self._outcome_store = outcome_store
        self._session_store = session_store
        self._quota_tracker = quota_tracker
        self._coin_ledger = coin_ledger
        self._tool_executor = tool_executor
        self._tool_registry = tool_registry
        self._tracer = tracer
        # Resolves a sub-agent name -> Agent for delegation. Callable or mapping.
        self._agent_resolver = agent_resolver

    async def handle(
        self,
        messages: list[dict[str, Any]],
        auth: Any,
        *,
        session_id: str | None = None,
        model_override: str | None = None,
        status_callback: Any = None,
        classified_task_type: str = "",
        _delegation_depth: int = 0,
    ) -> AgentResponse:
        trace = (
            self._tracer.create_trace(
                user_id=getattr(auth, "user_id", ""),
                session_id=session_id or "",
                name=f"agent.{self.identity.name}",
                metadata={"agent": self.identity.name},
            )
            if self._tracer
            else None
        )

        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_text = content
                elif isinstance(content, list):
                    user_text = " ".join(
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                break

        if trace:
            with trace.span("warden.user_input") as ws:
                ws.set_input({"text_length": len(user_text)})
                warden_verdict = await self._warden.scan(user_text, "user_input")
                ws.set_output({"clean": warden_verdict.clean, "flags": warden_verdict.flags})
        else:
            warden_verdict = await self._warden.scan(user_text, "user_input")

        if not warden_verdict.clean:
            if trace:
                trace.score("blocked", 1.0, comment=f"flags: {warden_verdict.flags}")
                trace.end()
            return AgentResponse.blocked_response(
                f"Blocked by Warden: {', '.join(warden_verdict.flags)}",
            )

        session_history_count = 0
        if session_id and self._session_store:
            history = await self._session_store.get_history(session_id)
            if history:
                session_history_count = len(history)
                if messages and messages[0].get("role") == "system":
                    messages = [messages[0], *history, *messages[1:]]
                else:
                    messages = [*history, *messages]

        org_id = getattr(auth, "org_id", "")
        team_id = getattr(auth, "team_id", "")

        if trace:
            with trace.span("prompt.build") as ps:
                ps.set_input({"message_count": len(messages)})
                context_messages, injected_learning_ids = await self._context_builder.build(
                    messages,
                    self.identity,
                    prompt_manager=self._prompt_manager,
                    learning_store=self._learning_store,
                    agent_id=self.identity.name,
                    org_id=org_id,
                    team_id=team_id,
                )
                ps.set_output(
                    {
                        "context_message_count": len(context_messages),
                        "learnings_injected": len(injected_learning_ids),
                    }
                )
        else:
            context_messages, injected_learning_ids = await self._context_builder.build(
                messages,
                self.identity,
                prompt_manager=self._prompt_manager,
                learning_store=self._learning_store,
                agent_id=self.identity.name,
                org_id=org_id,
                team_id=team_id,
            )

        tool_defs: list[dict[str, Any]] | None = None
        if self.identity.tools:
            tool_defs = [
                _build_tool_schema(name, registry=self._tool_registry)
                for name in self.identity.tools
            ]

        model = model_override or self.identity.model
        strategy_kwargs: dict[str, Any] = {}
        if trace:
            strategy_kwargs["trace"] = trace
        strategy_kwargs["warden"] = self._warden
        strategy_kwargs["auth"] = auth
        if self._sentinel is not None:
            strategy_kwargs["sentinel"] = self._sentinel
        if status_callback:
            strategy_kwargs["status_callback"] = status_callback
        strategy_kwargs["identity"] = self.identity
        if classified_task_type:
            strategy_kwargs["classified_task_type"] = classified_task_type

        try:
            if trace:
                with trace.span("strategy.reason") as ss:
                    ss.set_input({"model": model, "tools": len(tool_defs) if tool_defs else 0})
                    result = await self._strategy.reason(
                        context_messages,
                        model,
                        self._llm,
                        tools=tool_defs,
                        tool_executor=self._tool_executor,
                        **strategy_kwargs,
                    )
                    ss.set_output(
                        {
                            "done": result.done,
                            "tool_rounds": len(result.tool_history) if result.tool_history else 0,
                            "response_length": len(result.response or ""),
                        }
                    )
            else:
                result = await self._strategy.reason(
                    context_messages,
                    model,
                    self._llm,
                    tools=tool_defs,
                    tool_executor=self._tool_executor,
                    **strategy_kwargs,
                )
        except (ValueError, RuntimeError, TimeoutError, OSError) as exc:
            import logging as _log

            _log.getLogger("maistro.agent").warning(
                "Strategy failed: agent=%s model=%s error=%s",
                self.identity.name,
                model,
                type(exc).__name__,
            )
            if trace:
                trace.score("strategy_error", 0.0, "Strategy raised an exception")
                trace.end()
            return AgentResponse(
                content="I encountered an internal error. Please try again.",
                agent_name=self.identity.name,
            )

        # Delegation: the strategy decided to route to a sub-agent. Resolve the
        # target and return *its* response. Without this, a DelegateStrategy
        # result (response=None, done=False, delegate_to=<name>) would fall
        # through and produce an empty AgentResponse.
        if result.delegate_to:
            delegated = await self._delegate(
                result,
                auth=auth,
                session_id=session_id,
                model_override=model_override,
                status_callback=status_callback,
                classified_task_type=classified_task_type,
                depth=_delegation_depth,
                trace=trace,
            )
            if delegated is not None:
                return delegated

        tool_had_failures = bool(
            result.tool_history
            and any(
                str(h.get("result", "")).startswith("Error")
                or "error" in str(h.get("result", ""))[:50].lower()
                for h in result.tool_history
            )
        )
        if (
            tool_had_failures
            and self._rca_extractor
            and self._learning_store
            and result.tool_history
        ):
            if trace:
                with trace.span("rca.extraction") as rs:
                    rca = await self._rca_extractor.extract_rca(
                        user_text,
                        result.tool_history,
                    )
                    if rca:
                        rca.agent_id = self.identity.name
                        rca.org_id = org_id
                        rca.team_id = team_id
                        await self._learning_store.store(rca)
                        rs.set_output({"rca": rca.learning[:200]})
                    else:
                        rs.set_output({"rca": "none"})
            else:
                rca = await self._rca_extractor.extract_rca(
                    user_text,
                    result.tool_history,
                )
                if rca:
                    rca.agent_id = self.identity.name
                    await self._learning_store.store(rca)

        if result.tool_history and self._learning_extractor and self._learning_store:
            if trace:
                with trace.span("learning.extraction") as ls:
                    corrections = self._learning_extractor.extract_corrections(
                        user_text,
                        result.tool_history,
                    )
                    positives = self._learning_extractor.extract_positive_patterns(
                        user_text,
                        result.tool_history,
                    )
                    all_learnings = corrections + positives
                    for learning in all_learnings:
                        learning.agent_id = self.identity.name
                        learning.org_id = org_id
                        learning.team_id = team_id
                        await self._learning_store.store(learning)
                    ls.set_output(
                        {
                            "corrections": len(corrections),
                            "positives": len(positives),
                        }
                    )
            else:
                corrections = self._learning_extractor.extract_corrections(
                    user_text,
                    result.tool_history,
                )
                for learning in corrections:
                    learning.agent_id = self.identity.name
                    learning.org_id = org_id
                    learning.team_id = team_id
                    await self._learning_store.store(learning)

        if self._learning_promoter and injected_learning_ids:
            await self._learning_promoter.check_and_promote(org_id=org_id)

        if session_id and self._session_store and result.response:
            save_msgs: list[dict[str, str]] = []
            if user_text:
                save_msgs.append({"role": "user", "content": user_text})
            save_msgs.append({"role": "assistant", "content": result.response})
            await self._session_store.append_messages(session_id, save_msgs)

        if self._outcome_store:
            from maistro.types.memory import Outcome

            charge_info: dict[str, Any] = {
                "charged_microchips": 0,
                "pricing_version": "",
            }
            if self._coin_ledger:
                charge_info = await self._coin_ledger.charge_usage(
                    request_id=session_id or "",
                    org_id=org_id,
                    team_id=team_id,
                    user_id=getattr(auth, "user_id", ""),
                    model_used=model,
                    provider="",
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )

            outcome = Outcome(
                request_id=session_id or "",
                task_type="",
                model_used=model,
                provider="",
                tool_calls=[
                    {
                        "name": str(h.get("tool_name", "")),
                        "success": not str(h.get("result", "")).startswith("Error"),
                    }
                    for h in (result.tool_history or [])
                ],
                success=not tool_had_failures,
                error_type="tool_error" if tool_had_failures else "",
                org_id=org_id,
                team_id=team_id,
                user_id=getattr(auth, "user_id", ""),
                agent_id=self.identity.name,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                charged_microchips=int(str(charge_info.get("charged_microchips", 0))),
                pricing_version=str(charge_info.get("pricing_version", "")),
            )
            await self._outcome_store.record(outcome)

        if injected_learning_ids and self._learning_store:
            await self._learning_store.mark_outcome(
                injected_learning_ids,
                success=not tool_had_failures,
                org_id=org_id,
            )

        if trace:
            tool_success_count = 0
            tool_fail_count = 0
            tools_used: list[str] = []
            for th in result.tool_history or []:
                r = str(th.get("result", ""))
                tools_used.append(str(th.get("tool_name", "")))
                if r.startswith("Error") or "error" in r[:50].lower():
                    tool_fail_count += 1
                else:
                    tool_success_count += 1

            trace.update(
                {
                    "agent": self.identity.name,
                    "model": model,
                    "response_length": str(len(result.response or "")),
                    "tool_calls_total": str(len(result.tool_history) if result.tool_history else 0),
                    "tool_calls_success": str(tool_success_count),
                    "tool_calls_failed": str(tool_fail_count),
                    "tools_used": ",".join(dict.fromkeys(tools_used)),
                    "session_history_injected": str(session_history_count),
                    "learnings_injected": str(len(injected_learning_ids)),
                }
            )
            trace.end()

        return AgentResponse(
            content=result.response or "",
            agent_name=self.identity.name,
        )

    async def _delegate(
        self,
        result: Any,
        *,
        auth: Any,
        session_id: str | None,
        model_override: str | None,
        status_callback: Any,
        classified_task_type: str,
        depth: int,
        trace: Any,
    ) -> AgentResponse | None:
        """Invoke the sub-agent chosen by the reasoning strategy.

        Returns the sub-agent's :class:`AgentResponse`, or ``None`` if the
        target cannot be resolved (caller then falls back to normal handling).
        """
        import logging as _log

        log = _log.getLogger("maistro.agent")
        target_name = result.delegate_to

        _MAX_DELEGATION_DEPTH = 5
        if depth >= _MAX_DELEGATION_DEPTH:
            log.warning(
                "Delegation depth limit reached: agent=%s target=%s depth=%d",
                self.identity.name,
                target_name,
                depth,
            )
            if trace:
                trace.score("delegation_depth_exceeded", 0.0, comment=target_name)
                trace.end()
            return AgentResponse(
                content="Delegation chain too deep; aborting.",
                agent_name=self.identity.name,
            )

        target = self._resolve_agent(target_name)
        if target is None:
            log.warning(
                "Delegation target unresolved: agent=%s target=%s",
                self.identity.name,
                target_name,
            )
            return None

        delegate_text = result.delegate_message or ""
        delegate_messages = [{"role": "user", "content": delegate_text}]

        if trace:
            trace.update({"delegated_to": target_name})

        return await target.handle(
            messages=delegate_messages,
            auth=auth,
            session_id=session_id,
            model_override=model_override,
            status_callback=status_callback,
            classified_task_type=classified_task_type,
            _delegation_depth=depth + 1,
        )

    def _resolve_agent(self, name: str) -> Agent | None:
        """Look up a sub-agent by name via the configured resolver.

        The resolver may be a callable ``name -> Agent | None`` or a mapping.
        """
        resolver = self._agent_resolver
        if resolver is None:
            return None
        target = resolver(name) if callable(resolver) else resolver.get(name)
        return target if isinstance(target, Agent) else None
