"""Session manager — handles per-connection state and message flow."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from silicon_valet.config import ValetConfig
from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.context import MemoryContext
from silicon_valet.memory.episodic import Episode, EpisodicMemory
from silicon_valet.orchestrator.planner import PlannerAgent
from silicon_valet.orchestrator.coder import CoderAgent
from silicon_valet.orchestrator.router import AgentType, TaskRouter
from silicon_valet.orchestrator.handoff import HandoffManager
from silicon_valet.risk.engine import RiskEngine
from silicon_valet.server.protocol import Message, MessageType

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages a single client session over WebSocket."""

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
        self.router = TaskRouter()

        self.session_id = str(uuid.uuid4())[:8]
        self.history: list[dict] = []
        self.command_log: list[dict] = []
        self._ws = None
        self._pending_approval: asyncio.Future | None = None

    async def start_session(self, ws) -> None:
        """Initialize session and send status to client."""
        self._ws = ws
        summary = self.dna.get_context_summary()
        status = Message.session_status(
            session_id=self.session_id,
            dna_summary=summary,
            services_count=len(self.dna.get_all_services()),
            nodes_count=len(self.dna.get_all_nodes()),
        )
        await ws.send(status.to_json())
        logger.info("Session %s started", self.session_id)

    async def handle_message(self, message: Message, ws) -> None:
        """Route an incoming message to the appropriate handler."""
        self._ws = ws

        if message.type == MessageType.USER_INPUT:
            text = message.payload.get("text", "").strip()
            if not text:
                return
            # Check for slash commands
            if text.startswith("/"):
                await self._handle_command(text, ws)
                return
            await self._handle_user_input(text, ws)

        elif message.type == MessageType.RISK_RESPONSE:
            if self._pending_approval is not None:
                approved = message.payload.get("approved", False)
                self._pending_approval.set_result(approved)

    async def _handle_user_input(self, text: str, ws) -> None:
        """Process user input through the orchestrator."""
        self.history.append({"role": "user", "content": text})

        agent_type = self.router.route(text)

        try:
            if agent_type == AgentType.CODER:
                async for token in self.coder.generate(text):
                    await ws.send(Message.token(token).to_json())
            else:
                async for token in self.planner.run(text, self.history):
                    await ws.send(Message.token(token).to_json())

            await ws.send(Message.stream_end().to_json())

        except Exception as e:
            logger.error("Error processing message: %s", e)
            await ws.send(Message.error(str(e)).to_json())

    async def _handle_command(self, text: str, ws) -> None:
        """Handle slash commands."""
        from silicon_valet.cli.commands import handle_command
        result = await handle_command(text, self)
        if result:
            await ws.send(Message.token(result).to_json())
            await ws.send(Message.stream_end().to_json())

    def get_approval_callback(self):
        """Create an approval callback for the risk engine.

        Returns an async function that sends a risk prompt to the client
        and waits for the response.
        """
        async def callback(command: str, tier: str, explanation: str) -> bool:
            if self._ws is None:
                logger.warning("No WebSocket connection for approval")
                return False
            # Send risk prompt
            prompt = Message.risk_prompt(command, tier, explanation)
            await self._ws.send(prompt.to_json())
            # Wait for response
            self._pending_approval = asyncio.get_event_loop().create_future()
            try:
                approved = await asyncio.wait_for(self._pending_approval, timeout=300)
                return approved
            except asyncio.TimeoutError:
                logger.warning("Approval timed out for: %s", command)
                return False
            finally:
                self._pending_approval = None

        return callback

    async def end_session(self) -> None:
        """Clean up session and optionally save episode."""
        if len(self.history) > 2:
            # Save a brief episode summary
            try:
                user_msgs = [m["content"] for m in self.history if m["role"] == "user"]
                episode = Episode(
                    session_id=self.session_id,
                    problem_description=user_msgs[0] if user_msgs else "Unknown",
                    conversation_summary=f"Session with {len(self.history)} messages",
                    outcome="completed",
                    tags=[],
                    resolution_summary="Session ended normally",
                )
                await self.episodic.store(episode)
            except Exception as e:
                logger.warning("Failed to save session episode: %s", e)

        logger.info("Session %s ended (%d messages)", self.session_id, len(self.history))
