"""A small XML lexer that yields raw events. Safe loading is not implemented here."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class LexError(Exception):
    pass


@dataclass
class Event:
    kind: str
    value: str
    attrs: list[tuple[str, str]] | None = None
    pos: int = 0

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "value": self.value, "pos": self.pos}
        if self.attrs is not None:
            d["attrs"] = [{"name": n, "value": v} for n, v in self.attrs]
        return d


def _read_name(s: str, i: int) -> tuple[str, int]:
    j = i
    if j >= len(s) or not (s[j].isalpha() or s[j] in "_:"):
        raise LexError("bad_name")
    j += 1
    while j < len(s) and (s[j].isalnum() or s[j] in "._:-"):
        j += 1
    return s[i:j], j


def lex(src: str) -> list[Event]:
    ev: list[Event] = []
    i = 0
    n = len(src)
    # BOM
    if src.startswith("\ufeff"):
        ev.append(Event("bom", "utf-8-bom", pos=0))
        i = 1
    while i < n:
        if src[i] == "<":
            if src.startswith("<?", i):
                j = src.find("?>", i)
                if j < 0:
                    raise LexError("unclosed_pi")
                ev.append(Event("pi", src[i + 2:j].strip(), pos=i))
                i = j + 2
                continue
            if src.startswith("<!--", i):
                j = src.find("-->", i)
                if j < 0:
                    raise LexError("unclosed_comment")
                ev.append(Event("comment", src[i + 4:j], pos=i))
                i = j + 3
                continue
            if src.startswith("<!DOCTYPE", i) or src.startswith("<!doctype", i):
                # crude: read until the matching '>' at depth, handling []
                j = i + 9
                depth = 0
                while j < n:
                    if src[j] == "[":
                        depth += 1
                    elif src[j] == "]":
                        depth -= 1
                    elif src[j] == ">" and depth <= 0:
                        break
                    j += 1
                if j >= n:
                    raise LexError("unclosed_doctype")
                ev.append(Event("doctype", src[i:j + 1], pos=i))
                i = j + 1
                continue
            if src.startswith("<![CDATA[", i):
                j = src.find("]]>", i)
                if j < 0:
                    raise LexError("unclosed_cdata")
                ev.append(Event("cdata", src[i + 9:j], pos=i))
                i = j + 3
                continue
            if src.startswith("</", i):
                name, j = _read_name(src, i + 2)
                while j < n and src[j].isspace():
                    j += 1
                if j >= n or src[j] != ">":
                    raise LexError("bad_end_tag")
                ev.append(Event("end", name, pos=i))
                i = j + 1
                continue
            # start tag
            name, j = _read_name(src, i + 1)
            attrs: list[tuple[str, str]] = []
            while j < n and src[j].isspace():
                j += 1
                if j < n and src[j] in "/>":
                    break
                if j < n and (src[j].isalpha() or src[j] in "_:"):
                    an, j = _read_name(src, j)
                    while j < n and src[j].isspace():
                        j += 1
                    if j >= n or src[j] != "=":
                        raise LexError("bad_attr")
                    j += 1
                    while j < n and src[j].isspace():
                        j += 1
                    if j >= n or src[j] not in "\"'":
                        raise LexError("bad_attr")
                    q = src[j]
                    k = src.find(q, j + 1)
                    if k < 0:
                        raise LexError("unclosed_attr")
                    attrs.append((an, src[j + 1:k]))
                    j = k + 1
                    while j < n and src[j].isspace():
                        j += 1
            empty = False
            if j < n and src[j] == "/":
                empty = True
                j += 1
            if j >= n or src[j] != ">":
                raise LexError("bad_start_tag")
            ev.append(Event("start", name, attrs=attrs, pos=i))
            i = j + 1
            if empty:
                ev.append(Event("end", name, pos=i))
            continue
        if src[i] == "&":
            j = src.find(";", i)
            if j < 0:
                raise LexError("unclosed_entity")
            ev.append(Event("entity", src[i + 1:j], pos=i))
            i = j + 1
            continue
        j = i
        while j < n and src[j] not in "<&":
            j += 1
        ev.append(Event("text", src[i:j], pos=i))
        i = j
    return ev


def load_events(path: str | Path) -> list[Event]:
    data = Path(path).read_bytes()
    # decode: UTF-8 default; UTF-16 BOM supported so the renderer can still see encoding tricks
    if data.startswith(b"\xff\xfe"):
        text = data[2:].decode("utf-16-le")
    elif data.startswith(b"\xfe\xff"):
        text = data[2:].decode("utf-16-be")
    elif data.startswith(b"\xef\xbb\xbf"):
        text = data[3:].decode("utf-8")
        text = "\ufeff" + text
    else:
        text = data.decode("utf-8")
    return lex(text)
