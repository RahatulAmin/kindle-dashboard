"""Export the machine-readable contract for scoped external-client routes."""

import json
from pathlib import Path
from sys import path

ROOT = Path(__file__).resolve().parents[1]
path.insert(0, str(ROOT / "backend"))

from app.main import create_app


def references(value):
    if isinstance(value, dict):
        for key, field in value.items():
            if key == "$ref":
                yield field.rsplit("/", 1)[-1]
            else:
                yield from references(field)
    elif isinstance(value, list):
        for field in value:
            yield from references(field)


def main():
    source = create_app().openapi()
    paths = {
        path: {method: operation for method, operation in operations.items()
               if {"AssistantBearer": []} in operation.get("security", [])}
        for path, operations in source["paths"].items()
    }
    paths = {path: operations for path, operations in paths.items() if operations}
    schemas = {}
    pending = set(references(paths))
    while pending:
        name = pending.pop()
        schema = source["components"]["schemas"][name]
        schemas[name] = schema
        pending.update(set(references(schema)) - schemas.keys())
    result = {
        "openapi": source["openapi"],
        "info": {"title": "Kindle Dashboard External Assistant API", "version": "0.4.0"},
        "paths": paths,
        "components": {"schemas": schemas, "securitySchemes": source["components"]["securitySchemes"]},
    }
    (ROOT / "docs/assistant-openapi.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
