"""CLI client — connects to Silicon Valet server over WebSocket."""

from __future__ import annotations

import asyncio
import logging

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


def _run_local_server_and_connect(port: int = 7443) -> None:
    """Start the Silicon Valet server locally and connect to it."""
    import threading
    from silicon_valet.__main__ import startup

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("Starting Silicon Valet...")
    print("  (detecting environment and loading models...)\n")

    # Run server in background thread
    def _server_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(startup())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            loop.close()

    thread = threading.Thread(target=_server_thread, daemon=True)
    thread.start()

    # Wait for server to start
    import time
    for _ in range(60):
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("localhost", port))
            s.close()
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(1)
    else:
        print("Server did not start within 60 seconds. Check logs for errors.")
        return

    # Connect locally
    url = f"ws://localhost:{port}"
    client = ValetClient(url)
    print(f"Connected to local server.\n")

    try:
        asyncio.run(client.connect())
    except KeyboardInterrupt:
        print("\nShutting down...")


def main():
    """CLI entry point: valet [run|connect|setup]"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Silicon Valet — Infrastructure Intelligence",
        epilog="Run 'valet run' to start locally, or 'valet connect <server>' for remote.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # run — start server + connect locally (default)
    run_parser = subparsers.add_parser("run", help="Start Silicon Valet and chat locally")
    run_parser.add_argument("--port", type=int, default=7443, help="Server port (default: 7443)")

    # connect — connect to remote server
    connect_parser = subparsers.add_parser("connect", help="Connect to a remote Silicon Valet server")
    connect_parser.add_argument("server", help="Server address (e.g., 192.168.1.10 or localhost)")
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

    elif args.command == "run":
        _run_local_server_and_connect(args.port)

    else:
        # Default: run locally
        _run_local_server_and_connect()


if __name__ == "__main__":
    main()
