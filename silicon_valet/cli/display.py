"""Rich terminal display — renders Silicon Valet output in the terminal."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

VALET_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "danger": "bold red",
    "success": "bold green",
    "tier.green": "green",
    "tier.yellow": "yellow",
    "tier.red": "bold red",
    "command": "bold white on grey23",
})


class ValetDisplay:
    """Renders Silicon Valet output using Rich."""

    def __init__(self):
        self.console = Console(theme=VALET_THEME)
        self._stream_buffer = ""

    def show_startup(self, status: dict) -> None:
        """Show session startup information."""
        self.console.print()
        self.console.print(
            Panel(
                f"[bold cyan]Silicon Valet[/bold cyan] v0.1.0\n"
                f"Session: {status.get('session_id', 'unknown')}\n"
                f"Nodes: {status.get('nodes_count', '?')} | "
                f"Services: {status.get('services_count', '?')}",
                title="Connected",
                border_style="cyan",
            )
        )
        dna = status.get("dna_summary", "")
        if dna:
            self.console.print(f"\n[dim]{dna}[/dim]\n")

    def stream_token(self, token: str) -> None:
        """Append a token to the live display."""
        self._stream_buffer += token
        sys.stdout.write(token)
        sys.stdout.flush()

    def end_stream(self) -> None:
        """Finalize the streamed response."""
        if self._stream_buffer:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._stream_buffer = ""

    def show_risk_prompt(self, action: dict) -> bool:
        """Display a risk confirmation prompt and get user response."""
        tier = action.get("tier", "yellow").upper()
        command = action.get("command", "unknown")
        explanation = action.get("explanation", "")

        style = f"tier.{tier.lower()}" if tier.lower() in ("green", "yellow", "red") else "warning"

        self.console.print()
        self.console.print(
            Panel(
                f"[bold]Command:[/bold] [command]{command}[/command]\n"
                f"[bold]Risk:[/bold] [{style}]{tier}[/{style}]\n"
                f"[bold]Explanation:[/bold] {explanation}",
                title=f"[{style}]Confirmation Required[/{style}]",
                border_style=style,
            )
        )

        if tier == "RED":
            self.console.print(f"[danger]Type the command name to confirm:[/danger] ", end="")
            response = input().strip()
            return response == command.split()[0]
        else:
            self.console.print("[yellow]Approve? (y/n):[/yellow] ", end="")
            response = input().strip().lower()
            return response in ("y", "yes")

    def show_command_output(self, output: dict) -> None:
        """Display command execution output."""
        command = output.get("command", "")
        stdout = output.get("output", "")
        rc = output.get("return_code", -1)

        style = "success" if rc == 0 else "danger"
        self.console.print(
            Panel(
                stdout[:2000] if stdout else "[dim]No output[/dim]",
                title=f"[{style}]{command}[/{style}] (rc={rc})",
                border_style="dim",
            )
        )

    def show_plan(self, steps: list[str]) -> None:
        """Display an execution plan."""
        table = Table(title="Execution Plan", show_lines=True)
        table.add_column("#", width=3)
        table.add_column("Step")
        for i, step in enumerate(steps, 1):
            table.add_row(str(i), step)
        self.console.print(table)

    def show_error(self, error: str) -> None:
        """Display an error message."""
        self.console.print(f"[danger]Error:[/danger] {error}")

    def prompt(self) -> str:
        """Show the input prompt and return user input."""
        try:
            return self.console.input("[bold cyan]valet>[/bold cyan] ")
        except (EOFError, KeyboardInterrupt):
            return "/quit"
