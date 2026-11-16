"""The JSON schema a tool's parameters are shown to the talker as (`model_schema`; plan 010):
pydantic's schema of the arguments' model, said the way a model fills it in reliably, every
argument it accepts still accepted, none added:

- **No titles.** The model reads the schema at every request and needs none of pydantic's
  `title` keywords (a property named "title" is kept).
- **No references.** Each `$ref` to `$defs` is replaced by the definition itself, and `$defs`
  left out: gpt-oss on Groq sees a tool's schema rendered as a type, and a referenced type
  reaches it as a bare name with no fields, so it wrote a date form as text («الخميس الجاي»)
  and Groq refused every such call (`tool_use_failed`, 37 of 56 requests on run F's first turns,
  none once inlined; plan 010's progress log, 2026-11-17). A reference that leads back to itself
  (a recursive model) is kept, with the definitions it still needs.
- **A union as `anyOf`.** pydantic writes a discriminated union as `oneOf` with an OpenAPI
  `discriminator`; its branches never overlap (each holds its own constant), so `anyOf` says the
  same, and the `discriminator` keyword, no JSON Schema, is left out.
- **A constant is required.** A field holding one value (`Literal["on"] = "on"`, a union's tag)
  is listed as required, with no default: the union is told apart by it, so an argument without
  it never validates (the model left `kind` out once in 40 date forms while it was optional).

A schema with none of these (no reference, union or constant, as a tool of plain arguments) is
the same as before but for its titles.
"""

from __future__ import annotations

import copy
from typing import Any, Final

# The keys of a JSON schema whose value maps names to schemas, not keywords to values.
SCHEMA_MAPS: Final = frozenset({"properties", "$defs", "definitions", "patternProperties"})
_DEFS: Final = ("$defs", "definitions")


def model_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """`schema` (pydantic's, of a tool's parameters) as the talker is shown it (the module's
    docstring)."""
    defs: dict[str, Any] = {}
    for key in _DEFS:
        defs.update(schema.get(key) or {})
    kept: set[str] = set()
    shown: dict[str, Any] = _shown(_inline(schema, defs, (), kept))
    needed: dict[str, Any] = {}
    while todo := sorted(kept - needed.keys()):  # a recursive reference: what it still needs
        for name in todo:
            needed[name] = _shown(_inline(defs[name], defs, (name,), kept))
    if needed:
        shown["$defs"] = needed
    return shown


def _name(ref: str) -> str | None:
    for key in _DEFS:
        prefix = f"#/{key}/"
        if ref.startswith(prefix):
            return ref.removeprefix(prefix)
    return None


def _inline(node: Any, defs: dict[str, Any], path: tuple[str, ...], kept: set[str]) -> Any:
    """`node` with each reference to `defs` replaced by its definition, a reference along
    `path` (the definitions being inlined) kept and its name added to `kept`."""
    if isinstance(node, list):
        return [_inline(item, defs, path, kept) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    name = _name(ref) if isinstance(ref, str) else None
    if name is not None and name in defs:
        if name in path:
            kept.add(name)
            return {"$ref": f"#/$defs/{name}"}
        merged = {**copy.deepcopy(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
        return _inline(merged, defs, (*path, name), kept)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DEFS:
            continue
        if key in SCHEMA_MAPS and isinstance(value, dict):
            out[key] = {k: _inline(v, defs, path, kept) for k, v in value.items()}
        else:
            out[key] = _inline(value, defs, path, kept)
    return out


def _shown(node: Any) -> Any:
    """`node` untitled, each union an `anyOf` with no `discriminator`, each constant required."""
    if isinstance(node, list):
        return [_shown(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "discriminator" or (key == "title" and isinstance(value, str)):
            continue
        if key in SCHEMA_MAPS and isinstance(value, dict):
            out[key] = {k: _shown(v) for k, v in value.items()}
        else:
            out["anyOf" if key == "oneOf" else key] = _shown(value)
    properties = out.get("properties")
    if out.get("type") == "object" and isinstance(properties, dict):
        constants = [k for k, v in properties.items() if isinstance(v, dict) and "const" in v]
        for k in constants:
            properties[k] = {kk: vv for kk, vv in properties[k].items() if kk != "default"}
        if constants:
            required = [r for r in out.get("required", []) if r not in constants]
            out["required"] = [*constants, *required]
    return out
