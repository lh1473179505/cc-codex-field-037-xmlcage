from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from xmlcage.lex import LexError, load_events


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xmlcage")
    sub = p.add_subparsers(dest="cmd", required=True)
    ins = sub.add_parser("inspect", help="lex an XML document into events")
    ins.add_argument("--doc", required=True)
    bld = sub.add_parser("build", help="safely expand entities and build a tree")
    bld.add_argument("--doc", required=True)
    bld.add_argument("--policy", required=True)
    bld.add_argument("--dtd-dir", required=False)
    bld.add_argument("--report", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        events = load_events(args.doc)
    except (OSError, UnicodeDecodeError, LexError) as exc:
        print(f"failed to lex document: {exc}", file=sys.stderr)
        return 2
    if args.cmd == "inspect":
        print(json.dumps({"events": [e.as_dict() for e in events]}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "build":
        try:
            policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"failed to load policy: {exc}", file=sys.stderr)
            return 2
        from xmlcage.engine import build

        try:
            report = build(events, policy, getattr(args, "dtd_dir", None))
        except NotImplementedError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        decision = str(report.get("decision", "")).lower()
        if decision == "allow":
            return 0
        if decision == "deny":
            return 1
        print("report is missing a decision of allow or deny", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
