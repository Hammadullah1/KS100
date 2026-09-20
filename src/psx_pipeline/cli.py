"""Local and Actions use exactly the same commands. Exit 2=invalid, 3=blocked."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from .adapters import ADAPTERS, ManualAdapter, SourceBlocked, registry
from .contracts import TABLES, utcnow
from .data import build_feature, stamp, validate_dataset
from .drivers import ablation_compare, driver_features, news_features
from .fixtures import make_fixture
from .forward import score_forward
from .operations import backup, reserve_budget, restore, rollback_model
from .pipeline import authorize_dataset, daily, issue, mature, results_bundle
from .publishing import empty_bundle, publish, rollback, verify_bundle
from .research import dataset, promote, protocol, run_research
from .storage import Store, digest, read_json, write_json


def parser():
    p = argparse.ArgumentParser(prog="psx", description="PSX research. No fixture fallback in production.")
    p.add_argument("--state", default="state/local")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("source-audit")
    s = sub.add_parser(
        "snapshot-research", help="Local retrospective CSV experiment; never production evidence"
    )
    s.add_argument("--csv", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--config", default="config/snapshot_research.yaml")
    s.add_argument("--brent-csv", help="Optional FRED Brent snapshot; uses an explicitly assumed 7-day delay")
    f = sub.add_parser("fixture")
    f.add_argument("--sessions", type=int, default=1250)
    b = sub.add_parser("backfill")
    b.add_argument("--source", required=True)
    b.add_argument("--table", choices=TABLES, default="bars")
    b.add_argument("--file")
    b.add_argument("--start", type=date.fromisoformat)
    b.add_argument("--end", type=date.fromisoformat)
    sub.add_parser("validate")
    f = sub.add_parser("features")
    f.add_argument("--session", required=True)
    f.add_argument("--cutoff", required=True, type=stamp)
    for command in ["baseline", "train", "evaluate"]:
        r = sub.add_parser(command)
        r.add_argument("--horizon", type=int, choices=[1, 5], required=True)
        r.add_argument("--cutoff", type=stamp, required=True)
        r.add_argument("--output", required=True)
        r.add_argument("--scope", choices=["index", "company"], default="index")
        r.add_argument("--instrument")
        r.add_argument("--final", action="store_true")
    p1 = sub.add_parser("promote")
    p1.add_argument("--candidate", required=True)
    p1.add_argument("--expected-sha256", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--cutoff", type=stamp)
    d.add_argument("--recovery", action="store_true")
    f = sub.add_parser("forecast")
    f.add_argument("--session", required=True)
    f.add_argument("--cutoff", type=stamp, required=True)
    for name in ["outcomes", "forward"]:
        o = sub.add_parser(name)
        o.add_argument("--cutoff", type=stamp, required=True)
    a = sub.add_parser("ablate")
    a.add_argument("--cutoff", type=stamp, required=True)
    a.add_argument("--horizon", type=int, choices=[1, 5], required=True)
    a.add_argument("--output", required=True)
    b = sub.add_parser("bundle")
    b.add_argument("--output", default="web/public/data")
    b.add_argument("--empty", action="store_true")
    v = sub.add_parser("verify-bundle")
    v.add_argument("--output", default="web/public/data")
    r = sub.add_parser("rollback-bundle")
    r.add_argument("--output", required=True)
    r.add_argument("--bundle-id", required=True)
    r = sub.add_parser("rollback-model")
    r.add_argument("--horizon", type=int, choices=[1, 5], required=True)
    r.add_argument("--instrument", default="PSX:KSE100:TR")
    r.add_argument("--scope", choices=["index", "company"], default="index")
    b = sub.add_parser("budget")
    b.add_argument("--job-id", required=True)
    b.add_argument("--kind", choices=["daily", "research"], required=True)
    b = sub.add_parser("backup")
    b.add_argument("--output", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--archive", required=True)
    return p


def execute(a):
    root = Path(a.state)
    command = a.command
    if command == "snapshot-research":
        from .snapshot_research import run_snapshot

        return run_snapshot(a.csv, a.output, a.config, a.brent_csv)
    if command == "source-audit":
        return {
            "status": "blocked",
            "reviewed_at": "2026-09-18",
            "sources": {
                k: {"enabled": v["enabled"], "permissions": v["permissions"], "blocker": v["blocker"]}
                for k, v in registry().items()
            },
            "reason": "Free permitted PSX historical data and public forecast rights are not verified.",
        }
    if command == "fixture":
        if not 50 <= a.sessions <= 3000:
            raise ValueError("fixture sessions must be 50..3000")
        if (root / "dataset.json").exists() and not Store(root).load()[0]["fixture"]:
            raise ValueError("refusing to replace real state with fixtures")
        tables = make_fixture(a.sessions)
        quality = validate_dataset(tables)
        snapshot = Store(root).save(tables, fixture=True)
        write_json(root / "quality.json", quality)
        return {"status": "completed", "mode": "fixture", "snapshot": snapshot, "quality": quality}
    if command == "backfill":
        tables = (
            Store(root).load()[1]
            if (root / "dataset.json").exists()
            else {
                k: []
                for k in [
                    "instruments",
                    "sessions",
                    "bars",
                    "actions",
                    "membership",
                    "macro",
                    "flows",
                    "events",
                ]
            }
        )
        if a.file:
            incoming = ManualAdapter(a.source, a.table).read(a.file)
        else:
            if a.source not in ADAPTERS or not a.start or not a.end:
                raise ValueError("live import requires source, start and end")
            incoming = ADAPTERS[a.source].fetch(a.start, a.end)
        combined = tables.get(a.table, []) + incoming
        tables[a.table] = list({digest(r): r for r in combined}.values())
        if tables.get("bars"):
            validate_dataset(tables)
        return {"status": "completed", "snapshot": Store(root).save(tables), "imported": len(incoming)}
    if command == "daily":
        return daily(root, a.cutoff, a.recovery)
    if command == "bundle":
        bundle, sources = (empty_bundle(utcnow()), []) if a.empty else results_bundle(root, utcnow())
        bundle_id = publish(a.output, bundle, sources)
        write_json(root / "publication.json", {"bundle_id": bundle_id, "completed_at": utcnow().isoformat()})
        return {
            "status": bundle.status,
            "bundle_id": bundle_id,
            "reason": bundle.reason,
        }
    if command == "verify-bundle":
        identifier = read_json(Path(a.output) / "latest.json")["bundle_id"]
        verify_bundle(a.output, identifier)
        return {"status": "completed", "bundle_id": identifier}
    if command == "rollback-bundle":
        rollback(a.output, a.bundle_id)
        return {"status": "completed"}
    if command == "rollback-model":
        return {"status": "completed", "version": rollback_model(root, a.horizon, a.instrument, a.scope)}
    if command == "budget":
        return reserve_budget(root, a.job_id, a.kind)
    if command == "backup":
        return backup(root, a.output)
    if command == "restore":
        return restore(a.archive, root)
    manifest, tables = Store(root).load()
    if command == "validate":
        report = validate_dataset(tables)
        write_json(root / "quality.json", report)
        return report
    if not manifest["fixture"]:
        authorize_dataset(tables, ["private_storage", "training"])
    if command == "features":
        rows = [
            build_feature(
                tables, i["id"], a.session, a.cutoff, manifest["snapshot"], manifest["fixture"]
            ).model_dump(mode="json")
            for i in tables["instruments"]
        ]
        write_json(root / "features.json", rows)
        return {"rows": len(rows), "eligible": sum(r["eligible"] for r in rows)}
    if command in ["baseline", "train", "evaluate"]:
        if a.instrument:
            tables = {**tables, "instruments": [i for i in tables["instruments"] if i["id"] == a.instrument]}
        frame, exclusions = dataset(
            tables, manifest["snapshot"], a.horizon, a.cutoff, a.scope, manifest["fixture"]
        )
        basis = "adjusted_price" if a.scope == "company" else tables["instruments"][0]["return_basis"]
        report, candidate = run_research(
            frame,
            protocol(),
            a.horizon,
            manifest["snapshot"],
            manifest["fixture"],
            a.output,
            a.final,
            target_basis=basis,
        )
        write_json(Path(a.output) / "exclusions.json", exclusions)
        return {
            "status": "completed",
            "mode": report["mode"],
            "version": candidate["version"],
            "runtime_seconds": report["runtime_seconds"],
            "folds": len(report["folds"]),
            "report": str(Path(a.output) / ("final-test.json" if a.final else "historical.json")),
            "claim": report["claim"],
            "exclusions": exclusions,
        }
    if command == "promote":
        candidate = read_json(a.candidate)
        if digest(candidate) != a.expected_sha256:
            raise ValueError("candidate checksum mismatch")
        if candidate["snapshot"] != manifest["snapshot"]:
            raise ValueError("candidate snapshot differs from reviewed dataset")
        return promote(root, a.candidate, utcnow(), protocol())
    if command == "forecast":
        if manifest["fixture"]:
            raise ValueError("forecast command refuses fixtures; fixture tests explicitly simulate issuance")
        return {"status": "completed", "forecasts": len(issue(root, tables, manifest, a.session, a.cutoff))}
    if command == "forward":
        report = score_forward(root, a.cutoff)
        write_json(root / "forward.json", report)
        return report
    if command == "ablate":
        return run_ablation(tables, manifest, a.horizon, a.cutoff, a.output)
    if command == "outcomes":
        return {"status": "completed", "appended": mature(root, tables, a.cutoff)}
    raise ValueError("unimplemented command")


def run_ablation(tables, manifest, horizon, cutoff, output):
    import yaml

    frame, exclusions = dataset(tables, manifest["snapshot"], horizon, cutoff, fixture=manifest["fixture"])
    config = yaml.safe_load(Path("config/features.yaml").read_text())
    groups = {k: v for k, v in config["groups"].items() if k != "price"}
    columns = {}
    for index, row in frame.iterrows():
        additions = driver_features(tables.get("macro", []), stamp(row.cutoff), groups)
        if groups.get("news", {}).get("enabled"):
            additions.update(news_features(tables.get("events", []), stamp(row.cutoff), row.instrument))
        for name, value in additions.items():
            frame.loc[index, name] = value
    for group in groups:
        columns[group] = [c for c in frame.columns if c.startswith(group + "_")]

    def runner(data, features, name):
        return run_research(
            data,
            protocol(),
            horizon,
            manifest["snapshot"],
            manifest["fixture"],
            Path(output) / name,
            columns=features,
        )[0]

    results = ablation_compare(frame, columns, runner)
    report = {
        "mode": "fixture" if manifest["fixture"] else "research",
        "groups": results,
        "neural": {
            "status": "deferred",
            "reason": "Permitted timestamped news and cheap-feature advantage are not established.",
        },
        "exclusions": exclusions,
    }
    write_json(Path(output) / "ablations.json", report)
    return {"status": "completed", "report": str(Path(output) / "ablations.json"), **report}


def main():
    args = parser().parse_args()
    try:
        result = execute(args)
        print(json.dumps(result, allow_nan=False, default=str))
        # Publishing an honest blocked bundle is a successful packaging operation.
        if result.get("status") == "blocked" and args.command not in {"bundle", "source-audit"}:
            return 3
        return 0
    except (SourceBlocked, FileNotFoundError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 3
    except ValidationError as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "schema validation failed",
                    "fields": [{"location": e["loc"], "type": e["type"]} for e in exc.errors()],
                }
            )
        )
        return 2
    except (ValueError, KeyError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
