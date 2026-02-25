"""SQLite schema definition for Infrastructure DNA."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hostname    TEXT NOT NULL UNIQUE,
    ip          TEXT,
    role        TEXT,  -- 'control-plane', 'worker', etc.
    os_version  TEXT,
    ram_total_mb INTEGER,
    cpu_cores   INTEGER,
    last_seen   TEXT NOT NULL  -- ISO 8601
);

CREATE TABLE IF NOT EXISTS services (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,  -- 'systemd', 'k8s_pod', 'k8s_deploy', 'k8s_svc', 'container'
    node_id     INTEGER REFERENCES nodes(id),
    namespace   TEXT,  -- k8s namespace or NULL for systemd
    status      TEXT,  -- 'running', 'stopped', 'failed', 'pending', etc.
    pid         INTEGER,
    image       TEXT,  -- container image if applicable
    last_seen   TEXT NOT NULL,
    UNIQUE(name, type, node_id, namespace)
);

CREATE TABLE IF NOT EXISTS ports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id    INTEGER REFERENCES services(id) ON DELETE CASCADE,
    port          INTEGER NOT NULL,
    protocol      TEXT NOT NULL DEFAULT 'tcp',  -- 'tcp' or 'udp'
    bind_address  TEXT DEFAULT '0.0.0.0',
    state         TEXT DEFAULT 'LISTEN',
    UNIQUE(service_id, port, protocol)
);

CREATE TABLE IF NOT EXISTS config_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id    INTEGER REFERENCES services(id) ON DELETE CASCADE,
    path          TEXT NOT NULL,
    hash_sha256   TEXT,
    last_modified TEXT,
    last_scanned  TEXT NOT NULL,
    UNIQUE(service_id, path)
);

CREATE TABLE IF NOT EXISTS dependencies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_service_id   INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    target_service_id   INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    dep_type            TEXT NOT NULL,  -- 'network', 'volume', 'config', 'env'
    detail              TEXT,  -- e.g., 'connects on port 5432', 'mounts /shared/data'
    UNIQUE(source_service_id, target_service_id, dep_type)
);

CREATE TABLE IF NOT EXISTS network_interfaces (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    name    TEXT NOT NULL,
    ip      TEXT,
    subnet  TEXT,
    mac     TEXT,
    state   TEXT DEFAULT 'UP',
    UNIQUE(node_id, name)
);

CREATE TABLE IF NOT EXISTS changes_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- 'node', 'service', 'port', 'config_file', 'dependency', 'network_interface'
    entity_id   INTEGER NOT NULL,
    change_type TEXT NOT NULL,  -- 'added', 'modified', 'removed'
    field       TEXT,  -- which field changed (NULL for added/removed)
    old_value   TEXT,
    new_value   TEXT,
    timestamp   TEXT NOT NULL  -- ISO 8601
);

CREATE INDEX IF NOT EXISTS idx_services_node ON services(node_id);
CREATE INDEX IF NOT EXISTS idx_services_name ON services(name);
CREATE INDEX IF NOT EXISTS idx_ports_service ON ports(service_id);
CREATE INDEX IF NOT EXISTS idx_ports_number ON ports(port);
CREATE INDEX IF NOT EXISTS idx_config_files_service ON config_files(service_id);
CREATE INDEX IF NOT EXISTS idx_deps_source ON dependencies(source_service_id);
CREATE INDEX IF NOT EXISTS idx_deps_target ON dependencies(target_service_id);
CREATE INDEX IF NOT EXISTS idx_changes_timestamp ON changes_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_changes_entity ON changes_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_network_interfaces_node ON network_interfaces(node_id);
"""


def init_schema(db_path: Path | str) -> sqlite3.Connection:
    """Initialize the DNA database schema. Returns an open connection."""
    db_path = str(db_path)
    is_memory = db_path == ":memory:"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript(DDL)

    # Track schema version
    cur = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = cur.fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()

    return conn
