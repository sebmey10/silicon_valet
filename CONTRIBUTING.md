# Contributing to Silicon Valet

## Development Setup

```bash
git clone https://github.com/your-org/silicon-valet.git
cd silicon-valet
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Writing a Domain Pack

Domain packs extend Silicon Valet with service-specific knowledge. Each pack lives in `silicon_valet/packs/<name>/`.

### 1. Create the pack directory

```
silicon_valet/packs/myservice/
└── __init__.py
```

### 2. Implement the Pack class

```python
from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack

class Pack(BasePack):
    name = "myservice"
    version = "1.0"
    description = "MyService monitoring and management"

    def detect(self, dna: DNAStore) -> bool:
        """Return True if this pack is relevant to the environment."""
        return len(dna.search_services("myservice")) > 0

    def get_tools(self) -> list[type]:
        """Return any custom tool classes."""
        return []

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        """Return seed runbooks for common problems."""
        return [
            RunbookEntry(
                title="MyService not responding",
                problem_pattern="MyService health check fails",
                symptoms=["Port not listening", "Connection refused"],
                steps=[
                    {"action": "check", "command": "systemctl status myservice",
                     "explanation": "Check service status", "risk_tier": "green"},
                ],
                root_cause="Service crashed or misconfigured",
                verification="curl localhost:8080/health returns 200",
                tags=["myservice"],
                pack_source="myservice",
            ),
        ]
```

### 3. Register the pack

Add the module path to `PACK_MODULES` in `silicon_valet/packs/loader.py`:

```python
PACK_MODULES = [
    ...
    "silicon_valet.packs.myservice",
]
```

## Adding Tools

Tools use the Qwen-Agent `@register_tool` pattern. All tools that execute commands must route through the risk engine.

```python
from qwen_agent.tools.base import BaseTool, register_tool

@register_tool("my_tool")
class MyTool(BaseTool):
    description = "What the tool does."
    parameters = [
        {"name": "param", "type": "string", "description": "...", "required": True},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params, **kwargs):
        # Parse params, build command, route through risk engine
        ...
```

## Adding Risk Patterns

Edit `silicon_valet/risk/patterns.py` to add new command classifications. Commands are matched by regex. Unrecognized commands default to YELLOW.

## Running Tests

```bash
pytest tests/ -v           # All tests
pytest tests/ -v -k "dna"  # DNA tests only
```

## Commit Convention

- `feat:` New feature
- `fix:` Bug fix
- `refactor:` Code restructuring
- `test:` Test additions
- `docs:` Documentation
- `deploy:` Deployment changes
