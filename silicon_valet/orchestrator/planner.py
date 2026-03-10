"""Planner agent — main orchestrator using Qwen-Agent with Ollama backend."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from silicon_valet.config import ValetConfig
from silicon_valet.memory.context import MemoryContext
from silicon_valet.orchestrator.router import TaskRouter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are Silicon Valet, an infrastructure intelligence assistant.
You are managing a {environment_description}.
You help users understand and manage their infrastructure through conversation.

CORE PRINCIPLES:
1. Safety first — all commands go through the risk engine. Never bypass it.
2. Explain before acting — tell the user what you plan to do and why.
3. Use your memory — search history and runbooks before starting from scratch.
4. Verify changes — after modifying anything, confirm the change took effect.
5. Be honest about uncertainty — if you're unsure, say so.

AVAILABLE CONTEXT:
{context}

RISK TIERS:
- GREEN: Read-only commands execute automatically
- YELLOW: Modification commands require user confirmation
- RED: Destructive commands require explicit type-to-confirm

When diagnosing problems:
1. First check the DNA for relevant services and recent changes
2. Search memory for similar past incidents
3. Gather information with read-only commands
4. Form a hypothesis and explain it to the user
5. Propose a fix with risk classification
6. Verify the fix after execution

Keep responses concise and actionable. Use plain English."""


class PlannerAgent:
    """Main orchestrator agent using Qwen-Agent with Ollama backend."""

    def __init__(
        self,
        config: ValetConfig,
        tool_names: list[str],
        memory: MemoryContext,
    ):
        self.config = config
        self.tool_names = tool_names
        self.memory = memory
        self.router = TaskRouter()
        self._agent = None

    def _ensure_agent(self, system_prompt: str):
        """Lazily initialize the Qwen-Agent assistant."""
        try:
            from qwen_agent.agents import Assistant

            llm_cfg = {
                "model": self.config.orchestrator_model,
                "model_server": self.config.ollama_orchestrator + "/v1",
                "api_key": "EMPTY",
                "generate_cfg": {"top_p": 0.8},
            }
            self._agent = Assistant(
                llm=llm_cfg,
                function_list=self.tool_names,
                system_message=system_prompt,
            )
        except ImportError:
            logger.warning("qwen-agent not installed; planner will use direct Ollama calls")
            self._agent = None

    async def run(
        self,
        user_message: str,
        session_history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens for a user message.

        Builds context from DNA + memory, initializes agent, and yields tokens.
        """
        # Build context
        context = await self.memory.build_context(user_message)

        # Build environment description from detected capabilities
        env_desc = "server"
        if self.config.capabilities:
            env_desc = self.config.capabilities.environment_description

        system_prompt = SYSTEM_PROMPT.format(
            context=context,
            environment_description=env_desc,
        )

        # Thinking mode for complex diagnostics
        use_thinking = self.router.needs_thinking(user_message)
        if use_thinking:
            user_message = "/think " + user_message

        # Try Qwen-Agent first, fall back to direct Ollama
        if self._agent is None:
            self._ensure_agent(system_prompt)

        if self._agent is not None:
            async for token in self._run_qwen_agent(user_message, session_history or []):
                yield token
        else:
            async for token in self._run_ollama_direct(user_message, system_prompt, session_history or []):
                yield token

    async def _run_qwen_agent(
        self, user_message: str, history: list[dict]
    ) -> AsyncIterator[str]:
        """Run via Qwen-Agent (preferred path)."""
        messages = history + [{"role": "user", "content": user_message}]
        try:
            responses = self._agent.run(messages=messages)
            for response_batch in responses:
                for msg in response_batch:
                    if msg.get("role") == "assistant" and msg.get("content"):
                        content = msg["content"]
                        # Strip thinking blocks unless user wants reasoning
                        content = self._strip_thinking(content)
                        yield content
        except Exception as e:
            logger.error("Qwen-Agent error: %s", e)
            yield f"I encountered an error processing your request: {e}"

    async def _run_ollama_direct(
        self, user_message: str, system_prompt: str, history: list[dict]
    ) -> AsyncIterator[str]:
        """Fallback: stream directly from Ollama API."""
        import httpx

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.config.orchestrator_model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": self.config.num_ctx, "top_p": 0.8},
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.config.ollama_orchestrator}/api/chat",
                    json=payload,
                ) as resp:
                    buffer = ""
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        import json
                        data = json.loads(line)
                        if data.get("done"):
                            break
                        token = data.get("message", {}).get("content", "")
                        buffer += token
                        # Strip thinking blocks incrementally
                        if "<think>" in buffer and "</think>" not in buffer:
                            continue
                        if "</think>" in buffer:
                            import re
                            buffer = re.sub(r"<think>.*?</think>", "", buffer, flags=re.DOTALL)
                        if buffer:
                            yield buffer
                            buffer = ""
        except Exception as e:
            logger.error("Ollama direct call error: %s", e)
            yield f"I couldn't reach the language model: {e}"

    @staticmethod
    def _strip_thinking(content: str) -> str:
        """Remove <think>...</think> blocks from output."""
        import re
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
