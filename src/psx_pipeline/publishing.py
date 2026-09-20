"""Atomic, content-addressed public bundles. The latest pointer moves last."""

import re
from pathlib import Path

from .adapters import registry, require
from .contracts import Bundle, Forecast
from .storage import canonical, digest, lock, read_json, write_json


def empty_bundle(now, reason="No permitted PSX dataset or trained model is available."):
    sources = [
        {
            "id": k,
            "name": r["identity"],
            "status": "disabled" if not r["enabled"] else "requires_live_check",
            "reason": r["blocker"],
            "url": r["documentation_url"],
            "reviewed_at": r["reviewed_at"],
        }
        for k, r in registry().items()
    ]
    return Bundle(
        mode="production",
        generated_at=now,
        status="blocked",
        reason=reason,
        update_due_at=None,
        calendar_coverage_until=None,
        source_session_coverage=None,
        model_versions=[],
        forecasts=[],
        metrics=[],
        history=[],
        outcomes=[],
        drivers=[],
        sources=sources,
        stages={"fetch": None, "validation": None, "prediction": None, "publication": None},
        attribution=[],
    )


def public_safety(bundle, sources, registry_path="config/sources.yaml"):
    bundle = Bundle.model_validate(bundle)
    if bundle.mode != "production":
        raise ValueError("fixture bundle cannot be published")
    if (
        bundle.forecasts
        or bundle.history
        or bundle.metrics
        or bundle.drivers
        or bundle.outcomes
        or bundle.drivers
    ):
        if not sources:
            raise ValueError("provenance source list required")
        for source in sources:
            require(source, ["public_derived"], registry_path=registry_path)
        for f in bundle.forecasts + bundle.history:
            Forecast.model_validate(f)
            if f.fixture or f.instrument.startswith("TEST:"):
                raise ValueError("fixture forecast in production")
            if f.model_version not in bundle.model_versions:
                raise ValueError("inconsistent model version")
        if (
            any(f.reference_close is not None for f in bundle.forecasts + bundle.history)
            or bundle.outcomes
            or bundle.drivers
        ):
            for source in sources:
                require(source, ["public_raw"], registry_path=registry_path)
    if bundle.status == "ready" and not bundle.forecasts:
        raise ValueError("ready bundle contains no forecasts")
    # Nested free-form metrics are constrained to the project's scorecard vocabulary.
    forbidden = {
        "api_key",
        "access_token",
        "password",
        "secret",
        "payload",
        "raw_text",
        "model_text",
        "coef",
        "intercept",
    }

    def check(obj):
        if isinstance(obj, dict):
            if obj.get("fixture") is True or obj.get("mode") == "fixture":
                raise ValueError("fixture metadata in public bundle")
            if forbidden.intersection(k.lower() for k in obj):
                raise ValueError("private field in public bundle")
            for v in obj.values():
                check(v)
        elif isinstance(obj, list):
            for v in obj:
                check(v)

    check(bundle.model_dump(mode="json"))
    return bundle


def verify_bundle(root, bundle_id):
    if not re.fullmatch("[a-f0-9]{64}", bundle_id):
        raise ValueError("unsafe bundle id")
    base = Path(root) / "bundles" / bundle_id
    manifest = read_json(base / "manifest.json")
    if manifest["bundle_id"] != bundle_id or set(manifest["files"]) != {"results.json"}:
        raise ValueError("manifest mismatch")
    data = (base / "results.json").read_bytes()
    if digest(data) != manifest["files"]["results.json"] or digest(data) != bundle_id:
        raise ValueError("bundle hash mismatch")
    bundle = Bundle.model_validate_json(data)
    if (
        manifest["model_versions"] != bundle.model_versions
        or manifest["schema_version"] != bundle.schema_version
    ):
        raise ValueError("bundle metadata mismatch")
    return manifest, bundle


def publish(root, bundle, sources=(), registry_path="config/sources.yaml"):
    bundle = public_safety(bundle, sources, registry_path)
    data = canonical(bundle.model_dump(mode="json"))
    if len(data) > 2_000_000:
        raise ValueError("public bundle size cap exceeded; archive history explicitly")
    bundle_id = digest(data)
    base = Path(root) / "bundles" / bundle_id
    with lock(root):
        write_json(base / "results.json", bundle.model_dump(mode="json"))
        manifest = {
            "schema_version": "1",
            "bundle_id": bundle_id,
            "generated_at": bundle.generated_at.isoformat(),
            "update_due_at": bundle.update_due_at.isoformat() if bundle.update_due_at else None,
            "source_session_coverage": bundle.source_session_coverage,
            "model_versions": bundle.model_versions,
            "files": {"results.json": bundle_id},
            "pipeline_status": bundle.status,
            "attribution": bundle.attribution,
        }
        write_json(base / "manifest.json", manifest)
        verify_bundle(root, bundle_id)
        pointer = Path(root) / "latest.json"
        if pointer.exists():
            write_json(Path(root) / "previous.json", read_json(pointer))
        write_json(
            pointer,
            {"schema_version": "1", "bundle_id": bundle_id, "manifest_hash": digest(canonical(manifest))},
        )
    return bundle_id


def rollback(root, bundle_id):
    manifest, _ = verify_bundle(root, bundle_id)
    with lock(root):
        write_json(
            Path(root) / "latest.json",
            {"schema_version": "1", "bundle_id": bundle_id, "manifest_hash": digest(canonical(manifest))},
        )
