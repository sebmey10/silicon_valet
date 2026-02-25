"""WebSocket message protocol — message types and serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum


class MessageType(Enum):
    USER_INPUT = "user_input"
    TOKEN_STREAM = "token_stream"
    STREAM_END = "stream_end"
    RISK_PROMPT = "risk_prompt"
    RISK_RESPONSE = "risk_response"
    SESSION_STATUS = "session_status"
    COMMAND_OUTPUT = "command_output"
    ERROR = "error"


@dataclass
class Message:
    type: MessageType
    payload: dict
    timestamp: str | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> Message:
        data = json.loads(raw)
        return cls(
            type=MessageType(data["type"]),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp"),
        )

    @classmethod
    def token(cls, text: str) -> Message:
        return cls(type=MessageType.TOKEN_STREAM, payload={"text": text})

    @classmethod
    def stream_end(cls) -> Message:
        return cls(type=MessageType.STREAM_END, payload={})

    @classmethod
    def risk_prompt(cls, command: str, tier: str, explanation: str) -> Message:
        return cls(
            type=MessageType.RISK_PROMPT,
            payload={"command": command, "tier": tier, "explanation": explanation},
        )

    @classmethod
    def risk_response(cls, approved: bool) -> Message:
        return cls(
            type=MessageType.RISK_RESPONSE,
            payload={"approved": approved},
        )

    @classmethod
    def session_status(cls, **kwargs) -> Message:
        return cls(type=MessageType.SESSION_STATUS, payload=kwargs)

    @classmethod
    def command_output(cls, command: str, output: str, return_code: int) -> Message:
        return cls(
            type=MessageType.COMMAND_OUTPUT,
            payload={"command": command, "output": output, "return_code": return_code},
        )

    @classmethod
    def error(cls, message: str) -> Message:
        return cls(type=MessageType.ERROR, payload={"message": message})
