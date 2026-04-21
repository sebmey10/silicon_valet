"""WebSocket server — accepts client connections and manages sessions."""

from __future__ import annotations

import asyncio
import logging

import websockets

from silicon_valet.config import ValetConfig
from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.context import MemoryContext
from silicon_valet.memory.episodic import EpisodicMemory
from silicon_valet.orchestrator.planner import PlannerAgent
from silicon_valet.orchestrator.coder import CoderAgent
from silicon_valet.orchestrator.handoff import HandoffManager
from silicon_valet.risk.engine import RiskEngine
from silicon_valet.server.protocol import Message, MessageType
from silicon_valet.server.session import SessionManager

logger = logging.getLogger(__name__)


class ValetServer:
    """WebSocket server for Silicon Valet."""

    def __init__(
        self,
        config: ValetConfig,
        dna: DNAStore,
        memory: MemoryContext,
        episodic: EpisodicMemory,
        risk_engine: RiskEngine,
        planner: PlannerAgent,
        coder: CoderAgent,
        handoff: HandoffManager,
    ):
        self.config = config
        self.dna = dna
        self.memory = memory
        self.episodic = episodic
        self.risk_engine = risk_engine
        self.planner = planner
        self.coder = coder
        self.handoff = handoff
        self._server = None

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await websockets.serve(
            self.handler,
            self.config.ws_host,
            self.config.ws_port,
            ping_interval=30,
            ping_timeout=10,
        )
        logger.info(
            "Silicon Valet server listening on ws://%s:%d",
            self.config.ws_host,
            self.config.ws_port,
        )
        await self._server.wait_closed()

    async def handler(self, websocket) -> None:
        """Handle a single client connection."""
        # Optional bearer-token auth. The token is also accepted as a
        # ?token=... query param so browsers without header support still work.
        expected = getattr(self.config, "auth_token", "")
        if expected:
            auth_hdr = websocket.request_headers.get("Authorization", "") \
                if hasattr(websocket, "request_headers") else ""
            token = ""
            if auth_hdr.lower().startswith("bearer "):
                token = auth_hdr.split(" ", 1)[1].strip()
            if not token:
                try:
                    from urllib.parse import urlparse, parse_qs
                    q = parse_qs(urlparse(getattr(websocket, "path", "")).query)
                    token = (q.get("token") or [""])[0]
                except Exception:
                    token = ""
            if token != expected:
                logger.warning("Rejected WebSocket connection: bad/missing token")
                try:
                    await websocket.close(code=4401, reason="unauthorized")
                except Exception:
                    pass
                return

        session = SessionManager(
            config=self.config,
            dna=self.dna,
            memory=self.memory,
            episodic=self.episodic,
            risk_engine=self.risk_engine,
            planner=self.planner,
            coder=self.coder,
            handoff=self.handoff,
        )

        # Inject approval callback into risk engine for this session
        self.risk_engine.approval_callback = session.get_approval_callback()

        try:
            await session.start_session(websocket)

            async for raw in websocket:
                try:
                    message = Message.from_json(raw)
                    await session.handle_message(message, websocket)
                except Exception as e:
                    logger.error("Error handling message: %s", e)
                    await websocket.send(Message.error(str(e)).to_json())

        except websockets.ConnectionClosed:
            logger.info("Client disconnected: session %s", session.session_id)
        except Exception as e:
            logger.error("Session error: %s", e)
        finally:
            await session.end_session()

    async def stop(self) -> None:
        """Stop the server gracefully."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Server stopped")
