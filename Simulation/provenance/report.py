"""
Provenance report: a plain-text query interface over provenance/catalog.py,
same "no dashboard, plain report" convention as stats/report.py,
validation/report.py, and financial_system/bridges/capability_report.py
(Design.md: "plain text or Markdown, printed to console and optionally
saved to a file -- no dashboard, no charts").

Real, runnable queries against the real catalog -- not a static table:

    python provenance/report.py --research-grounded
    python provenance/report.py --placeholders
    python provenance/report.py --modeling-assumptions
    python provenance/report.py --rejected-alternatives
    python provenance/report.py --show SAVINGS_SWEEP_FRACTION
    python provenance/report.py --status proposed
    python provenance/report.py --all
    python provenance/report.py --all --save provenance/CATALOG.md   (markdown export)

Run without arguments for a one-line-per-entry summary of the whole catalog.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance.catalog import (  # noqa: E402
    CATALOG, ProvenanceEntry, VERIFIED_AT_COMMIT, all_entries, by_status, modeling_assumptions, placeholders,
    proposed, research_grounded, with_rejected_alternatives,
)


def _entry_block(e: ProvenanceEntry, markdown: bool = False) -> str:
    lines = []
    header = f"{e.constant_name}  [{e.provenance_type}, {e.status}]"
    lines.append(f"### {header}" if markdown else header)
    lines.append(f"  location: {e.location}")
    lines.append(f"  value:    {e.value}")
    lines.append(f"  source:   {e.source}")
    if e.citation_verbatim:
        lines.append(f"  citation_verbatim (checked against Research.md): {e.citation_verbatim!r}")
    if e.confidence_note:
        lines.append(f"  confidence_note: {e.confidence_note}")
    if e.rejected_alternatives:
        lines.append(f"  rejected_alternatives: {e.rejected_alternatives}")
    if e.notes:
        lines.append(f"  notes: {e.notes}")
    return "\n".join(lines)


def _summary_line(e: ProvenanceEntry) -> str:
    return f"  {e.constant_name:<48} [{e.provenance_type:<19} {e.status:<11}] {e.value}"


def build_full_report(markdown: bool = False) -> str:
    lines = []
    title = "Project Truman -- Research Provenance Catalog"
    lines.append(f"# {title}" if markdown else f"=== {title} ===")
    lines.append(f"(verified against commit {VERIFIED_AT_COMMIT}; {len(CATALOG)} entries: "
                  f"{len(by_status('implemented'))} implemented, {len(by_status('proposed'))} proposed)")
    lines.append("")
    for e in sorted(all_entries(), key=lambda x: (x.status, x.provenance_type, x.constant_name)):
        lines.append(_entry_block(e, markdown=markdown))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_summary(entries: list[ProvenanceEntry], title: str) -> str:
    lines = [f"=== {title} ({len(entries)}) ===", ""]
    for e in sorted(entries, key=lambda x: x.constant_name):
        lines.append(_summary_line(e))
    return "\n".join(lines).rstrip() + "\n"


def build_show(constant_name: str) -> str:
    if constant_name not in CATALOG:
        matches = [n for n in CATALOG if constant_name.lower() in n.lower()]
        if matches:
            return (
                f"No exact entry named {constant_name!r}. Did you mean:\n" + "\n".join(f"  {m}" for m in matches)
            )
        return f"No entry named {constant_name!r} in the catalog ({len(CATALOG)} entries total)."
    return "=== " + constant_name + " ===\n" + _entry_block(CATALOG[constant_name]) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Project Truman's research provenance catalog.")
    parser.add_argument("--research-grounded", action="store_true", help="list all research-grounded entries, with citations")
    parser.add_argument("--modeling-assumptions", action="store_true", help="list all modeling-assumption entries")
    parser.add_argument("--placeholders", action="store_true", help="list everything still a placeholder")
    parser.add_argument("--rejected-alternatives", action="store_true", help="list every considered-and-rejected alternative, and why")
    parser.add_argument("--status", choices=["implemented", "proposed"], help="list entries by implementation status")
    parser.add_argument("--show", metavar="CONSTANT_NAME", help="show the full entry for one constant")
    parser.add_argument("--all", action="store_true", help="print the full catalog, every field")
    parser.add_argument("--markdown", action="store_true", help="format --all output as Markdown")
    parser.add_argument("--save", metavar="PATH", help="also write the report to this file")
    args = parser.parse_args()

    out = None
    if args.show:
        out = build_show(args.show)
    elif args.research_grounded:
        out = build_summary(research_grounded(), "Research-grounded entries")
    elif args.modeling_assumptions:
        out = build_summary(modeling_assumptions(), "Modeling-assumption entries")
    elif args.placeholders:
        out = build_summary(placeholders(), "Placeholder entries")
    elif args.rejected_alternatives:
        entries = with_rejected_alternatives()
        lines = [f"=== Considered-and-rejected alternatives ({len(entries)}) ===", ""]
        for e in sorted(entries, key=lambda x: x.constant_name):
            lines.append(f"{e.constant_name}  [{e.provenance_type}, {e.status}]")
            lines.append(f"  rejected_alternatives: {e.rejected_alternatives}")
            lines.append("")
        out = "\n".join(lines).rstrip() + "\n"
    elif args.status:
        out = build_summary(by_status(args.status), f"status={args.status}")
    elif args.all:
        out = build_full_report(markdown=args.markdown)
    else:
        out = build_summary(all_entries(), "All catalog entries (one line each; use --show NAME for detail)")

    print(out)
    if args.save:
        Path(args.save).write_text(out, encoding="utf-8")
        print(f"(also saved to {args.save})", file=sys.stderr)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
