from __future__ import annotations

from fastapi import APIRouter

from models.schemas import MCPServer, MCPTool

import stores

router = APIRouter(tags=["mcp"])


@router.get("/servers", response_model=list[MCPServer])
def list_servers() -> list[MCPServer]:
    return list(stores.mcp_servers.values())


@router.get("/tools", response_model=list[MCPTool])
def list_tools() -> list[MCPTool]:
    return list(stores.mcp_tools.values())
