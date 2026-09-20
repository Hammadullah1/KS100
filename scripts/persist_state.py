"""Commit approved normalized private state; reject fixture state and obvious secret files."""

import subprocess
from pathlib import Path

from psx_pipeline.storage import Store

root = Path("state/private").resolve()
if (root / "dataset.json").exists():
    manifest, tables = Store(root).load()
    if manifest["fixture"]:
        raise ValueError("fixture state cannot be persisted as production")
files = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts]
if sum(p.stat().st_size for p in files) > 100_000_000:
    raise ValueError("private state size cap; manual archival required")
for p in files:
    if p.name.startswith(".env") or p.suffix.lower() in {".pem", ".key", ".pfx", ".pdf", ".html"}:
        raise ValueError("prohibited private-state artifact")


def git(*args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


git("config", "user.name", "github-actions[bot]")
git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
git("add", "--all")
if git("diff", "--cached", "--name-only").stdout.strip():
    git("commit", "-m", "Persist audited pipeline state")
    git("push")
    print("Private state commit pushed.")
else:
    print("Private state unchanged.")
