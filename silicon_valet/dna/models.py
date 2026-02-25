"""Dataclass models for Infrastructure DNA entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Node:
    hostname: str
    ip: str | None = None
    role: str | None = None
    os_version: str | None = None
    ram_total_mb: int | None = None
    cpu_cores: int | None = None
    last_seen: str = field(default_factory=_now)
    id: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_row(cls, row: dict) -> Node:
        return cls(**{k: row[k] for k in row.keys() if k in cls.__dataclass_fields__})


@dataclass
class Service:
    name: str
    type: str  # 'systemd', 'k8s_pod', 'k8s_deploy', 'k8s_svc', 'container'
    node_id: int | None = None
    namespace: str | None = None
    status: str | None = None
    pid: int | None = None
    image: str | None = None
    last_seen: str = field(default_factory=_now)
    id: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_row(cls, row: dict) -> Service:
        return cls(**{k: row[k] for k in row.keys() if k in cls.__dataclass_fields__})


@dataclass
class Port:
    port: int
    service_id: int | None = None
    protocol: str = "tcp"
    bind_address: str = "0.0.0.0"
    state: str = "LISTEN"
    id: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_row(cls, row: dict) -> Port:
        return cls(**{k: row[k] for k in row.keys() if k in cls.__dataclass_fields__})


@dataclass
class ConfigFile:
    path: str
    service_id: int | None = None
    hash_sha256: str | None = None
    last_modified: str | None = None
    last_scanned: str = field(default_factory=_now)
    id: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_row(cls, row: dict) -> ConfigFile:
        return cls(**{k: row[k] for k in row.keys() if k in cls.__dataclass_fields__})


@dataclass
class Dependency:
    source_service_id: int
    target_service_id: int
    dep_type: str  # 'network', 'volume', 'config', 'env'
    detail: str | None = None
    id: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_row(cls, row: dict) -> Dependency:
        return cls(**{k: row[k] for k in row.keys() if k in cls.__dataclass_fields__})


@dataclass
class NetworkInterface:
    node_id: int
    name: str
    ip: str | None = None
    subnet: str | None = None
    mac: str | None = None
    state: str = "UP"
    id: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_row(cls, row: dict) -> NetworkInterface:
        return cls(**{k: row[k] for k in row.keys() if k in cls.__dataclass_fields__})


@dataclass
class ChangeEntry:
    entity_type: str
    entity_id: int
    change_type: str  # 'added', 'modified', 'removed'
    timestamp: str = field(default_factory=_now)
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    id: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_row(cls, row: dict) -> ChangeEntry:
        return cls(**{k: row[k] for k in row.keys() if k in cls.__dataclass_fields__})
