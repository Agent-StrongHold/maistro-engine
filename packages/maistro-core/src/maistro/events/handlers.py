"""Built-in action handlers for the event bus.

Single-tenant: no auth between services. Direct HTTP calls on local network.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from maistro.events.bus import Event, Trigger

logger = logging.getLogger("maistro.events.handlers")


async def webhook_action(trigger: Trigger, event: Event) -> None:
    url = trigger.action_config.get("url", "")
    method = trigger.action_config.get("method", "POST").upper()
    headers = trigger.action_config.get("headers", {})
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

    if "Authorization" not in headers and trigger.action_config.get("bearer_token"):
        headers["Authorization"] = f"Bearer {trigger.action_config['bearer_token']}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url, json=body, headers=headers)
        logger.info(
            "Webhook %s %s → %d",
            method,
            url,
            response.status_code,
        )


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

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        logger.info(
            "Conductor action %s → %d",
            trigger.name,
            response.status_code,
        )


async def coinswarm_action(trigger: Trigger, event: Event) -> None:
    base_url = trigger.action_config.get("coinswarm_url", "http://localhost:8080")
    endpoint = trigger.action_config.get("endpoint", "")
    params = trigger.action_config.get("params", {})

    resolved_params = {
        k: (v.format(**event.payload) if isinstance(v, str) else v) for k, v in params.items()
    }

    url = f"{base_url}{endpoint}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=resolved_params)
        logger.info(
            "CoinSwarm action %s %s → %d",
            trigger.name,
            endpoint,
            response.status_code,
        )


async def ha_action(trigger: Trigger, event: Event) -> None:
    base_url = trigger.action_config.get("ha_url", "http://localhost:8123")
    token = trigger.action_config.get("ha_token", "")
    domain = trigger.action_config.get("domain", "automation")
    service = trigger.action_config.get("service", "trigger")
    entity_id = trigger.action_config.get("entity_id", "")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {}
    if entity_id:
        payload["entity_id"] = entity_id
    payload.update(trigger.action_config.get("service_data", {}))

    url = f"{base_url}/api/services/{domain}/{service}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload, headers=headers)
        logger.info(
            "HA action %s %s.%s → %d",
            trigger.name,
            domain,
            service,
            response.status_code,
        )


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
