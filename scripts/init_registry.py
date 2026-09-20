import json
from pathlib import Path

rows = {
    "psx": (
        "Pakistan Stock Exchange / Capital Stake",
        "https://dps.psx.com.pk/",
        "PSX:KSE100:TR",
        "index_points",
        "https://www.psx.com.pk/psx/product-and-services/data-services-vending",
    ),
    "corporate_actions": (
        "Pakistan Stock Exchange",
        "https://dps.psx.com.pk/",
        "actions",
        "ratio/PKR",
        "https://dps.psx.com.pk/",
    ),
    "membership": (
        "Pakistan Stock Exchange",
        "https://www.psx.com.pk/psx/product-and-services/indices",
        "membership",
        "fraction",
        "https://dps.psx.com.pk/",
    ),
    "sbp": (
        "State Bank of Pakistan",
        "https://www.sbp.org.pk/economic-data",
        "fx/rates",
        "definition_required",
        "https://www.sbp.org.pk/economic-data",
    ),
    "eia": (
        "US Energy Information Administration",
        "https://www.eia.gov/opendata/documentation.php",
        "PET.RBRTE.D",
        "USD/barrel",
        "https://www.eia.gov/about/copyrights_reuse.php",
    ),
    "fred": (
        "Federal Reserve Bank of St. Louis",
        "https://fred.stlouisfed.org/docs/api/fred/",
        "DCOILBRENTEU",
        "USD/barrel",
        "https://fred.stlouisfed.org/docs/api/terms_of_use.html",
    ),
    "nccpl": (
        "National Clearing Company of Pakistan",
        "https://www.nccpl.com.pk/market-information",
        "FIPI/LIPI",
        "unverified",
        "https://www.nccpl.com.pk/market-information",
    ),
    "pbs": (
        "Pakistan Bureau of Statistics",
        "https://www.pbs.gov.pk/press-release/",
        "CPI",
        "definition_required",
        "https://www.pbs.gov.pk/press-release/",
    ),
    "disclosures": (
        "Official issuer / authority",
        "https://dps.psx.com.pk/",
        "events",
        "metadata",
        "https://dps.psx.com.pk/",
    ),
}
sources = {}
for key, (identity, url, series, units, evidence) in rows.items():
    eia = key == "eia"
    sources[key] = {
        "identity": identity,
        "documentation_url": url,
        "evidence_url": evidence,
        "reviewed_at": "2026-09-18",
        "review_expires": "2027-03-18",
        "endpoint": "https://api.eia.gov/v2/seriesid/PET.RBRTE.D" if eia else None,
        "mechanism": "documented_api_route_unverified_live" if eia else "manual_normalized_import",
        "enabled": False,
        "permissions": {
            p: "approved" if eia else "unknown"
            for p in ["collection", "private_storage", "training", "public_raw", "public_derived"]
        },
        "authentication": "EIA_API_KEY" if eia else ("FRED_API_KEY" if key == "fred" else "unverified"),
        "free_limits": "free key; quota unverified" if eia else "unverified",
        "rate_limit": "one request/second project cap; provider limit unverified",
        "attribution": identity,
        "series": series,
        "units": units,
        "fields": ["reference_period", "value", "published_at", "available_at", "vintage"],
        "adjustment_basis": "source-defined; normalized instrument must match",
        "timezone": "UTC availability; observation timezone needs evidence",
        "history_depth": "unverified",
        "publication_schedule": "unverified",
        "revision_behavior": "append vintages",
        "historical_availability": "unverified",
        "owner": "project maintainer",
        "parser_version": "normalized-v1",
        "timeout_seconds": 20,
        "attempts": 3,
        "fallback": "unavailable; never silently switch to fixtures",
        "blocker": "API key, live shape check and historical release evidence"
        if eia
        else "permitted sample and dated rights evidence",
    }
Path("config/sources.yaml").write_text(
    json.dumps({"schema_version": "1", "sources": sources}, indent=2) + "\n", encoding="utf-8"
)
