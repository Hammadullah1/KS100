"""Static checks only. A passing result is not a successful hosted workflow."""

import re
from pathlib import Path

import yaml

from psx_pipeline.storage import read_json, write_json

pins = read_json("reports/action-pins.json")
checked = []
for path in sorted(Path(".github/workflows").glob("*.yml")):
    value = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert value["on"], path
    for job in value["jobs"].values():
        assert int(job["timeout-minutes"]) <= 45, path
        for step in job.get("steps", []):
            if "uses" not in step:
                continue
            use = step["uses"]
            repo, sha = use.split("@")
            assert re.fullmatch("[a-f0-9]{40}", sha), (path, use)
            assert pins[repo]["sha"] == sha, (path, use)
    checked.append(path.name)
assert set(checked) == {"ci.yml", "daily.yml", "research.yml", "release.yml", "live-research.yml"}
write_json(
    "reports/workflow-static-check.json", {"status": "passed", "files": checked, "hosted_run_verified": False}
)
print("Workflow static checks passed:", ", ".join(checked))
