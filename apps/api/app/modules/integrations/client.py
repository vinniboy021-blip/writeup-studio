# SPDX-License-Identifier: MIT
"""Bounded Streamable HTTP MCP client with session initialization."""

from __future__ import annotations

import json
import uuid

import httpx


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, url: str, token: str, timeout: float, max_bytes: int, *, transport=None):
        self.url = url
        self.max_bytes = max_bytes
        self.headers = {"Accept": "application/json, text/event-stream"}
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.client = httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.client.aclose()

    async def request(self, method: str, params: dict | None = None, *, notification=False):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        request_id = str(uuid.uuid4())
        if not notification:
            payload["id"] = request_id
        async with self.client.stream("POST", self.url, json=payload, headers=self.headers) as response:
            response.raise_for_status()
            if notification and response.status_code in {200, 202, 204}:
                return None
            session = response.headers.get("Mcp-Session-Id")
            if session:
                if len(session) > 256 or any(ord(char) < 32 for char in session):
                    raise MCPError("Invalid MCP session")
                self.headers["Mcp-Session-Id"] = session
            content_type = response.headers.get("Content-Type", "")
            buffer = bytearray()
            async for chunk in response.aiter_bytes():
                buffer.extend(chunk)
                if len(buffer) > self.max_bytes:
                    raise MCPError("Resposta MCP excedeu o limite")
                if "text/event-stream" in content_type:
                    decoded = bytes(buffer).decode("utf-8", errors="strict").replace("\r\n", "\n")
                    for event in decoded.split("\n\n")[:-1]:
                        lines = [line[5:].strip() for line in event.splitlines() if line.startswith("data:")]
                        if lines:
                            value = json.loads("\n".join(lines))
                            if value.get("id") == request_id:
                                return self._result(value, request_id)
            if "text/event-stream" in content_type:
                raise MCPError("Resposta MCP sem resultado correspondente")
            try:
                value = json.loads(buffer)
            except (ValueError, UnicodeError) as exc:
                raise MCPError("Resposta MCP inválida") from exc
            return self._result(value, request_id)

    @staticmethod
    def _result(value, request_id):
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or value.get("id") != request_id:
            raise MCPError("Resposta JSON-RPC não corresponde à requisição")
        if "error" in value or "result" not in value:
            raise MCPError("Servidor MCP rejeitou a operação")
        return value["result"]

    async def initialize(self):
        result = await self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "CTF Writeup Studio", "version": "1.0.0"},
            },
        )
        if not isinstance(result, dict):
            raise MCPError("Resposta initialize inválida")
        version = result.get("protocolVersion")
        if version not in {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}:
            raise MCPError("Versão MCP não suportada")
        self.headers["MCP-Protocol-Version"] = version
        await self.request("notifications/initialized", notification=True)
        return result

    async def tools(self):
        tools = []
        cursor = None
        for _ in range(10):
            result = await self.request("tools/list", {"cursor": cursor} if cursor else {})
            if not isinstance(result, dict):
                raise MCPError("Lista de ferramentas MCP inválida")
            batch = result.get("tools", [])
            if not isinstance(batch, list) or len(tools) + len(batch) > 500:
                raise MCPError("Lista de ferramentas MCP inválida")
            tools.extend(batch)
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
        raise MCPError("Paginação MCP excedeu o limite")

    async def call(self, name: str, arguments: dict):
        result = await self.request("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict) or result.get("isError"):
            raise MCPError("Ferramenta MCP falhou")
        return result
