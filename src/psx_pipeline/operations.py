import zipfile
from pathlib import Path

from .contracts import utcnow
from .publishing import verify_bundle
from .storage import Store, append_record, digest, lock, read_json, records, write_json


def reserve_budget(root, job_id, kind, cap=1500):
    reserve = 45 if kind == "research" else 30
    month = utcnow().strftime("%Y-%m")
    with lock(root):
        previous = records(root, "budget")
        existing = next((r for r in previous if r["job_id"] == job_id), None)
        if existing:
            return existing
        used = sum(r["reserved_minutes"] for r in previous if r["month"] == month)
        if used + reserve > cap:
            raise ValueError("monthly conservative CPU reservation cap reached")
        row = {"job_id": job_id, "month": month, "kind": kind, "reserved_minutes": reserve}
        append_record(root, "budget", job_id, row)
    return row


def backup(root, target):
    root = Path(root).resolve()
    target = Path(target).resolve()
    if target.is_relative_to(root):
        raise ValueError("backup must be outside state directory")
    paths = [p for p in root.rglob("*") if p.is_file() and p.name != ".writer.lock"]
    if sum(p.stat().st_size for p in paths) > 100_000_000:
        raise ValueError("state growth cap reached")
    target.parent.mkdir(parents=True, exist_ok=True)
    with lock(root), zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for p in paths:
            if p.is_symlink():
                raise ValueError("symlink in state")
            archive.write(p, p.relative_to(root).as_posix())
    return {"file": str(target), "sha256": digest(target.read_bytes()), "files": len(paths)}


def restore(archive, destination):
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("restore requires empty directory")
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > 100_000_000:
            raise ValueError("restore size cap")
        for item in z.infolist():
            path = (destination / item.filename).resolve()
            if not path.is_relative_to(destination) or ":" in item.filename:
                raise ValueError("unsafe archive path")
        z.extractall(destination)
    if (destination / "dataset.json").exists():
        Store(destination).load()
    if (destination / "public" / "latest.json").exists():
        verify_bundle(destination / "public", read_json(destination / "public" / "latest.json")["bundle_id"])
    return {"restored": str(destination), "verified": True}


def rollback_model(root, horizon, instrument="PSX:KSE100:TR", scope="index"):
    root = Path(root)
    with lock(root):
        suffix = digest(instrument)[:12] if scope == "index" else "pooled"
        slot = f"{scope}-{suffix}-h{horizon}"
        old = root / f"previous-{slot}.json"
        if not old.exists():
            raise ValueError("no preceding active model")
        candidate = read_json(old)
        if not any(
            r["version"] == candidate["version"] and r["artifact_hash"] == digest(candidate)
            for r in records(root, "promotions")
        ):
            raise ValueError("rollback model provenance mismatch")
        write_json(root / f"active-{slot}.json", candidate)
        append_record(
            root,
            "rollbacks",
            utcnow().isoformat(),
            {"version": candidate["version"], "at": utcnow().isoformat()},
        )
    return candidate["version"]
