"""Coder agent — code specialist using qwen2.5-coder via Ollama."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from silicon_valet.config import ValetConfig

logger = logging.getLogger(__name__)

CODER_SYSTEM_PROMPT = """\
You are a code specialist assistant within Silicon Valet.
You help with:
- Analyzing configuration files, scripts, and logs
- Writing shell scripts, Python scripts, and config files
- Debugging code issues
- Generating configuration snippets
- Parsing and formatting data (JSON, YAML, log formats)

Be precise, use proper formatting with code blocks, and explain your code clearly.
Keep responses focused on the code task at hand."""


class CoderAgent:
    """Code specialist agent using qwen2.5-coder on the secondary Ollama instance."""

    def __init__(self, config: ValetConfig):
        self.config = config
        self.model = config.coder_model
        self.ollama_url = config.ollama_coder

    async def analyze(self, code: str, question: str) -> AsyncIterator[str]:
        """Analyze a piece of code and answer a question about it."""
        prompt = f"Here is the code to analyze:\n\n```\n{code}\n```\n\n{question}"
        async for token in self._stream(prompt):
            yield token

    async def generate(self, spec: str) -> AsyncIterator[str]:
        """Generate code from a specification."""
        async for token in self._stream(spec):
            yield token

    async def _stream(self, user_message: str) -> AsyncIterator[str]:
        """Stream tokens from the coder model."""

        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": self.config.num_ctx, "top_p": 0.8},
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        if data.get("done"):
                            break
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
        except Exception as e:
            logger.error("Coder agent error: %s", e)
            yield f"Code analysis error: {e}"
