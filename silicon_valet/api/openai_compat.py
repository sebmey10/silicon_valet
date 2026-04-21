"""OpenAI-compatible HTTP API for Silicon Valet.

Exposes `/v1/models` and `/v1/chat/completions` so any OpenAI-compatible client
— primarily OpenWebUI — can chat with the Silicon Valet agent exactly like it
would chat with GPT-4. Every message still flows through the Planner + risk
engine, so tool calls are classified the same way as over the CLI.

Auth: if config.auth_token is set, clients must send
    Authorization: Bearer <token>
OpenWebUI stores this per external connection.

YELLOW/RED approval: the interactive approval loop is only fully supported via
the WebSocket CLI. Over HTTP, we default to denying YELLOW/RED tool calls
unless SV_HTTP_AUTO_APPROVE_YELLOW=true. The agent will stream back a message
explaining what approval is needed — the user can then run the CLI for the
specific operation, or accept the risk by setting the env var.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from silicon_valet.config import ValetConfig
from silicon_valet.memory.context import MemoryContext
from silicon_valet.orchestrator.planner import PlannerAgent
from silicon_valet.risk.engine import RiskEngine

logger = logging.getLogger(__name__)


def _openai_chunk(model: str, delta_content: str, finish_reason: str | None = None) -> dict:
    """Build an OpenAI-style streaming chunk."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": delta_content} if delta_content else {},
            "finish_reason": finish_reason,
        }],
    }


class OpenAICompatServer:
    """FastAPI app exposing an OpenAI-compatible surface over Silicon Valet."""

    def __init__(
        self,
        config: ValetConfig,
        planner: PlannerAgent,
        memory: MemoryContext,
        risk_engine: RiskEngine,
    ) -> None:
        self.config = config
        self.planner = planner
        self.memory = memory
        self.risk_engine = risk_engine
        self._http_approval_callback = self._make_http_approval_callback()
        # Inject callback so tool calls from HTTP sessions are gated the same way.
        # NOTE: this is a process-global setting; the WebSocket server overrides it
        # per-connection for interactive approvals.
        self.risk_engine.approval_callback = self._http_approval_callback

    def _make_http_approval_callback(self):
        """Approval callback for the HTTP/OpenWebUI path.

        No interactive UI here — we auto-approve GREEN (handled by the risk
        engine itself), and deny YELLOW/RED unless the operator has opted in
        by setting SV_HTTP_AUTO_APPROVE_YELLOW=true.
        """
        allow_yellow = self.config.http_auto_approve_yellow

        async def callback(command: str, tier: str, explanation: str) -> bool:
            if tier == "green":
                return True
            if tier == "yellow" and allow_yellow:
                logger.info("HTTP auto-approve yellow: %s", command)
                return True
            logger.info("HTTP denied %s: %s", tier, command)
            return False

        return callback

    def build_app(self):
        """Construct and return the FastAPI app."""
        try:
            from fastapi import FastAPI, Header, HTTPException, Request
            from fastapi.responses import StreamingResponse, JSONResponse
        except ImportError as e:
            raise RuntimeError(
                "fastapi is required for the HTTP API. Install with: pip install fastapi uvicorn"
            ) from e

        app = FastAPI(title="Silicon Valet", version="0.1.0")
        model_name = "silicon-valet"

        def check_auth(authorization: str | None) -> None:
            expected = self.config.auth_token
            if not expected:
                return  # Auth disabled
            if not authorization:
                raise HTTPException(status_code=401, detail="Missing Authorization header")
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or token.strip() != expected:
                raise HTTPException(status_code=401, detail="Invalid token")

        @app.get("/v1/models")
        async def list_models(authorization: str | None = Header(default=None)):
            check_auth(authorization)
            return {
                "object": "list",
                "data": [{
                    "id": model_name,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "silicon-valet",
                }],
            }

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.post("/v1/chat/completions")
        async def chat_completions(request: Request,
                                   authorization: str | None = Header(default=None)):
            check_auth(authorization)
            body = await request.json()
            messages = body.get("messages", [])
            stream = bool(body.get("stream", False))
            requested_model = body.get("model", model_name)

            user_message = ""
            history: list[dict] = []
            for m in messages:
                role = m.get("role")
                content = m.get("content", "")
                if isinstance(content, list):
                    # OpenWebUI can send content as a list of parts
                    content = " ".join(
                        p.get("text", "") for p in content if isinstance(p, dict)
                    )
                if role == "user":
                    user_message = content
                    history.append({"role": "user", "content": content})
                elif role == "assistant":
                    history.append({"role": "assistant", "content": content})
                elif role == "system":
                    # Silicon Valet builds its own system prompt; ignore client-provided ones.
                    continue

            # Last user message is the current turn; everything before it is history.
            prior_history = history[:-1] if history and history[-1]["role"] == "user" else history

            if stream:
                return StreamingResponse(
                    self._stream_sse(requested_model, user_message, prior_history),
                    media_type="text/event-stream",
                )

            # Non-streaming: aggregate tokens
            full = ""
            async for token in self.planner.run(user_message, prior_history):
                full += token
            return JSONResponse({
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": requested_model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": full},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })

        return app

    async def _stream_sse(
        self,
        model: str,
        user_message: str,
        history: list[dict],
    ) -> AsyncIterator[bytes]:
        """Yield OpenAI-compatible SSE chunks."""
        try:
            async for token in self.planner.run(user_message, history):
                chunk = _openai_chunk(model, token)
                yield f"data: {json.dumps(chunk)}\n\n".encode()
        except Exception as e:
            logger.exception("HTTP stream error")
            err = _openai_chunk(model, f"\n\n[silicon-valet error: {e}]")
            yield f"data: {json.dumps(err)}\n\n".encode()

        # Final chunk with finish_reason
        final = _openai_chunk(model, "", finish_reason="stop")
        yield f"data: {json.dumps(final)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    async def serve(self) -> None:
        """Run the HTTP server with uvicorn. Awaits until shutdown."""
        try:
            import uvicorn
        except ImportError as e:
            raise RuntimeError(
                "uvicorn is required for the HTTP API. Install with: pip install uvicorn"
            ) from e

        app = self.build_app()
        uv_config = uvicorn.Config(
            app,
            host=self.config.http_host,
            port=self.config.http_port,
            log_level=self.config.log_level.lower(),
            access_log=False,
        )
        server = uvicorn.Server(uv_config)
        logger.info(
            "Silicon Valet HTTP API listening on http://%s:%d (OpenAI-compatible)",
            self.config.http_host,
            self.config.http_port,
        )
        await server.serve()
