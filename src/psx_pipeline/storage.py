"""Content-addressed Parquet snapshots and immutable ledgers; caches are not state."""

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .contracts import TABLES


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(canonical(value))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".writer.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("state busy; investigate lock owner before recovery") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def append_record(root, kind, key, value):
    # Serialize the transaction with lock(root).
    target = Path(root) / "ledger" / kind / (digest(key) + ".json")
    if target.exists():
        if read_json(target) != value:
            raise ValueError("immutable ledger conflict")
        return False
    write_json(target, value)
    return True


def records(root, kind):
    return [read_json(p) for p in sorted((Path(root) / "ledger" / kind).glob("*.json"))]


def forecast_key(f):
    return "|".join(str(f[k]) for k in ("instrument", "reference_session", "horizon", "policy"))


class Store:
    def __init__(self, root):
        self.root = Path(root)

    def save(self, tables, fixture=False):
        normalized = {}
        for name, rows in tables.items():
            if name not in TABLES:
                raise ValueError("unknown table")
            normalized[name] = [TABLES[name].model_validate(r).model_dump(mode="json") for r in rows]
            if not fixture and any(r.get("fixture", False) for r in normalized[name]):
                raise ValueError("fixture in production dataset")
        snapshot = digest({"tables": normalized, "fixture": fixture})
        dest = self.root / "snapshots" / snapshot
        with lock(self.root):
            if (dest / "manifest.json").exists():
                self.load(snapshot)
                return snapshot
            dest.mkdir(parents=True, exist_ok=True)
            files = {}
            for name, rows in normalized.items():
                groups = {}
                for row in rows:
                    year = str(row.get("session", row.get("reference_period", row.get("date", "metadata"))))[
                        :4
                    ]
                    groups.setdefault(year, []).append(row)
                for year, group in groups.items():
                    rel = f"{name}/year={year}/part.parquet"
                    p = dest / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    pq.write_table(pa.Table.from_pylist(group), p, compression="zstd")
                    files[rel] = digest(p.read_bytes())
            write_json(
                dest / "manifest.json",
                {
                    "schema_version": "1",
                    "snapshot": snapshot,
                    "fixture": fixture,
                    "tables": list(normalized),
                    "files": files,
                },
            )
            write_json(self.root / "dataset.json", {"snapshot": snapshot})
        return snapshot

    def load(self, snapshot=None):
        if snapshot is None:
            snapshot = read_json(self.root / "dataset.json")["snapshot"]
        if not re.fullmatch("[a-f0-9]{64}", snapshot):
            raise ValueError("invalid snapshot")
        base = self.root / "snapshots" / snapshot
        manifest = read_json(base / "manifest.json")
        tables = {name: [] for name in manifest["tables"]}
        for rel, sha in manifest["files"].items():
            path = (base / rel).resolve()
            if not path.is_relative_to(base.resolve()):
                raise ValueError("unsafe snapshot path")
            if digest(path.read_bytes()) != sha:
                raise ValueError("corrupt snapshot")
            table = rel.split("/")[0]
            tables[table].extend(
                TABLES[table].model_validate(r).model_dump(mode="json")
                for r in pq.ParquetFile(path).read().to_pylist()
            )
        return manifest, tables
