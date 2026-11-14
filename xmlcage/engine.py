"""Safe XML document builder: budgeted entity expansion over lexer events."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from xmlcage.lex import Event, LexError, lex

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9._:-]*$")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_ENTITY_DECL_RE = re.compile(
    r"<!ENTITY\s+(%\s+)?([A-Za-z_:][A-Za-z0-9._:-]*)\s+(.*?)\s*>\s*$", re.S
)
_EXT_ID_RE = re.compile(
    r"(?:SYSTEM\s+([\"'])(?P<sys>.*?)\1"
    r"|PUBLIC\s+([\"']).*?\3\s+([\"'])(?P<pub>.*?)\4)\s*$",
    re.S,
)
_PE_REF_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9._:-]*);")
_DOCTYPE_SYS_RE = re.compile(r"\bSYSTEM\s+([\"'])(.*?)\1", re.S)
_DOCTYPE_PUB_RE = re.compile(r"\bPUBLIC\s+([\"']).*?\1\s+([\"'])(.*?)\2", re.S)

_BUILTINS = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


class _Deny(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _load_external(uri: str, dtd_dir: str | None) -> str:
    """Load a local DTD fragment; anything remotely suspicious is external_id."""
    if _SCHEME_RE.match(uri) or uri.startswith("//") or uri.startswith("\\\\"):
        raise _Deny("external_id")
    if ".." in uri:
        raise _Deny("external_id")
    if dtd_dir is None:
        raise _Deny("external_id")
    base = Path(dtd_dir).resolve()
    target = (base / uri).resolve()
    if target != base and base not in target.parents:
        raise _Deny("external_id")
    try:
        return target.read_text(encoding="utf-8")
    except OSError:
        raise _Deny("external_id")


def _scan_decls(text: str) -> list[str]:
    """Split DTD text into markup declarations, respecting quoted sections."""
    decls: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "<":
            i += 1
            continue
        if text.startswith("<!--", i):
            j = text.find("-->", i)
            i = n if j < 0 else j + 3
            continue
        if text.startswith("<?", i):
            j = text.find("?>", i)
            i = n if j < 0 else j + 2
            continue
        j = i + 1
        quote: str | None = None
        while j < n:
            ch = text[j]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == ">":
                break
            j += 1
        decls.append(text[i : j + 1] if j < n else text[i:])
        i = j + 1
    return decls


def _store_entity(decl: str, dtd_dir: str | None, table: dict[str, str]) -> None:
    m = _ENTITY_DECL_RE.match(decl)
    if not m:
        return
    name = m.group(2)
    rest = m.group(3).strip()
    if rest[:1] in ("\"", "'"):
        quote = rest[0]
        end = rest.find(quote, 1)
        value = rest[1:end] if end >= 0 else rest[1:]
    else:
        ext = _EXT_ID_RE.match(rest)
        if not ext:
            return
        uri = ext.group("sys") if ext.group("sys") is not None else ext.group("pub")
        value = _load_external(uri, dtd_dir)
    if name not in table:
        table[name] = value


def _parse_dtd_text(
    text: str,
    dtd_dir: str | None,
    entities: dict[str, str],
    pe_entities: dict[str, str],
    notes: list[str],
) -> None:
    decls = _scan_decls(text)
    for decl in decls:
        m = _ENTITY_DECL_RE.match(decl)
        if m and m.group(1):
            _store_entity(decl, dtd_dir, pe_entities)
    # Parameter entities may be used inside the DTD itself; expand with a cap.
    # References may sit between declarations, so expand in the full text.
    expanded = text
    for _ in range(8):
        new_text = _PE_REF_RE.sub(
            lambda mm: pe_entities.get(mm.group(1), mm.group(0)), expanded
        )
        if new_text == expanded:
            break
        expanded = new_text
    for decl in _scan_decls(expanded):
        if decl.startswith("<!ATTLIST"):
            # Defaults must never be auto-inserted into the tree; note only.
            if ('"' in decl or "'" in decl) and "default_attr_ignored" not in notes:
                notes.append("default_attr_ignored")
            continue
        m = _ENTITY_DECL_RE.match(decl)
        if m and not m.group(1):
            _store_entity(decl, dtd_dir, entities)


def _parse_doctype(
    raw: str,
    dtd_dir: str | None,
    entities: dict[str, str],
    pe_entities: dict[str, str],
    notes: list[str],
) -> None:
    body = re.sub(r"^<!DOCTYPE", "", raw, flags=re.I).strip()
    if body.endswith(">"):
        body = body[:-1]
    subset = ""
    bracket = body.find("[")
    if bracket >= 0:
        close = body.rfind("]")
        if close < bracket:
            close = len(body)
        subset = body[bracket + 1 : close]
        header = body[:bracket]
    else:
        header = body
    m = _DOCTYPE_SYS_RE.search(header)
    if m:
        uri: str | None = m.group(2)
    else:
        m = _DOCTYPE_PUB_RE.search(header)
        uri = m.group(3) if m else None
    if uri is not None:
        fragment = _load_external(uri, dtd_dir)
        _parse_dtd_text(fragment, dtd_dir, entities, pe_entities, notes)
    if subset:
        _parse_dtd_text(subset, dtd_dir, entities, pe_entities, notes)


class _Builder:
    def __init__(
        self,
        policy: dict[str, Any],
        entities: dict[str, str],
        pe_entities: dict[str, str],
    ) -> None:
        self.entities = entities
        self.pe_entities = pe_entities
        self.max_depth = int(policy.get("max_entity_depth", 4))
        self.max_expansions = int(policy.get("max_expansions", 32))
        self.max_bytes = int(policy.get("max_expansion_bytes", 4096))
        self.max_text = int(policy.get("max_text_bytes", 2048))
        self.expansion_count = 0
        self.expansion_bytes = 0
        self.stack: list[dict[str, Any]] = []
        self.text_lens: list[int] = []
        self.root: dict[str, Any] | None = None
        self.exp_stack: list[str] = []
        self.attr_sink: list[str] | None = None

    def add_text(self, s: str) -> None:
        if self.attr_sink is not None:
            self.attr_sink.append(s)
            return
        if not self.stack:
            return  # character data outside the root element is ignored
        idx = len(self.text_lens) - 1
        self.text_lens[idx] += len(s)
        if self.text_lens[idx] > self.max_text:
            raise _Deny("text_blowup")
        children = self.stack[-1]["children"]
        if children and isinstance(children[-1], str):
            children[-1] += s
        else:
            children.append(s)

    def process(self, events: list[Event]) -> None:
        for ev in events:
            kind = ev.kind
            if kind == "start":
                self._start(ev)
            elif kind == "end":
                self._end(ev)
            elif kind in ("text", "cdata"):
                self.add_text(ev.value)
            elif kind == "entity":
                self._entity(ev.value)
            # comment / pi / doctype / bom carry no tree content

    def _start(self, ev: Event) -> None:
        name = ev.value
        if not _NAME_RE.match(name):
            raise _Deny("bad_name")
        attrs: dict[str, str] = {}
        for attr_name, raw_value in ev.attrs or []:
            if not _NAME_RE.match(attr_name):
                raise _Deny("bad_name")
            if attr_name in attrs:
                raise _Deny("dup_attr")
            attrs[attr_name] = self._expand_attr(raw_value)
        elem: dict[str, Any] = {"name": name, "attrs": attrs, "children": []}
        if self.stack:
            self.stack[-1]["children"].append(elem)
        else:
            if self.root is not None:
                raise _Deny("multiple_root")
            self.root = elem
        self.stack.append(elem)
        self.text_lens.append(0)

    def _end(self, ev: Event) -> None:
        if not self.stack or self.stack[-1]["name"] != ev.value:
            raise _Deny("unbalanced")
        self.stack.pop()
        self.text_lens.pop()

    def _expand_attr(self, raw: str) -> str:
        if "<" in raw:
            raise _Deny("attr_lt")
        try:
            sub = lex(raw)
        except LexError as exc:
            raise _Deny(str(exc) or "unknown_entity")
        self.attr_sink = []
        try:
            self.process(sub)
        finally:
            sink = self.attr_sink
            self.attr_sink = None
        return "".join(sink)

    @staticmethod
    def _char_ref(name: str) -> str:
        try:
            if name[1:2] in ("x", "X"):
                return chr(int(name[2:], 16))
            return chr(int(name[1:], 10))
        except (ValueError, OverflowError):
            raise _Deny("unknown_entity")

    def _entity(self, name: str) -> None:
        if name.startswith("#"):
            self.add_text(self._char_ref(name))
            return
        if name in _BUILTINS:
            self.add_text(_BUILTINS[name])
            return
        if name in self.entities:
            self._expand_named(name)
            return
        if name in self.pe_entities:
            raise _Deny("pe_in_content")
        raise _Deny("unknown_entity")

    def _expand_named(self, name: str) -> None:
        if name in self.exp_stack:
            raise _Deny("entity_cycle")
        if len(self.exp_stack) + 1 > self.max_depth:
            raise _Deny("entity_depth")
        self.expansion_count += 1
        if self.expansion_count > self.max_expansions:
            raise _Deny("entity_count")
        replacement = self.entities[name]
        self.expansion_bytes += len(replacement)
        if self.expansion_bytes > self.max_bytes:
            raise _Deny("entity_bytes")
        try:
            sub = lex(replacement)
        except LexError as exc:
            raise _Deny(str(exc) or "unknown_entity")
        self.exp_stack.append(name)
        try:
            self.process(sub)
        finally:
            self.exp_stack.pop()


def build(
    events: list[Event],
    policy: dict[str, Any],
    dtd_dir: str | None,
) -> dict[str, Any]:
    entities: dict[str, str] = {}
    pe_entities: dict[str, str] = {}
    notes: list[str] = []
    builder = _Builder(policy, entities, pe_entities)
    try:
        for ev in events:
            if ev.kind == "doctype":
                _parse_doctype(ev.value, dtd_dir, entities, pe_entities, notes)
                break
        builder.process(events)
        if builder.stack:
            raise _Deny("unbalanced")
        if builder.root is None:
            raise _Deny("no_root")
    except _Deny as deny:
        return {
            "decision": "deny",
            "reason_codes": [deny.code],
            "root": None,
            "notes": notes,
            "expansion_count": builder.expansion_count,
            "expansion_bytes": builder.expansion_bytes,
        }
    return {
        "decision": "allow",
        "reason_codes": [],
        "root": builder.root,
        "notes": notes,
        "expansion_count": builder.expansion_count,
        "expansion_bytes": builder.expansion_bytes,
    }
