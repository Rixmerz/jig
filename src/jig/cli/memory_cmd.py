"""jig memory — list and search user-level memories at ~/.jig/memory/."""
from __future__ import annotations

import argparse
import re
import sys


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("memory", help="List or search user-level memories")
    msub = p.add_subparsers(dest="memory_cmd", metavar="SUBCMD")

    # jig memory list
    ls = msub.add_parser("list", help="List all memories")
    ls.add_argument("--type", default=None, help="Filter by type (feedback/project/user/reference)")
    ls.set_defaults(func=_cmd_list)

    # jig memory search
    se = msub.add_parser("search", help="Search memories by keyword")
    se.add_argument("query", help="Search terms")
    se.set_defaults(func=_cmd_search)

    p.set_defaults(func=_cmd_default)


def _cmd_default(args: argparse.Namespace) -> int:
    print("Usage: jig memory <list|search>", file=sys.stderr)
    return 1


def _cmd_list(args: argparse.Namespace) -> int:
    from jig.engines.memory_store import load_all

    nodes = load_all()
    if not nodes:
        print("No memories found in ~/.jig/memory/")
        return 0
    type_filter = getattr(args, "type", None)
    rows = [n for n in nodes.values() if not type_filter or n.type == type_filter]
    rows.sort(key=lambda n: (n.priority != "high", n.type, n.name))
    for n in rows:
        priority_mark = " ★" if n.priority == "high" else ""
        ttl_mark = f" [ttl:{n.ttl}]" if n.ttl else ""
        print(f"  [{n.type}] {n.id}{priority_mark}{ttl_mark}")
        print(f"    {n.description or n.name}")
    print(f"\n{len(rows)} memories")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    from jig.engines.memory_store import load_all

    query = args.query.lower()
    words = set(re.findall(r"[a-z0-9_]{2,}", query))
    nodes = load_all()
    results = []
    for n in nodes.values():
        text = f"{n.name} {n.description} {' '.join(n.tags)} {n.body}".lower()
        score = sum(1 for w in words if w in text)
        if score > 0:
            results.append((score, n))
    results.sort(key=lambda x: -x[0])
    if not results:
        print(f"No memories matching '{args.query}'")
        return 0
    for score, n in results[:10]:
        print(f"  [{n.type}] {n.id}  (score: {score})")
        print(f"    {n.description or n.name}")
    print(f"\n{len(results)} results")
    return 0
