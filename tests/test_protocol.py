"""Tests for the WebSocket message protocol."""

import json
import pytest

from silicon_valet.server.protocol import Message, MessageType


class TestMessageType:
    def test_all_types_exist(self):
        assert MessageType.USER_INPUT.value == "user_input"
        assert MessageType.TOKEN_STREAM.value == "token_stream"
        assert MessageType.STREAM_END.value == "stream_end"
        assert MessageType.RISK_PROMPT.value == "risk_prompt"
        assert MessageType.RISK_RESPONSE.value == "risk_response"
        assert MessageType.SESSION_STATUS.value == "session_status"
        assert MessageType.COMMAND_OUTPUT.value == "command_output"
        assert MessageType.ERROR.value == "error"


class TestMessage:
    def test_create_message(self):
        msg = Message(type=MessageType.USER_INPUT, payload={"text": "hello"})
        assert msg.type == MessageType.USER_INPUT
        assert msg.payload == {"text": "hello"}
        assert msg.timestamp is not None

    def test_serialize_deserialize(self):
        msg = Message(type=MessageType.USER_INPUT, payload={"text": "hello"})
        raw = msg.to_json()
        restored = Message.from_json(raw)
        assert restored.type == msg.type
        assert restored.payload == msg.payload

    def test_token_factory(self):
        msg = Message.token("Hello")
        assert msg.type == MessageType.TOKEN_STREAM
        assert msg.payload == {"text": "Hello"}

    def test_stream_end_factory(self):
        msg = Message.stream_end()
        assert msg.type == MessageType.STREAM_END

    def test_risk_prompt_factory(self):
        msg = Message.risk_prompt("rm -rf /tmp/test", "red", "Deletes files")
        assert msg.type == MessageType.RISK_PROMPT
        assert msg.payload["command"] == "rm -rf /tmp/test"
        assert msg.payload["tier"] == "red"
        assert msg.payload["explanation"] == "Deletes files"

    def test_risk_response_factory(self):
        msg = Message.risk_response(True)
        assert msg.type == MessageType.RISK_RESPONSE
        assert msg.payload["approved"] is True

    def test_session_status_factory(self):
        msg = Message.session_status(session_id="abc", nodes=3)
        assert msg.type == MessageType.SESSION_STATUS
        assert msg.payload["session_id"] == "abc"
        assert msg.payload["nodes"] == 3

    def test_command_output_factory(self):
        msg = Message.command_output("ls -la", "file1\nfile2", 0)
        assert msg.type == MessageType.COMMAND_OUTPUT
        assert msg.payload["command"] == "ls -la"
        assert msg.payload["return_code"] == 0

    def test_error_factory(self):
        msg = Message.error("Something went wrong")
        assert msg.type == MessageType.ERROR
        assert msg.payload["message"] == "Something went wrong"

    def test_roundtrip_all_types(self):
        messages = [
            Message.token("test"),
            Message.stream_end(),
            Message.risk_prompt("cmd", "yellow", "info"),
            Message.risk_response(False),
            Message.session_status(id="x"),
            Message.command_output("ls", "out", 0),
            Message.error("err"),
        ]
        for msg in messages:
            raw = msg.to_json()
            restored = Message.from_json(raw)
            assert restored.type == msg.type
            assert restored.payload == msg.payload
