from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import stores
from fastapi import APIRouter, HTTPException
from models.schemas import MCPServer, MCPTool
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["mcp"])

logger = logging.getLogger(__name__)


async def _health_check(server: MCPServer) -> MCPServer:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(server.url)
            if r.status_code < 500:
                return server.model_copy(update={
                    "status": "connected",
                    "last_ping": datetime.now(UTC),
                })
    except Exception:
        pass
    return server.model_copy(update={"status": "disconnected"})


@router.get("/servers", response_model=list[MCPServer])
async def list_servers() -> list[MCPServer]:
    import asyncio

    servers = list(stores.mcp_servers.values())
    checked = await asyncio.gather(*[_health_check(s) for s in servers])
    for s in checked:
        stores.mcp_servers[s.id] = s
    return list(checked)


@router.get("/servers/{server_id}", response_model=MCPServer)
def get_server(server_id: str) -> MCPServer:
    if server_id not in stores.mcp_servers:
        raise HTTPException(status_code=404, detail="server not found")
    return stores.mcp_servers[server_id]


class CreateServerBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    url: str


@router.post("/servers", response_model=MCPServer, status_code=201)
def add_server(body: CreateServerBody) -> MCPServer:
    sid = str(uuid4())
    server = MCPServer(
        id=sid,
        name=body.name,
        description=body.description,
        url=body.url,
        status="connecting",
        tools_count=0,
    )
    stores.mcp_servers[sid] = server
    return server


@router.delete("/servers/{server_id}", status_code=204)
def delete_server(server_id: str) -> None:
    if server_id not in stores.mcp_servers:
        raise HTTPException(status_code=404, detail="server not found")
    stores.mcp_servers.pop(server_id)


@router.post("/servers/{server_id}/scan")
def scan_server(server_id: str) -> dict:
    if server_id not in stores.mcp_servers:
        raise HTTPException(status_code=404, detail="server not found")
    return {"findings": [], "status": "clean"}


@router.get("/tools", response_model=list[MCPTool])
def list_tools() -> list[MCPTool]:
    return list(stores.mcp_tools.values())


class DiscoverBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str


@router.post("/discover")
def discover_tools(body: DiscoverBody) -> dict:
    return {"tools": [], "status": "scanning"}
