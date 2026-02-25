"""Task router — analyzes user input and routes to the appropriate agent."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Keywords that suggest code-specific tasks
CODE_KEYWORDS = [
    r"\bscript\b", r"\bcode\b", r"\bprogram\b", r"\bfunction\b",
    r"\bwrite\s+(a|me|the)\s+\w+\s*(script|program|code)",
    r"\bparse\b", r"\bregex\b", r"\bjson\b", r"\byaml\b",
    r"\bgenerate\s+(a|the)?\s*config",
    r"\banalyze\s+(this|the)?\s*(code|script|file)",
    r"\brefactor\b", r"\bdebug\s+(this|the)?\s*(code|script)",
    r"\bpython\b", r"\bbash\s+script\b", r"\bshell\s+script\b",
]

CODE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CODE_KEYWORDS]

# Keywords suggesting complex diagnostic tasks (benefit from thinking mode)
COMPLEX_KEYWORDS = [
    r"\bwhy\s+(is|are|does|did|do)\b",
    r"\bdiagnose\b", r"\btroubleshoot\b", r"\binvestigate\b",
    r"\broot\s+cause\b", r"\bintermittent\b",
    r"\bkeeps?\s+(crash|fail|restart|dying)",
    r"\bslow\b.*\b(response|latency|timeout)\b",
    r"\bcan't\s+(connect|reach|access)\b",
    r"\bnot\s+(work|respond|start|running)\b",
]

COMPLEX_PATTERNS = [re.compile(p, re.IGNORECASE) for p in COMPLEX_KEYWORDS]


class AgentType:
    PLANNER = "planner"
    CODER = "coder"


class TaskRouter:
    """Analyzes user input and routes to the appropriate agent."""

    def route(self, message: str) -> str:
        """Returns AgentType.PLANNER or AgentType.CODER."""
        for pattern in CODE_PATTERNS:
            if pattern.search(message):
                logger.info("Routing to CODER agent (matched: %s)", pattern.pattern)
                return AgentType.CODER
        logger.info("Routing to PLANNER agent (default)")
        return AgentType.PLANNER

    def needs_thinking(self, message: str) -> bool:
        """Returns True if the task is complex enough to benefit from thinking mode."""
        for pattern in COMPLEX_PATTERNS:
            if pattern.search(message):
                return True
        return False
