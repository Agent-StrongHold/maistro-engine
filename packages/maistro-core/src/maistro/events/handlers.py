"""Built-in action handlers for the event bus.

Uses ServiceKeyClient for authenticated cross-service calls when available.
Falls back to raw httpx when no service client is configured (backward compat).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from maistro.auth.client import ServiceKeyClient
from maistro.events.bus import Event, Trigger

logger = logging.getLogger("maistro.events.handlers")

_global_client: ServiceKeyClient | None = None


def set_service_client(client: ServiceKeyClient | None) -> None:
    """Set the global ServiceKeyClient for all handlers to use."""
    global _global_client
    _global_client = client


def _get_client() -> ServiceKeyClient | None:
    return _global_client


async def webhook_action(trigger: Trigger, event: Event) -> None:
    url = trigger.action_config.get("url", "")
    method = trigger.action_config.get("method", "POST").upper()
    extra_headers = trigger.action_config.get("headers", {})
    timeout = trigger.action_config.get("timeout", 10)

    body = {
        "trigger_id": trigger.trigger_id,
        "trigger_name": trigger.name,
        "event": {
            "id": event.event_id,
            "category": event.category.value,
            "type": event.event_type,
            "source": event.source,
            "payload": event.payload,
            "timestamp": event.timestamp,
        },
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    headers.update(extra_headers)
    if "Authorization" not in headers and trigger.action_config.get("bearer_token"):
        headers["Authorization"] = f"Bearer {trigger.action_config['bearer_token']}"

    svc = _get_client()
    if svc:
        resp = await svc.request(method, url, json=body, headers=headers, timeout=timeout)
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, json=body, headers=headers)
    logger.info("Webhook %s %s → %d", method, url, resp.status_code)


async def conductor_chat_action(trigger: Trigger, event: Event) -> None:
    base_url = trigger.action_config.get("conductor_url", "http://localhost:8100")
    api_key = trigger.action_config.get("api_key", "")
    model = trigger.action_config.get("model", "auto")
    message_template = trigger.action_config.get("message", "")

    message = (
        message_template.format(**event.payload)
        if message_template
        else (
            f"[Trigger: {trigger.name}] Event {event.event_type} from {event.source}: "
            f"{event.payload}"
        )
    )

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    svc = _get_client()
    if svc:
        resp = await svc.post(
            f"{base_url}/v1/chat/completions", json=payload, headers=headers, timeout=30
        )
    else:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
    logger.info("Conductor action %s → %d", trigger.name, resp.status_code)


async def coinswarm_action(trigger: Trigger, event: Event) -> None:
    base_url = trigger.action_config.get("coinswarm_url", "http://localhost:8080")
    endpoint = trigger.action_config.get("endpoint", "")
    params = trigger.action_config.get("params", {})

    resolved_params = {
        k: (v.format(**event.payload) if isinstance(v, str) else v) for k, v in params.items()
    }

    url = f"{base_url}{endpoint}"
    svc = _get_client()
    if svc:
        resp = await svc.post(url, json=resolved_params, timeout=15)
    else:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=resolved_params)
    logger.info("CoinSwarm action %s %s → %d", trigger.name, endpoint, resp.status_code)


async def ha_action(trigger: Trigger, event: Event) -> None:
    base_url = trigger.action_config.get("ha_url", "http://localhost:8123")
    token = trigger.action_config.get("ha_token", "")
    domain = trigger.action_config.get("domain", "automation")
    service = trigger.action_config.get("service", "trigger")
    entity_id = trigger.action_config.get("entity_id", "")

    headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {}
    if entity_id:
        payload["entity_id"] = entity_id
    payload.update(trigger.action_config.get("service_data", {}))

    url = f"{base_url}/api/services/{domain}/{service}"
    svc = _get_client()
    if svc:
        resp = await svc.post(url, json=payload, headers=headers, timeout=10)
    else:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
    logger.info("HA action %s %s.%s → %d", trigger.name, domain, service, resp.status_code)


async def log_action(trigger: Trigger, event: Event) -> None:
    logger.info(
        "TRIGGER [%s] event=%s/%s source=%s payload=%s",
        trigger.name,
        event.category.value,
        event.event_type,
        event.source,
        event.payload,
    )


BUILTIN_HANDLERS = {
    "webhook": webhook_action,
    "conductor_chat": conductor_chat_action,
    "coinswarm": coinswarm_action,
    "ha": ha_action,
    "log": log_action,
}
