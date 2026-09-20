from pathlib import Path

from psx_pipeline.contracts import TABLES, Bundle
from psx_pipeline.storage import write_json

for name, model in TABLES.items():
    write_json(Path("src/psx_pipeline/schemas") / (name + ".schema.json"), model.model_json_schema())
write_json("web/src/bundle.schema.json", Bundle.model_json_schema())
