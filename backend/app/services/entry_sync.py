from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.services.assistant import audit, timestamp

EXTERNAL_FIELDS = {"source", "external_ref"}
PROTECTED_UPSERT_FIELDS = {"completed", "position", "kindle_visible", "archived"}


def find(db, model, item_id):
    record = db.get(model, item_id)
    if record is None:
        raise HTTPException(404, "This entry no longer exists.")
    return record


def filtered(query, model, filters):
    for field in ("completed", "source", "external_ref"):
        value = getattr(filters, field)
        if value is not None:
            query = query.where(getattr(model, field) == value)
    if filters.due_from is not None:
        query = query.where(model.due_date >= filters.due_from)
    if filters.due_to is not None:
        query = query.where(model.due_date <= filters.due_to)
    if filters.updated_since is not None:
        query = query.where(model.updated_at >= timestamp(filters.updated_since))
    return query


def by_external_id(db, model, source, external_ref):
    if source is not None:
        return db.scalar(select(model).where(model.source == source, model.external_ref == external_ref))


def validate_fields(schema, values):
    try:
        return schema.model_validate(values).model_dump()
    except ValidationError as error:
        first = error.errors(include_input=False)[0]
        field = ".".join(map(str, first["loc"]))
        raise HTTPException(422, f"{field}: {first['msg']}") from None


def conflict(resource, record, message="Entry version has changed. Retrieve the latest state and retry."):
    path = f"/api/v1/{resource}s/{record.id}"
    return HTTPException(409, message, headers={
        "Link": f'<{path}>; rel="latest-version"',
        "ETag": f'"{record.updated_at}"',
        "Cache-Control": "no-store",
    })


def change_entry(db, model, schema, resource, data, token, item_id=None):
    values = data.model_dump(exclude_unset=True)
    expected = values.pop("expected_updated_at", None)
    external = {field: values.pop(field) for field in EXTERNAL_FIELDS if field in values}
    if token is None:
        external = {}
        if expected is not None:
            raise HTTPException(422, "Versioned synchronization requires an API token.")

    upserting = token is not None and item_id is None and external.get("source") is not None
    record = find(db, model, item_id) if item_id is not None else None
    if upserting:
        record = by_external_id(db, model, external["source"], external["external_ref"])

    if record is None:
        if expected is not None:
            raise HTTPException(409, "No existing entry matches this version.")
        if token is not None:
            values.setdefault("kindle_visible", False)
        normalized = validate_fields(schema, values)
        record = model(**normalized, **external)
        db.add(record)
        db.flush()
        audit(db, token, "create", resource, record.id, set(normalized) | external.keys())
        db.commit()
        return record, True

    if token is None:
        proposed = validate_fields(schema, values)
    else:
        merged = {field: getattr(record, field) for field in schema.model_fields}
        proposed = validate_fields(schema, {**merged, **values})
        proposed = {field: proposed[field] for field in values} | external

    changes = {field: value for field, value in proposed.items() if getattr(record, field) != value}
    if changes:
        if expected is not None and timestamp(expected) != record.updated_at:
            raise conflict(resource, record)
        protected = PROTECTED_UPSERT_FIELDS if upserting else {"completed"}
        if token is not None and expected is None and changes.keys() & protected:
            raise conflict(resource, record, "Supply the current expected_updated_at to change protected fields.")
        if changes.keys() & EXTERNAL_FIELDS:
            duplicate = by_external_id(db, model, external["source"], external["external_ref"])
            if duplicate is not None and duplicate.id != record.id:
                raise conflict(resource, duplicate, "External identity already belongs to another entry.")
        for field, value in changes.items():
            setattr(record, field, value)
        audit(db, token, "upsert" if upserting else "update", resource, record.id, changes)
    db.commit()
    return record, False


def delete_entry(db, model, resource, item_id, token, expected):
    record = find(db, model, item_id)
    if expected is not None and timestamp(expected) != record.updated_at:
        raise conflict(resource, record)
    audit(db, token, "delete", resource, item_id)
    db.delete(record)
    db.commit()
