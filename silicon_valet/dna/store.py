"""DNAStore — CRUD and graph-like queries over the Infrastructure DNA database."""

from __future__ import annotations

import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from silicon_valet.dna.models import (
    ChangeEntry,
    ConfigFile,
    Dependency,
    NetworkInterface,
    Node,
    Port,
    Service,
)
from silicon_valet.dna.schema import init_schema


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DNAStore:
    """Main interface for reading and writing Infrastructure DNA."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.conn = init_schema(db_path)

    def close(self) -> None:
        self.conn.close()

    # ── Change tracking ──────────────────────────────────────────────

    def _record_change(
        self,
        entity_type: str,
        entity_id: int,
        change_type: str,
        field: str | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO changes_log (entity_type, entity_id, change_type, field, old_value, new_value, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entity_type, entity_id, change_type, field, str(old_value) if old_value is not None else None,
             str(new_value) if new_value is not None else None, _now()),
        )

    # ── Nodes ────────────────────────────────────────────────────────

    def upsert_node(self, node: Node) -> Node:
        existing = self.conn.execute(
            "SELECT * FROM nodes WHERE hostname = ?", (node.hostname,)
        ).fetchone()

        if existing is None:
            cur = self.conn.execute(
                "INSERT INTO nodes (hostname, ip, role, os_version, ram_total_mb, cpu_cores, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (node.hostname, node.ip, node.role, node.os_version,
                 node.ram_total_mb, node.cpu_cores, node.last_seen),
            )
            node.id = cur.lastrowid
            self._record_change("node", node.id, "added")
        else:
            node.id = existing["id"]
            for field_name in ("ip", "role", "os_version", "ram_total_mb", "cpu_cores"):
                old_val = existing[field_name]
                new_val = getattr(node, field_name)
                if new_val is not None and str(old_val) != str(new_val):
                    self._record_change("node", node.id, "modified", field_name, old_val, new_val)
            self.conn.execute(
                "UPDATE nodes SET ip=COALESCE(?,ip), role=COALESCE(?,role), "
                "os_version=COALESCE(?,os_version), ram_total_mb=COALESCE(?,ram_total_mb), "
                "cpu_cores=COALESCE(?,cpu_cores), last_seen=? WHERE id=?",
                (node.ip, node.role, node.os_version, node.ram_total_mb,
                 node.cpu_cores, node.last_seen, node.id),
            )
        self.conn.commit()
        return node

    def get_node(self, hostname: str) -> Node | None:
        row = self.conn.execute(
            "SELECT * FROM nodes WHERE hostname = ?", (hostname,)
        ).fetchone()
        return Node.from_row(row) if row else None

    def get_all_nodes(self) -> list[Node]:
        rows = self.conn.execute("SELECT * FROM nodes ORDER BY hostname").fetchall()
        return [Node.from_row(r) for r in rows]

    # ── Services ─────────────────────────────────────────────────────

    def upsert_service(self, service: Service) -> Service:
        existing = self.conn.execute(
            "SELECT * FROM services WHERE name=? AND type=? AND "
            "COALESCE(node_id,'')=COALESCE(?,'') AND COALESCE(namespace,'')=COALESCE(?,'')",
            (service.name, service.type, service.node_id, service.namespace),
        ).fetchone()

        if existing is None:
            cur = self.conn.execute(
                "INSERT INTO services (name, type, node_id, namespace, status, pid, image, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (service.name, service.type, service.node_id, service.namespace,
                 service.status, service.pid, service.image, service.last_seen),
            )
            service.id = cur.lastrowid
            self._record_change("service", service.id, "added")
        else:
            service.id = existing["id"]
            for field_name in ("status", "pid", "image"):
                old_val = existing[field_name]
                new_val = getattr(service, field_name)
                if new_val is not None and str(old_val) != str(new_val):
                    self._record_change("service", service.id, "modified", field_name, old_val, new_val)
            self.conn.execute(
                "UPDATE services SET status=COALESCE(?,status), pid=COALESCE(?,pid), "
                "image=COALESCE(?,image), last_seen=? WHERE id=?",
                (service.status, service.pid, service.image, service.last_seen, service.id),
            )
        self.conn.commit()
        return service

    def get_services_on_node(self, hostname: str) -> list[Service]:
        rows = self.conn.execute(
            "SELECT s.* FROM services s JOIN nodes n ON s.node_id = n.id "
            "WHERE n.hostname = ? ORDER BY s.name",
            (hostname,),
        ).fetchall()
        return [Service.from_row(r) for r in rows]

    def get_service_by_name(self, name: str) -> Service | None:
        row = self.conn.execute(
            "SELECT * FROM services WHERE name = ? ORDER BY last_seen DESC LIMIT 1",
            (name,),
        ).fetchone()
        return Service.from_row(row) if row else None

    def get_service_by_port(self, port: int) -> Service | None:
        row = self.conn.execute(
            "SELECT s.* FROM services s JOIN ports p ON s.id = p.service_id "
            "WHERE p.port = ? LIMIT 1",
            (port,),
        ).fetchone()
        return Service.from_row(row) if row else None

    def get_all_services(self) -> list[Service]:
        rows = self.conn.execute("SELECT * FROM services ORDER BY name").fetchall()
        return [Service.from_row(r) for r in rows]

    def search_services(self, query: str) -> list[Service]:
        rows = self.conn.execute(
            "SELECT * FROM services WHERE name LIKE ? OR image LIKE ? OR namespace LIKE ? ORDER BY name",
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
        return [Service.from_row(r) for r in rows]

    # ── Ports ────────────────────────────────────────────────────────

    def upsert_port(self, port: Port) -> Port:
        existing = self.conn.execute(
            "SELECT * FROM ports WHERE service_id=? AND port=? AND protocol=?",
            (port.service_id, port.port, port.protocol),
        ).fetchone()

        if existing is None:
            cur = self.conn.execute(
                "INSERT INTO ports (service_id, port, protocol, bind_address, state) "
                "VALUES (?, ?, ?, ?, ?)",
                (port.service_id, port.port, port.protocol, port.bind_address, port.state),
            )
            port.id = cur.lastrowid
            self._record_change("port", port.id, "added")
        else:
            port.id = existing["id"]
            if existing["state"] != port.state:
                self._record_change("port", port.id, "modified", "state", existing["state"], port.state)
            self.conn.execute(
                "UPDATE ports SET bind_address=?, state=? WHERE id=?",
                (port.bind_address, port.state, port.id),
            )
        self.conn.commit()
        return port

    def get_listening_ports(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT p.port, p.protocol, p.bind_address, p.state, "
            "s.name AS service_name, s.type AS service_type, n.hostname "
            "FROM ports p "
            "LEFT JOIN services s ON p.service_id = s.id "
            "LEFT JOIN nodes n ON s.node_id = n.id "
            "ORDER BY p.port"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Config Files ─────────────────────────────────────────────────

    def upsert_config_file(self, cf: ConfigFile) -> ConfigFile:
        existing = self.conn.execute(
            "SELECT * FROM config_files WHERE service_id=? AND path=?",
            (cf.service_id, cf.path),
        ).fetchone()

        if existing is None:
            cur = self.conn.execute(
                "INSERT INTO config_files (service_id, path, hash_sha256, last_modified, last_scanned) "
                "VALUES (?, ?, ?, ?, ?)",
                (cf.service_id, cf.path, cf.hash_sha256, cf.last_modified, cf.last_scanned),
            )
            cf.id = cur.lastrowid
            self._record_change("config_file", cf.id, "added")
        else:
            cf.id = existing["id"]
            if existing["hash_sha256"] != cf.hash_sha256 and cf.hash_sha256 is not None:
                self._record_change(
                    "config_file", cf.id, "modified", "hash_sha256",
                    existing["hash_sha256"], cf.hash_sha256,
                )
            self.conn.execute(
                "UPDATE config_files SET hash_sha256=COALESCE(?,hash_sha256), "
                "last_modified=COALESCE(?,last_modified), last_scanned=? WHERE id=?",
                (cf.hash_sha256, cf.last_modified, cf.last_scanned, cf.id),
            )
        self.conn.commit()
        return cf

    def get_configs_for_service(self, service_id: int) -> list[ConfigFile]:
        rows = self.conn.execute(
            "SELECT * FROM config_files WHERE service_id = ? ORDER BY path",
            (service_id,),
        ).fetchall()
        return [ConfigFile.from_row(r) for r in rows]

    # ── Dependencies ─────────────────────────────────────────────────

    def add_dependency(self, dep: Dependency) -> Dependency:
        existing = self.conn.execute(
            "SELECT * FROM dependencies WHERE source_service_id=? AND target_service_id=? AND dep_type=?",
            (dep.source_service_id, dep.target_service_id, dep.dep_type),
        ).fetchone()

        if existing is None:
            cur = self.conn.execute(
                "INSERT INTO dependencies (source_service_id, target_service_id, dep_type, detail) "
                "VALUES (?, ?, ?, ?)",
                (dep.source_service_id, dep.target_service_id, dep.dep_type, dep.detail),
            )
            dep.id = cur.lastrowid
            self._record_change("dependency", dep.id, "added")
            self.conn.commit()
        else:
            dep.id = existing["id"]
        return dep

    def get_dependencies(self, service_id: int, direction: str = "both") -> list[dict]:
        results = []
        if direction in ("both", "outgoing"):
            rows = self.conn.execute(
                "SELECT d.*, s.name AS target_name FROM dependencies d "
                "JOIN services s ON d.target_service_id = s.id "
                "WHERE d.source_service_id = ?",
                (service_id,),
            ).fetchall()
            results.extend({"direction": "outgoing", **dict(r)} for r in rows)

        if direction in ("both", "incoming"):
            rows = self.conn.execute(
                "SELECT d.*, s.name AS source_name FROM dependencies d "
                "JOIN services s ON d.source_service_id = s.id "
                "WHERE d.target_service_id = ?",
                (service_id,),
            ).fetchall()
            results.extend({"direction": "incoming", **dict(r)} for r in rows)

        return results

    def get_dependents(self, service_id: int) -> list[Service]:
        """BFS traversal: find all services that transitively depend on this service."""
        visited: set[int] = set()
        queue: deque[int] = deque([service_id])
        result: list[Service] = []

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            rows = self.conn.execute(
                "SELECT s.* FROM services s JOIN dependencies d ON s.id = d.source_service_id "
                "WHERE d.target_service_id = ?",
                (current,),
            ).fetchall()
            for row in rows:
                svc = Service.from_row(row)
                if svc.id not in visited:
                    result.append(svc)
                    queue.append(svc.id)

        return result

    # ── Network Interfaces ───────────────────────────────────────────

    def upsert_network_interface(self, iface: NetworkInterface) -> NetworkInterface:
        existing = self.conn.execute(
            "SELECT * FROM network_interfaces WHERE node_id=? AND name=?",
            (iface.node_id, iface.name),
        ).fetchone()

        if existing is None:
            cur = self.conn.execute(
                "INSERT INTO network_interfaces (node_id, name, ip, subnet, mac, state) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (iface.node_id, iface.name, iface.ip, iface.subnet, iface.mac, iface.state),
            )
            iface.id = cur.lastrowid
            self._record_change("network_interface", iface.id, "added")
        else:
            iface.id = existing["id"]
            for field_name in ("ip", "subnet", "mac", "state"):
                old_val = existing[field_name]
                new_val = getattr(iface, field_name)
                if new_val is not None and str(old_val) != str(new_val):
                    self._record_change("network_interface", iface.id, "modified", field_name, old_val, new_val)
            self.conn.execute(
                "UPDATE network_interfaces SET ip=COALESCE(?,ip), subnet=COALESCE(?,subnet), "
                "mac=COALESCE(?,mac), state=COALESCE(?,state) WHERE id=?",
                (iface.ip, iface.subnet, iface.mac, iface.state, iface.id),
            )
        self.conn.commit()
        return iface

    # ── Changes Log ──────────────────────────────────────────────────

    def get_changes_since(self, hours: int = 24) -> list[ChangeEntry]:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self.conn.execute(
            "SELECT * FROM changes_log WHERE timestamp >= ? ORDER BY timestamp DESC",
            (cutoff,),
        ).fetchall()
        return [ChangeEntry.from_row(r) for r in rows]

    # ── Mark removed ─────────────────────────────────────────────────

    def mark_services_removed(self, active_ids: set[int]) -> None:
        """Mark services not in active_ids as removed (log change, delete row)."""
        rows = self.conn.execute("SELECT id, name FROM services").fetchall()
        for row in rows:
            if row["id"] not in active_ids:
                self._record_change("service", row["id"], "removed")
                self.conn.execute("DELETE FROM services WHERE id=?", (row["id"],))
        self.conn.commit()

    # ── Context Summary ──────────────────────────────────────────────

    def get_context_summary(self) -> str:
        """Build a plain English summary of the current environment for agent injection."""
        nodes = self.get_all_nodes()
        services = self.get_all_services()
        ports = self.get_listening_ports()
        changes = self.get_changes_since(hours=24)

        lines = ["## Current Environment"]

        if nodes:
            lines.append(f"\n**Cluster:** {len(nodes)} node(s)")
            for n in nodes:
                ram = f"{n.ram_total_mb}MB RAM" if n.ram_total_mb else "unknown RAM"
                lines.append(f"  - {n.hostname} ({n.role or 'unknown role'}, {n.ip or 'no IP'}, {ram})")

        if services:
            running = [s for s in services if s.status == "running"]
            lines.append(f"\n**Services:** {len(services)} total, {len(running)} running")
            for s in services[:20]:  # Cap at 20 for context window
                lines.append(f"  - {s.name} [{s.type}] — {s.status or 'unknown'}")
            if len(services) > 20:
                lines.append(f"  ... and {len(services) - 20} more")

        if ports:
            lines.append(f"\n**Listening ports:** {len(ports)}")
            for p in ports[:15]:
                svc_name = p.get("service_name", "unknown")
                lines.append(f"  - :{p['port']}/{p['protocol']} — {svc_name}")
            if len(ports) > 15:
                lines.append(f"  ... and {len(ports) - 15} more")

        if changes:
            lines.append(f"\n**Recent changes (24h):** {len(changes)}")
            for c in changes[:5]:
                lines.append(f"  - {c.change_type} {c.entity_type} #{c.entity_id}")
                if c.field:
                    lines.append(f"    {c.field}: {c.old_value} → {c.new_value}")

        return "\n".join(lines)
