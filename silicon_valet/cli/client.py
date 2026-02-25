"""CLI client — connects to Silicon Valet server over WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import websockets

from silicon_valet.cli.display import ValetDisplay
from silicon_valet.server.protocol import Message, MessageType

logger = logging.getLogger(__name__)


class ValetClient:
    """Lightweight WebSocket client for Silicon Valet."""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.display = ValetDisplay()
        self._ws = None
        self._running = False

    async def connect(self) -> None:
        """Connect to the server and start the session."""
        self._running = True
        try:
            async with websockets.connect(
                self.server_url,
                ping_interval=30,
                ping_timeout=10,
            ) as ws:
                self._ws = ws
                # Start receive loop and input loop concurrently
                recv_task = asyncio.create_task(self._receive_loop(ws))
                input_task = asyncio.create_task(self._input_loop(ws))
                done, pending = await asyncio.wait(
                    [recv_task, input_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
        except websockets.ConnectionClosed:
            self.display.show_error("Connection closed by server")
        except ConnectionRefusedError:
            self.display.show_error(f"Could not connect to {self.server_url}")
        except Exception as e:
            self.display.show_error(f"Connection error: {e}")
        finally:
            self._running = False

    async def _receive_loop(self, ws) -> None:
        """Process incoming messages from the server."""
        try:
            async for raw in ws:
                msg = Message.from_json(raw)
                await self._handle_message(msg, ws)
        except websockets.ConnectionClosed:
            self._running = False

    async def _handle_message(self, msg: Message, ws) -> None:
        """Dispatch an incoming message to the appropriate display handler."""
        if msg.type == MessageType.SESSION_STATUS:
            self.display.show_startup(msg.payload)

        elif msg.type == MessageType.TOKEN_STREAM:
            self.display.stream_token(msg.payload.get("text", ""))

        elif msg.type == MessageType.STREAM_END:
            self.display.end_stream()

        elif msg.type == MessageType.RISK_PROMPT:
            approved = self.display.show_risk_prompt(msg.payload)
            response = Message.risk_response(approved)
            await ws.send(response.to_json())

        elif msg.type == MessageType.COMMAND_OUTPUT:
            self.display.show_command_output(msg.payload)

        elif msg.type == MessageType.ERROR:
            self.display.show_error(msg.payload.get("message", "Unknown error"))

    async def _input_loop(self, ws) -> None:
        """Read user input and send to server."""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                text = await loop.run_in_executor(None, self.display.prompt)
                text = text.strip()
                if not text:
                    continue
                if text == "/quit":
                    self._running = False
                    break
                msg = Message(type=MessageType.USER_INPUT, payload={"text": text})
                await ws.send(msg.to_json())
            except (EOFError, KeyboardInterrupt):
                self._running = False
                break

    async def send(self, text: str) -> None:
        """Send a message to the server."""
        if self._ws:
            msg = Message(type=MessageType.USER_INPUT, payload={"text": text})
            await self._ws.send(msg.to_json())


def main():
    """CLI entry point: valet connect <server>"""
    import argparse

    parser = argparse.ArgumentParser(description="Silicon Valet CLI")
    subparsers = parser.add_subparsers(dest="command")

    connect_parser = subparsers.add_parser("connect", help="Connect to a Silicon Valet server")
    connect_parser.add_argument("server", help="Server address (e.g., 192.168.1.10)")
    connect_parser.add_argument("--port", type=int, default=7443, help="Server port (default: 7443)")

    args = parser.parse_args()

    if args.command == "connect":
        url = f"ws://{args.server}:{args.port}"
        client = ValetClient(url)

        logging.basicConfig(level=logging.WARNING)
        print(f"Connecting to {url}...")

        try:
            asyncio.run(client.connect())
        except KeyboardInterrupt:
            print("\nDisconnected.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
