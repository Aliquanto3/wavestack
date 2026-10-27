"""Tool-call parsers, one per family format (AD-6).

- `qwen3_coder`: `<tool_call><function=NAME><parameter=ARG>value</parameter>`
  `</function></tool_call>`, values converted according to the tool's schema;
- `hermes`: `<tool_call>{"name": ..., "arguments": {...}}</tool_call>`;
- `minicpm5`: `<function name="NAME"><param name="ARG">value</param></function>`, no wrapper;
  a value with `<`, `&` or a newline is in a `<![CDATA[…]]>`, the call ends at the first
  `</function>` outside a CDATA.

A parse never raises: it returns the calls, or what is malformed and why (a `Message`,
French as a text, rendered in the session's language by the executor).
"""

from __future__ import annotations

import hashlib
import json
import re
import string
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import unescape

from wavestack.messages import Message
from wavestack.models.capabilities import tool_call_tags

_BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase


def tool_call_id(step_id: str, index: int) -> str:
    """AD-4: 9 base-62 characters of the hash of `"{step_id}#{index}"`, attributed by the
    session to every call it creates (model output)."""
    n = int.from_bytes(hashlib.sha256(f"{step_id}#{index}".encode()).digest(), "big")
    digits = []
    for _ in range(9):
        n, r = divmod(n, 62)
        digits.append(_BASE62[r])
    return "".join(digits)


_FUNCTION = re.compile(r"\s*<function=([^>\s]+)>(.*)</function>\s*", re.DOTALL)
_PARAMETER = re.compile(r"<parameter=([^>\s]+)>(.*?)</parameter>", re.DOTALL)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    source: str = field(default="", compare=False)  # its `<tool_call>…</tool_call>` block


@dataclass(frozen=True)
class Malformed:
    fragment: str  # the faulty part of the raw output
    detail_text: str


def convert_value(value: str, kind: str | None) -> Any:
    """`qwen3_coder` values are text: convert them per the schema, keep the text on failure."""
    try:
        match kind:
            case "integer":
                return int(value)
            case "number":
                return float(value)
            case "boolean" if value.strip().lower() in ("true", "false"):
                return value.strip().lower() == "true"
            case "object" | "array":
                return json.loads(value)
    except ValueError:
        pass
    return value


def _qwen3_coder(inner: str, schemas: dict[str, dict[str, str]]) -> ToolCall | str:
    function = _FUNCTION.fullmatch(inner)
    if function is None:
        return Message("tools.parser.function_tag")
    name, body = function.groups()
    params = _PARAMETER.findall(body)
    if len(params) != body.count("<parameter="):
        return Message("tools.parser.parameter_unclosed")
    schema = schemas.get(name, {})
    arguments = {}
    for arg, value in params:
        value = value.removeprefix("\n").removesuffix("\n")
        arguments[arg] = convert_value(value, schema.get(arg))
    return ToolCall(name, arguments)


def _hermes(inner: str, _schemas: dict[str, dict[str, str]]) -> ToolCall | str:
    try:
        data = json.loads(inner)
    except ValueError as exc:
        return Message("tools.parser.json_unreadable", cause=exc)
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return Message("tools.parser.no_name")
    arguments = data.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return Message("tools.parser.arguments_not_object")
    if not isinstance(arguments, dict):
        return Message("tools.parser.arguments_not_object")
    return ToolCall(data["name"], arguments)


_MC_FUNCTION = re.compile(r'<function name="([^"]+)">')
_CDATA = ("<![CDATA[", "]]>")
_ENTITIES = {"&quot;": '"', "&apos;": "'"}


def _minicpm5_end(raw: str, start: int) -> int:
    """Index just past the first `</function>` outside a CDATA after `start`, or -1 (also
    when a new `<function name="` opens first: the call was never closed)."""
    close = "</function>"
    pos = start
    while True:
        end, cdata = raw.find(close, pos), raw.find(_CDATA[0], pos)
        opening = raw.find('<function name="', pos)
        if end < 0 or 0 <= opening < end and (cdata < 0 or opening < cdata):
            return -1
        if cdata < 0 or end < cdata:
            return end + len(close)
        cdata_end = raw.find(_CDATA[1], cdata)
        if cdata_end < 0:
            return -1
        pos = cdata_end + len(_CDATA[1])


def _minicpm5_params(body: str) -> list[tuple[str, str]] | None:
    """The `(name, raw value)` pairs of `body`, or `None` when a `<param>` is not closed."""
    params: list[tuple[str, str]] = []
    pos = 0
    while (start := body.find('<param name="', pos)) >= 0:
        head = re.compile(r'<param name="([^"]*)">').match(body, start)
        if head is None:
            return None
        at = head.end()
        if body.startswith(_CDATA[0], at):
            stop = body.find(_CDATA[1], at)
            if stop < 0 or not body.startswith("</param>", stop + len(_CDATA[1])):
                return None
            params.append((head.group(1), body[at + len(_CDATA[0]) : stop]))
            pos = stop + len(_CDATA[1]) + len("</param>")
        else:
            stop = body.find("</param>", at)
            if stop < 0:
                return None
            params.append((head.group(1), unescape(body[at:stop], _ENTITIES)))
            pos = stop + len("</param>")
    return params


def _minicpm5(block: str, schemas: dict[str, dict[str, str]]) -> ToolCall | str:
    head = _MC_FUNCTION.match(block)
    if head is None:
        return Message("tools.parser.minicpm5_function_tag")
    body = block[head.end() : -len("</function>")]
    params = _minicpm5_params(body)
    if params is None:
        return Message("tools.parser.minicpm5_param_unclosed")
    schema = schemas.get(head.group(1), {})
    return ToolCall(
        head.group(1), {arg: convert_value(value, schema.get(arg)) for arg, value in params}
    )


def _parse_minicpm5(
    raw: str, schemas: dict[str, dict[str, str]]
) -> tuple[list[ToolCall], Malformed | None]:
    calls: list[ToolCall] = []
    pos = 0
    while (start := raw.find('<function name="', pos)) >= 0:
        head = _MC_FUNCTION.match(raw, start)
        if head is None:
            tag_end = raw.find(">", start)
            return [], Malformed(
                raw[start : tag_end + 1 if tag_end >= 0 else None],
                Message("tools.parser.minicpm5_function_tag"),
            )
        end = _minicpm5_end(raw, head.end())
        if end < 0:
            return [], Malformed(raw[start:], Message("tools.parser.minicpm5_never_closed"))
        block = raw[start:end]
        result = _minicpm5(block, schemas)
        if isinstance(result, str):
            return [], Malformed(block, result)
        calls.append(ToolCall(result.name, result.arguments, block))
        pos = end
    return calls, None


_FORMATS = {"qwen3_coder": _qwen3_coder, "hermes": _hermes}


def parse_tool_calls(
    raw: str, parser: str, schemas: dict[str, dict[str, str]]
) -> tuple[list[ToolCall], Malformed | None]:
    """Every `<tool_call>` block of `raw`; one malformed block makes the whole output malformed."""
    if parser == "minicpm5":
        return _parse_minicpm5(raw, schemas)
    open_tag, close_tag = tool_call_tags(parser)
    parse = _FORMATS[parser]
    calls: list[ToolCall] = []
    pos = 0
    while (start := raw.find(open_tag, pos)) >= 0:
        end = raw.find(close_tag, start)
        if end < 0:
            return [], Malformed(raw[start:], Message("tools.parser.never_closed"))
        block = raw[start : end + len(close_tag)]
        result = parse(raw[start + len(open_tag) : end], schemas)
        if isinstance(result, str):
            return [], Malformed(block, result)
        calls.append(ToolCall(result.name, result.arguments, block))
        pos = end + len(close_tag)
    return calls, None
