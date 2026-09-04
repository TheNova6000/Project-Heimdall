"""
Tests for provenance/catalog.py (docs/NORTH_STAR.md Section 34/40's bounded
implementation -- see that module's docstring for scope).

Three real, automated checks, per this task's own stated priorities:

1. test_every_implemented_entry_location_matches_real_code -- the single
   most valuable test here: every `status="implemented"` entry's
   `location` is read from the ACTUAL current source file at that exact
   line, and its `value` is compared against what's really there (via
   `ast.literal_eval`, not eyeballing) -- a provenance catalog that
   silently drifts from the real code is worse than no catalog.

2. test_every_research_grounded_entry_citation_is_verbatim_in_research_md
   -- every `provenance_type="research-grounded"` entry's
   `citation_verbatim` is checked as a real string-containment test
   against the actual current text of docs/Research.md, not eyeballed.

3. test_no_provenance_tagged_constant_is_missing_from_the_catalog --
   independently RE-SCANS world/engine.py, world/agents/person.py, and
   world/agents/merchant.py for module-level constants with a nearby
   "MODELING ASSUMPTION"/"RESEARCH-GROUNDED"/"PLACEHOLDER" comment tag
   (case-insensitive), grouping contiguous comment+assignment lines into
   one block so constants that share ONE comment block with an earlier
   sibling (e.g. INCOME_LOGNORMAL_SIGMA sharing MU's comment) are still
   found -- then asserts every constant this scan finds has a catalog
   entry. This is the actual coverage check, not a hardcoded list
   compared against itself.

Run with:
    python -m pytest tests/test_provenance.py -v          (from inside Simulation/)
    python tests/test_provenance.py                        (direct)
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SIM_ROOT = Path(__file__).resolve().parent.parent
if str(SIM_ROOT) not in sys.path:
    sys.path.insert(0, str(SIM_ROOT))

from provenance.catalog import CATALOG, research_grounded  # noqa: E402
RESEARCH_MD_TEXT = (SIM_ROOT / "docs" / "Research.md").read_text(encoding="utf-8")

_TAG_RE = re.compile(r"MODELING ASSUMPTION|RESEARCH-GROUNDED|PLACEHOLDER", re.IGNORECASE)
_LOC_RE = re.compile(r"^([\w./]+\.py):(\d+)")
_CONST_LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*(?::[^=]+)?=\s*(.+)$")


def _read_lines(rel_path: str) -> list[str]:
    return (SIM_ROOT / rel_path).read_text(encoding="utf-8").splitlines()


def _strip_trailing_comment(rhs: str) -> str:
    """Best-effort: cut a trailing '  # ...' comment off a literal's text,
    without breaking literals that legitimately contain '#' (none in this
    codebase's constants -- verified by inspection, not assumed)."""
    if "#" in rhs:
        rhs = rhs.split("#", 1)[0]
    return rhs.strip()


# ---------------------------------------------------------------------------
# Test 1: every IMPLEMENTED entry's location is real, and its value matches.
# ---------------------------------------------------------------------------

# The three IMPLEMENTED entries whose "location" is a real file:line but NOT
# a simple "NAME = literal" module-level assignment (settlement delay is
# structural/implicit; settlement batch hour and event-timestamp range are
# keyword arguments inside a method body, not module-level constants) --
# checked with a hand-written assertion per entry instead of ast.literal_eval.
def _check_settlement_delay() -> None:
    engine_text = (SIM_ROOT / "world" / "engine.py").read_text(encoding="utf-8")
    lines = _read_lines("world/engine.py")
    assert "_run_settlement" in lines[745], f"expected _run_settlement at engine.py:746, got: {lines[745]!r}"
    assert "RESEARCH-GROUNDED, WITH A NAMED SIMPLIFICATION" in engine_text
    assert "takes one to three business days after the transaction" in engine_text


def _check_settlement_batch_hour() -> None:
    lines = _read_lines("world/engine.py")
    assert "hour=3, minute=0, second=0" in lines[805], (
        f"expected 'hour=3, minute=0, second=0' at engine.py:806, got: {lines[805]!r}"
    )


def _check_event_timestamp_range() -> None:
    lines = _read_lines("world/engine.py")
    assert "self.rng.randint(7, 22)" in lines[1226], (
        f"expected 'self.rng.randint(7, 22)' at engine.py:1227, got: {lines[1226]!r}"
    )
    clock_text = (SIM_ROOT / "world" / "clock.py").read_text(encoding="utf-8")
    assert "MODELING ASSUMPTION" in clock_text


_CUSTOM_LOCATION_CHECKS = {
    "SETTLEMENT_DELAY_T_PLUS_1": _check_settlement_delay,
    "SETTLEMENT_BATCH_HOUR_UTC": _check_settlement_batch_hour,
    "EVENT_TIMESTAMP_INTRADAY_HOUR_RANGE": _check_event_timestamp_range,
}


def test_every_implemented_entry_location_matches_real_code():
    implemented = [e for e in CATALOG.values() if e.status == "implemented"]
    assert len(implemented) == 29, f"expected 29 implemented entries, found {len(implemented)}"

    checked = 0
    for entry in implemented:
        if entry.constant_name in _CUSTOM_LOCATION_CHECKS:
            _CUSTOM_LOCATION_CHECKS[entry.constant_name]()
            checked += 1
            continue

        m = _LOC_RE.match(entry.location)
        assert m, f"{entry.constant_name}: location {entry.location!r} is not a parseable 'file.py:line'"
        rel_path, lineno = m.group(1), int(m.group(2))
        full_path = SIM_ROOT / rel_path
        assert full_path.is_file(), f"{entry.constant_name}: {rel_path} does not exist under {SIM_ROOT}"

        lines = _read_lines(rel_path)
        assert 1 <= lineno <= len(lines), (
            f"{entry.constant_name}: {rel_path} has {len(lines)} lines, location claims line {lineno}"
        )
        line = lines[lineno - 1].strip()

        mm = _CONST_LINE_RE.match(line)
        assert mm and mm.group(1) == entry.constant_name, (
            f"{entry.constant_name}: {rel_path}:{lineno} does not read as "
            f"'{entry.constant_name} = ...' -- actual line: {line!r}"
        )
        rhs = _strip_trailing_comment(mm.group(2))
        actual_value = ast.literal_eval(rhs)
        expected_value = ast.literal_eval(entry.value)
        assert actual_value == expected_value, (
            f"{entry.constant_name}: catalog value={entry.value!r} ({expected_value!r}), but "
            f"{rel_path}:{lineno} actually has {rhs!r} ({actual_value!r})"
        )
        checked += 1

    assert checked == len(implemented)
    print(f"test_every_implemented_entry_location_matches_real_code: PASS ({checked} entries checked)")


# ---------------------------------------------------------------------------
# Test 2: every research-grounded entry's citation is verbatim in Research.md
# ---------------------------------------------------------------------------

def test_every_research_grounded_entry_citation_is_verbatim_in_research_md():
    entries = research_grounded()
    assert len(entries) == 10, f"expected 10 research-grounded entries, found {len(entries)}"

    checked = 0
    for entry in entries:
        assert entry.citation_verbatim, f"{entry.constant_name}: research-grounded entry has no citation_verbatim"
        assert entry.citation_verbatim in RESEARCH_MD_TEXT, (
            f"{entry.constant_name}: citation_verbatim {entry.citation_verbatim!r} "
            f"was NOT found verbatim in docs/Research.md"
        )
        checked += 1
    print(
        "test_every_research_grounded_entry_citation_is_verbatim_in_research_md: "
        f"PASS ({checked} entries checked against docs/Research.md, {len(RESEARCH_MD_TEXT)} chars)"
    )


# ---------------------------------------------------------------------------
# Test 3: coverage -- re-scan the real code for tagged constants, independent
# of what was hand-entered into the catalog, and confirm none are missing.
# ---------------------------------------------------------------------------

def _find_tagged_module_level_constants(rel_path: str) -> set[str]:
    """Groups contiguous (no blank-line-separated) runs of comment lines and
    module-level `NAME = ...` assignment lines into blocks; if ANY line in a
    block matches the provenance-tag pattern, every constant assigned in
    that block is considered 'tagged'. This correctly attributes a shared
    leading comment to every sibling constant under it (e.g.
    INCOME_LOGNORMAL_MU/_SIGMA/INCOME_MIN/INCOME_MAX all share one comment
    block; RISK_MULTIPLIER_MIN/_MAX share another), not just the first."""
    lines = _read_lines(rel_path)
    tagged: set[str] = set()

    block_has_tag = False
    block_constants: list[str] = []

    def _flush():
        nonlocal block_has_tag, block_constants
        if block_has_tag:
            tagged.update(block_constants)
        block_has_tag = False
        block_constants = []

    for raw in lines:
        stripped = raw.strip()
        is_comment = stripped.startswith("#")
        m = _CONST_LINE_RE.match(stripped) if not is_comment and raw[:1] not in ("", " ", "\t") else None
        # module-level only: raw must not start with whitespace (excludes
        # class/dataclass fields, function-local assignments).
        if raw[:1] in (" ", "\t"):
            m = None

        if is_comment:
            if _TAG_RE.search(raw):
                block_has_tag = True
            continue
        if m:
            block_constants.append(m.group(1))
            if _TAG_RE.search(raw):  # same-line trailing comment tag
                block_has_tag = True
            continue
        # blank line or unrelated code: block boundary
        _flush()
    _flush()
    return tagged


def test_no_provenance_tagged_constant_is_missing_from_the_catalog():
    scanned: dict[str, set[str]] = {
        "world/engine.py": _find_tagged_module_level_constants("world/engine.py"),
        "world/agents/person.py": _find_tagged_module_level_constants("world/agents/person.py"),
        "world/agents/merchant.py": _find_tagged_module_level_constants("world/agents/merchant.py"),
    }
    all_scanned = set()
    for names in scanned.values():
        all_scanned |= names

    catalog_names = set(CATALOG.keys())
    missing_from_catalog = all_scanned - catalog_names
    assert not missing_from_catalog, (
        f"provenance-tagged constant(s) found in real code but missing from provenance/catalog.py: "
        f"{sorted(missing_from_catalog)}"
    )

    # Sanity: the scan should find a non-trivial, expected-shape set (catches
    # a broken regex silently finding nothing just as much as it catches
    # real omissions).
    assert len(all_scanned) >= 25, f"expected the independent re-scan to find >=25 tagged constants, found {len(all_scanned)}: {sorted(all_scanned)}"

    print(
        "test_no_provenance_tagged_constant_is_missing_from_the_catalog: PASS "
        f"({len(all_scanned)} independently re-scanned tagged constants, all present in the catalog)"
    )
    for rel_path, names in scanned.items():
        print(f"    {rel_path}: {sorted(names)}")


if __name__ == "__main__":
    test_every_implemented_entry_location_matches_real_code()
    test_every_research_grounded_entry_citation_is_verbatim_in_research_md()
    test_no_provenance_tagged_constant_is_missing_from_the_catalog()
    print("\nALL PROVENANCE TESTS PASSED")
