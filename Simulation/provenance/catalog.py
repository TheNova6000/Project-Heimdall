"""
Research provenance catalog -- docs/NORTH_STAR.md Section 34 ("Systemic
Change #25 -- Create a Research Provenance System") and Section 40 ("The
First Proof of the New Architecture", whose shared-substrate list names
"provenance" and "research layer" explicitly), implemented at a bounded,
honest scale for Project Truman (Simulation/): a structured, queryable
index of every behavioral constant's provenance, extracted from what is
ALREADY documented in the running code (inline "MODELING ASSUMPTION" /
"RESEARCH-GROUNDED" / "PLACEHOLDER" comments, per Simulation/docs/Rules.md
#2) and in Simulation/docs/Research.md / Memory.md -- not new research, not
new provenance claims, a consolidation and formalization of what is
already true in the codebase.

WHAT THIS IS: one `ProvenanceEntry` per constant --
  - 28 entries with `status="implemented"`: every constant this catalog's
    own author found by grepping "MODELING ASSUMPTION"/"RESEARCH-GROUNDED"/
    "PLACEHOLDER" (case-insensitive, close variants) across
    Simulation/world/*.py and Simulation/world/agents/*.py, cross-checked
    against Research.md/Memory.md.
  - 14 entries with `status="proposed"`: every provenance-labeled rule from
    Research.md Part C's three NOT-implemented domain proposals (fraud,
    credit, loan) -- matching financial_system/bridges/registry.py's
    BRIDGED/BLOCKED "real vs. not-yet-real" distinction, applied here to
    "implemented vs. proposed" instead.

Every `status="implemented"` entry's `location` is a real file:line
(relative to this Simulation/ directory), cross-checked by
tests/test_provenance.py against the actual current source -- not
memorized from an old commit, not eyeballed. Every `research-grounded`
entry's `citation_verbatim` is a short, exact substring, independently
verified by the same test file to appear character-for-character
somewhere in Simulation/docs/Research.md.

WHAT THIS IS NOT (same disclaimer style as financial_system/bridges/
registry.py's module docstring, because this project holds itself to the
same standard here): not machine learning, not autonomous discovery, and
not a linter that scans new code for undocumented constants going
forward. This is a snapshot, hand-built by reading the real code and the
real docs once, as of VERIFIED_AT_COMMIT below. It does NOT detect a new
"MODELING ASSUMPTION"-style comment added to world/ after that commit --
a real, stated limitation, not silently glossed over (see this package's
README).

Vocabulary: exactly the three real categories Rules.md #2 actually uses --
`research-grounded` / `modeling-assumption` / `placeholder` -- NOT
NORTH_STAR.md's fuller seven-way vocabulary (EMPIRICALLY OBSERVED /
RESEARCH SUPPORTED / CALIBRATED / INFERRED / PLAUSIBLE / ASSUMED /
HYPOTHETICAL, Section 37's "Formalization Requirements"). That fuller
vocabulary was deliberately NOT adopted here: mapping this project's real
three-way labels onto it cleanly would require guessing, for every single
"MODELING ASSUMPTION" comment, whether it "really" means CALIBRATED vs.
INFERRED vs. PLAUSIBLE vs. ASSUMED -- a judgment call neither Research.md
nor Rules.md ever made, and one this catalog has no honest basis to make
on their behalf after the fact. Same design decision, same reasoning, as
registry.py's own BRIDGED/BLOCKED-only vocabulary in preference to Section
28's five-way SUPPORTED/PARTIAL/UNKNOWN/MISSING/UNVERIFIED (see that
module's docstring) -- this catalog follows that precedent deliberately.

Existing Simulation/ behavior is UNCHANGED by this module. Nothing in
world/*.py or world/agents/*.py is imported for its control flow or
modified; this module only records, in prose, what those files' own
comments and Simulation/docs/ already say.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# The commit this catalog's file:line locations and citation excerpts were
# verified against by reading the actual current source named below -- not
# a fabricated timestamp. Update by hand (with a fresh `git rev-parse HEAD`)
# only when the underlying constants/comments this catalog describes
# actually change. Same discipline as registry.py's VERIFIED_AT_COMMIT.
VERIFIED_AT_COMMIT = "532b1400ed8d92fc5a7150c81f39be1bb4502274"

ProvenanceType = Literal["research-grounded", "modeling-assumption", "placeholder"]
Status = Literal["implemented", "proposed"]


@dataclass(frozen=True)
class ProvenanceEntry:
    """One catalog entry. Every field here is something a real reader could
    check against real code or real docs -- nothing is aspirational."""

    constant_name: str
    location: str  # file:line or file:function, relative to Simulation/
    value: str  # the actual current value, as a string (or, for a
    # `status="proposed"` entry, a plain statement that no value exists yet)
    provenance_type: ProvenanceType
    status: Status  # "implemented" (real code today) or "proposed"
    # (Research.md Part C design only, NOT built -- financial_system/
    # bridges/registry.py's BLOCKED domains for fraud/credit/loan are the
    # reason these can never become "implemented" without a dedicated,
    # reviewed effort; see registry.py's own blocked_reason text)

    # For research-grounded: the exact citation from Research.md (title,
    # author/publication, date, URL where Research.md has one). For
    # modeling-assumption: the justification already given in the code
    # comment or Memory.md. For placeholder: says so plainly.
    source: str

    # research-grounded entries only: a short, exact substring of `source`
    # (or of the underlying Research.md passage) that
    # tests/test_provenance.py independently verifies is present,
    # character-for-character, somewhere in Simulation/docs/Research.md.
    # Kept separate from `source` (which is the fuller, human-readable
    # citation) so the automated check has one unambiguous string to look
    # for rather than parsing prose.
    citation_verbatim: Optional[str] = None

    # Research-grounded entries only, where applicable: an already-
    # documented caveat on the citation's reliability, reused verbatim
    # from Research.md (e.g. "WebSearch-synthesized, not independently
    # text-verified") -- never invented fresh here.
    confidence_note: Optional[str] = None

    # Optional, only where real: Research.md documents specific real-world
    # numbers that were found, considered, and explicitly NOT adopted.
    # Captured here as a "considered and rejected" note.
    rejected_alternatives: Optional[str] = None

    # Free-text: anything else worth recording honestly (e.g. a documented
    # sanity-check that isn't itself a citation, a cross-reference to a
    # related entry, a scope caveat already stated in the source material).
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if self.provenance_type not in ("research-grounded", "modeling-assumption", "placeholder"):
            raise ValueError(
                f"{self.constant_name}: provenance_type must be one of research-grounded/"
                f"modeling-assumption/placeholder, got {self.provenance_type!r}"
            )
        if self.status not in ("implemented", "proposed"):
            raise ValueError(f"{self.constant_name}: status must be implemented or proposed, got {self.status!r}")
        if not self.source:
            raise ValueError(f"{self.constant_name}: source must not be empty")
        if not self.location:
            raise ValueError(f"{self.constant_name}: location must not be empty")
        if not self.value:
            raise ValueError(f"{self.constant_name}: value must not be empty")
        if self.provenance_type == "research-grounded" and not self.citation_verbatim:
            raise ValueError(f"{self.constant_name}: research-grounded entries must set citation_verbatim")
        if self.provenance_type != "research-grounded" and self.citation_verbatim:
            raise ValueError(f"{self.constant_name}: citation_verbatim is only valid on research-grounded entries")
        if self.provenance_type == "placeholder":
            low = self.source.lower()
            if "placeholder" not in low and "no citation" not in low and "no source" not in low:
                raise ValueError(
                    f"{self.constant_name}: placeholder entries must plainly say so in `source` "
                    f"(Rules.md #2: 'explicitly marked TODO, not left silently looking authoritative')"
                )


# The catalog itself -- a plain dict, constant_name -> ProvenanceEntry. Not
# a database, not persisted, not self-updating: rebuilt by importing this
# module, exactly like financial_system/bridges/registry.py's DOMAIN_REGISTRY.
CATALOG: dict[str, ProvenanceEntry] = {}


def register(entry: ProvenanceEntry, *, replace: bool = False) -> ProvenanceEntry:
    """Register one catalog entry. Refuses a silent overwrite of an
    existing name unless replace=True, so a copy-paste typo can't quietly
    clobber an existing entry -- same guard as registry.py's register_domain()."""
    if entry.constant_name in CATALOG and not replace:
        raise ValueError(
            f"constant {entry.constant_name!r} is already registered "
            f"(pass replace=True to intentionally overwrite it)"
        )
    CATALOG[entry.constant_name] = entry
    return entry


def get(constant_name: str) -> ProvenanceEntry:
    return CATALOG[constant_name]


def all_entries() -> list[ProvenanceEntry]:
    return list(CATALOG.values())


def by_provenance_type(provenance_type: ProvenanceType) -> list[ProvenanceEntry]:
    return [e for e in CATALOG.values() if e.provenance_type == provenance_type]


def by_status(status: Status) -> list[ProvenanceEntry]:
    return [e for e in CATALOG.values() if e.status == status]


def research_grounded() -> list[ProvenanceEntry]:
    return by_provenance_type("research-grounded")


def modeling_assumptions() -> list[ProvenanceEntry]:
    return by_provenance_type("modeling-assumption")


def placeholders() -> list[ProvenanceEntry]:
    return by_provenance_type("placeholder")


def implemented() -> list[ProvenanceEntry]:
    return by_status("implemented")


def proposed() -> list[ProvenanceEntry]:
    return by_status("proposed")


def with_rejected_alternatives() -> list[ProvenanceEntry]:
    return [e for e in CATALOG.values() if e.rejected_alternatives]


# =============================================================================
# IMPLEMENTED constants (28) -- real code today, Simulation/world/*.py and
# Simulation/world/agents/*.py, at VERIFIED_AT_COMMIT.
# =============================================================================

# --- world/engine.py: population-generation constants ----------------------

register(ProvenanceEntry(
    constant_name="INCOME_LOGNORMAL_MU",
    location="world/engine.py:65",
    value="8.3",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 57-64 (code comment): 'MODELING ASSUMPTION, informally grounded in the "
        "standard stylized fact in income-distribution economics that individual incomes are approximately "
        "log-normally distributed (e.g. Aitchison & Brown, \"The Lognormal Distribution\", 1957) -- used here "
        "for its right-skewed *shape* only ... NOT calibrated against any real income dataset or currency, "
        "per Rules.md #3 (no external data) and #5 (don't overclaim). mu/sigma chosen so monthly incomes "
        "mostly fall in a plausible few-hundred-to-few-thousand-unit range.' Memory.md's Phase 1 provenance "
        "table records the same rule as 'Modeling assumption, informally motivated by the standard stylized "
        "fact that incomes are approximately log-normal (Aitchison & Brown 1957) -- shape only, not "
        "calibrated to any dataset.'"
    ),
    notes=(
        "Research.md Part A §1 independently corroborates the log-normal *shape* choice across three "
        "sources (arXiv:1602.06234, a ScienceDirect Pareto-lognormal paper, Schield 2018) but explicitly "
        "does NOT upgrade this constant's provenance label to research-grounded, because Research.md's own "
        "task brief authorized code changes only for the shape-vs-tail *finding*, not a citation-dressing "
        "of mu specifically -- mu itself (as opposed to sigma, see INCOME_LOGNORMAL_SIGMA) has no numeric "
        "candidate from Part A at all. Research.md: 'What the current code does NOT capture ... real income "
        "distributions are NOT log-normal in the tail -- the simulation's hard-clamped INCOME_MAX=25000.0 "
        "actually sidesteps this by construction ... This is reported as a genuine finding, not acted on: "
        "capping is already the practical fix a Pareto tail would have motivated, so no code change follows "
        "from this item.'"
    ),
))

register(ProvenanceEntry(
    constant_name="INCOME_LOGNORMAL_SIGMA",
    location="world/engine.py:66",
    value="0.5",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "Same code comment as INCOME_LOGNORMAL_MU (world/engine.py lines 57-64) -- shape-only log-normal "
        "motivation, mu/sigma chosen jointly, not independently calibrated."
    ),
    rejected_alternatives=(
        "Research.md Part A §1: a WebSearch turned up a claim (via a wage-inequality paper's abstract "
        "summary, NBER Working Paper w28375, 'Labor Market Institutions and the Distribution of Wages') that "
        "'the average standard deviation of log wages within states is close to 0.5' using U.S. CPS data -- "
        "coinciding almost exactly with this constant's existing value. Research.md: 'This was deliberately "
        "NOT used to upgrade the code's provenance label, for two honest reasons: (1) the NBER PDF could not "
        "be independently re-verified by this session's tooling ... the 0.5 figure is a WebSearch-"
        "synthesized paraphrase of a paper this session never actually read in full, not a firsthand-"
        "verified quote; (2) even if verified, that estimate is for *wage* dispersion (hourly earnings for "
        "employed workers), not *income* including all sources across an entire adult population ... a real "
        "but non-trivial mapping gap.' Research.md's own summary calls this 'the sigma≈0.5 coincidence' "
        "explicitly, listed alongside the DCPC zero-payment-day statistic as one of the tempting-but-"
        "rejected numbers (Research.md's closing 'Honest overall summary')."
    ),
    confidence_note=(
        "The rejected NBER figure itself is flagged in Research.md as 'a WebSearch-synthesized paraphrase "
        "... not a firsthand-verified quote' -- this is exactly why it was not adopted, not a caveat on the "
        "currently-implemented value (which carries no research citation at all, rejected or otherwise)."
    ),
))

register(ProvenanceEntry(
    constant_name="INCOME_MIN",
    location="world/engine.py:67",
    value="300.0",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 57-64 (shared comment block with INCOME_LOGNORMAL_MU/SIGMA/INCOME_MAX)."
    ),
    notes=(
        "Research.md Part B, explaining why this was left unchanged: 'INCOME_MIN/INCOME_MAX also have no "
        "clean real-world anchor since the simulation's income unit isn't tied to any real currency/scale "
        "(a fact the existing code comment already states correctly) -- there's no honest way to "
        "\"calibrate\" an absolute income level to USD Census figures without implicitly picking a currency "
        "scale nobody asked this project to commit to.'"
    ),
))

register(ProvenanceEntry(
    constant_name="INCOME_MAX",
    location="world/engine.py:68",
    value="25000.0",
    provenance_type="modeling-assumption",
    status="implemented",
    source="world/engine.py lines 57-64 (shared comment block with INCOME_LOGNORMAL_MU/SIGMA/INCOME_MIN).",
    notes=(
        "Research.md Part A §1 notes this hard clamp has an accidental upside: 'the simulation's hard-"
        "clamped INCOME_MAX = 25000.0 actually sidesteps [the log-normal's under-fat tail problem] by "
        "construction (it prevents the log-normal's under-fat tail from mattering, since nothing can exceed "
        "the cap anyway), which is an honest, if accidental, way the simplification avoids its main known "
        "flaw.' Same currency-scale caveat as INCOME_MIN applies; no code change followed."
    ),
))

register(ProvenanceEntry(
    constant_name="OPENING_BALANCE_FRACTION_RANGE",
    location="world/engine.py:74",
    value="(0.1, 1.0)",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 70-73: 'MODELING ASSUMPTION: a person's opening balance is a random fraction "
        "(10%-100%) of their own monthly income -- i.e. everyone starts with somewhere between a few days' "
        "and a full month's income already banked. Arbitrary but named starting condition, not derived from "
        "data.'"
    ),
    notes=(
        "Research.md Part B reports a real, directly-fetched, but non-substitutable finding here: the Fed's "
        "SHED survey (63% of adults could cover a $400 emergency expense with cash/equivalent; 55% report "
        "having a 3-month emergency fund) is 'broadly *consistent* with the current uniform 10%-100%-of-"
        "monthly-income range ... but these are point-in-time adequacy statistics, not a distributional "
        "shape or range for \"opening balance as a fraction of monthly income\", so there's no clean number "
        "to substitute in for the uniform range itself. Left unchanged; the consistency is reported as a "
        "mild positive sanity check, not a citation-backed replacement.' Deliberately NOT upgraded to "
        "research-grounded for exactly that reason -- a consistency check is not a citation."
    ),
))

register(ProvenanceEntry(
    constant_name="RISK_PREFERENCE_RANGE",
    location="world/engine.py:80",
    value="(0.0, 1.0)",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 76-79: 'MODELING ASSUMPTION: risk_preference is drawn uniformly over [0, 1] "
        "-- no claim that real risk preferences are uniformly distributed across a population; uniform is "
        "the least-assumption-laden choice available for a trait Architecture.md defines but does not "
        "specify a distribution for.'"
    ),
))

register(ProvenanceEntry(
    constant_name="PAYDAY_RANGE",
    location="world/engine.py:86",
    value="(1, 28)",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 82-86: 'MODELING ASSUMPTION: payday is a person's own fixed day-of-month, "
        "drawn uniformly from 1-28 (28 chosen, not 31, so \"payday\" is always a valid date in every month "
        "including February -- an implementation constraint, not a behavioral claim).'"
    ),
    notes=(
        "world/agents/person.py's Person dataclass field comment (around line 97) restates the same rule's "
        "intent ('each person has their own payday so income arrivals are staggered ... MODELING "
        "ASSUMPTION: makes \"not everyone is paid on the 1st\" explicit rather than accidental') -- treated "
        "here as the same rule, not a second constant, since it carries no independent numeric value."
    ),
))

register(ProvenanceEntry(
    constant_name="SAVINGS_SWEEP_FRACTION",
    location="world/engine.py:112",
    value="0.15",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 102-111: 'MODELING ASSUMPTION: a fixed 15% of every salary payment is swept "
        "into the person's own savings account ... Loosely motivated by the common personal-finance rule of "
        "thumb \"save roughly 15-20% of income\" (e.g. the well-known \"50/30/20\" budgeting guideline "
        "popularized by Elizabeth Warren's \"All Your Worth\", 2005) as a defensible, memorable round number "
        "-- this was NOT independently verified against real household savings-rate data for this task ... "
        "so it stays a named MODELING ASSUMPTION, not a citation dressed up as research-grounded.' Memory.md "
        "A.1 repeats this verbatim."
    ),
    notes=(
        "This is a deliberate near-miss case: a real, named popular-finance guideline is cited as loose "
        "motivation, but explicitly NOT treated as a research citation -- the code comment itself draws this "
        "line, which is why this entry stays modeling-assumption rather than research-grounded."
    ),
))

register(ProvenanceEntry(
    constant_name="HOUSEHOLD_SWEEP_FRACTION",
    location="world/engine.py:127",
    value="0.10",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 114-127: 'MODELING ASSUMPTION: a further fixed 10% of every salary payment "
        "is swept into the person's household's shared account ... Chosen smaller than the savings fraction "
        "because household pooling is modeled as a secondary behavior layered on top of a person's own "
        "saving, not a replacement for it.' Memory.md A.2 repeats this."
    ),
))

register(ProvenanceEntry(
    constant_name="HOUSEHOLD_SIZE_WEIGHTS",
    location="world/engine.py:137",
    value="{1: 0.30, 2: 0.35, 3: 0.20, 4: 0.15}",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 129-136: 'MODELING ASSUMPTION: household size is drawn from a simple, named "
        "discrete distribution weighted toward small households (1-4 persons). This task's brief permitted "
        "an OPTIONAL bounded WebSearch for real household-size-distribution stats to justify this instead; "
        "that search was not done in this session (judged not worth the scope for a purely structural, "
        "behaviorally-inert-beyond-the-sweep grouping) -- these weights are deliberately labeled an honest, "
        "uncited assumption, not dressed up as research-grounded. Round numbers, not fit to any dataset.' "
        "Memory.md A.2 repeats this and notes the bounded search remains available to a future session."
    ),
))

register(ProvenanceEntry(
    constant_name="ORG_MEMBERSHIP_FRACTION",
    location="world/engine.py:145",
    value="0.5",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 139-144: 'MODELING ASSUMPTION: roughly half the population is employed by a "
        "modeled Organization ... 0.5 is a round, defensible split chosen so BOTH salary-payment code paths "
        "are meaningfully exercised in every run, not because real employment-by-organization-size data was "
        "consulted.' Memory.md A.3 repeats this."
    ),
))

register(ProvenanceEntry(
    constant_name="ORG_TARGET_SIZE",
    location="world/engine.py:150",
    value="25",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 147-149: 'MODELING ASSUMPTION: target average employees per Organization, "
        "used only to decide how many Organizations to create ... An arbitrary, named round number, not "
        "derived from real firm-size data.' Memory.md A.3 repeats this."
    ),
))

register(ProvenanceEntry(
    constant_name="ORG_FUNDING_SAFETY_MULTIPLIER",
    location="world/engine.py:164",
    value="1.2",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 152-163: 'MODELING ASSUMPTION: each Organization's revenue account is funded "
        "ONCE ... with a buffer sized to comfortably cover that org's own full-run payroll ... times this "
        "safety multiplier -- a deliberate choice to fund generously so payroll failure is RARE in a "
        "typical run, NOT to structurally prevent it.' Memory.md A.3: buffer = (sum of employees' monthly "
        "income) x (num_days/30) x 1.2, i.e. full-run payroll plus a 20% margin, chosen so failure stays "
        "possible, not impossible."
    ),
))

register(ProvenanceEntry(
    constant_name="NUM_COMMUNITIES",
    location="world/engine.py:172",
    value="5",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 166-172: 'MODELING ASSUMPTION: households and organizations are grouped into "
        "a small, fixed number of named \"communities\" purely for future aggregate reporting -- Community "
        "has NO money-movement mechanic of its own ... 5 is an arbitrary round number, not derived from any "
        "real geographic/community-size data.' Memory.md A.4 repeats this and documents Community as "
        "deliberately, provenly inert (no community_id ever appears as a Transaction/Event subject in real "
        "output, per tests/test_phase25.py)."
    ),
))

register(ProvenanceEntry(
    constant_name="DEVICE_HOUSEHOLD_SHARING_FRACTION",
    location="world/engine.py:203",
    value="0.3",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 185-202: 'MODELING ASSUMPTION: for each household with 2+ members ... Every "
        "OTHER member of that household independently has a 30% chance of transacting from that same shared "
        "primary device instead of getting their own personal device. Chosen as a defensible minority-but-"
        "substantial fraction ... This is NOT derived from any real device-sharing survey (that would need "
        "its own dedicated research pass, out of this task's scope) -- named honestly as an uncited "
        "assumption, same style as ORG_MEMBERSHIP_FRACTION/SAVINGS_SWEEP_FRACTION above.' Memory.md's "
        "'Device' section repeats this in full."
    ),
    notes=(
        "Tested empirically, not just asserted: tests/test_device.py reconciles the ACTUAL observed sharing "
        "fraction over a 2000-person run against this constant within a +/-0.05 statistical tolerance band "
        "(Memory.md's Device section) -- a Bernoulli-draw check, looser than the Phase 2.5 sweep fractions' "
        "exact-arithmetic <0.001 bound, and the Memory.md text explains why."
    ),
))

register(ProvenanceEntry(
    constant_name="SETTLEMENT_DELAY_T_PLUS_1",
    location="world/engine.py:638 (SimulationEngine._run_settlement; the T+1 delay is implicit in the "
    "method's full-daily-sweep ordering -- not a standalone named numeric constant)",
    value="1 simulated day (T+1) -- structural, from _run_one_day() calling _run_settlement() once per "
    "tick before that day's purchases can add anything new to a pending account",
    provenance_type="research-grounded",
    status="implemented",
    source=(
        "world/engine.py's _run_settlement docstring (lines 643-674), Phase 3 update per Research.md Part B: "
        "'RESEARCH-GROUNDED, WITH A NAMED SIMPLIFICATION ... Real card-network settlement is consistently "
        "reported, across multiple independent industry sources, to take on the order of one to three "
        "business days after a transaction: Stripe's own public documentation states \"settlement typically "
        "takes one to three business days after the transaction\" for card payments (Stripe, \"Payment "
        "settlement explained: how it works and how long it takes\", stripe.com/resources/more/payment-"
        "settlement-explained-how-it-works-and-how-long-it-takes, accessed 2026), and multiple payments-"
        "industry processor explainers (e.g. Clearly Payments, \"How Long Do Credit Card Payments Take to "
        "Settle?\", clearlypayments.com) independently report the same 1-3 business day window.'"
    ),
    citation_verbatim="typically takes one to three business days after the transaction,",
    confidence_note=(
        "The docstring itself draws the exact same line this catalog's vocabulary decision draws: 'That "
        "range is what grounds \"not instant, on the order of a day or more\" as a real fact about card "
        "settlement, not an invented one. The SPECIFIC choice of exactly T+1 (the low/fastest end of that "
        "range, applied uniformly with no variation) remains a named MODELING ASSUMPTION, not itself "
        "research-derived: no source above says every merchant settles in exactly 1 day.' Cataloged as "
        "research-grounded overall (matching the docstring's own top-level label) with this qualitative-"
        "vs-specific-value distinction preserved here rather than silently dropped."
    ),
    notes=(
        "This is Research.md Part B's ONE actual code change (docstring-only, zero constant-value change, "
        "zero behavioral change) -- see Research.md's 'Changed: settlement-delay provenance (not the "
        "value)' section and Memory.md's Phase 3 section. Before Phase 3: bare 'MODELING ASSUMPTION'. "
        "Value was NOT widened to a random 1-3 day draw specifically to avoid perturbing the RNG draw "
        "sequence for purchases/salary (Phase 2's own protection, restated in the docstring)."
    ),
))

register(ProvenanceEntry(
    constant_name="SETTLEMENT_BATCH_HOUR_UTC",
    location="world/engine.py:698 (self.clock.timestamp(hour=3, minute=0, second=0), inside "
    "_run_settlement; not a standalone module-level constant)",
    value="hour=3, minute=0, second=0 (03:00 UTC)",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py's _run_settlement docstring (lines 684-689): 'A fixed batch time (03:00 UTC), not "
        "RNG-sampled: settlement is a systemic process run once a day, not an individual agent's "
        "probabilistic decision (contrast _event_timestamp() below), so this draws no randomness and cannot "
        "itself be a source of nondeterminism.' Memory.md's Phase 2 provenance table: 'Settlement batch "
        "time | Fixed 03:00 UTC, not RNG-sampled | Modeling assumption -- settlement is a systemic batch "
        "process, not an individual agent's probabilistic decision, so it is modeled as deterministic and "
        "RNG-free, unlike per-person event timestamps.'"
    ),
))

register(ProvenanceEntry(
    constant_name="EVENT_TIMESTAMP_INTRADAY_HOUR_RANGE",
    location="world/engine.py:1049-1056 (SimulationEngine._event_timestamp; hour=self.rng.randint(7, 22)); "
    "design-level statement of the same rule in world/clock.py:36-44 (SimClock.timestamp docstring)",
    value="hour uniform in [7, 22], minute uniform in [0, 59]",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/engine.py lines 1049-1055: 'MODELING ASSUMPTION: intraday time-of-day is sampled uniformly "
        "across a plausible \"awake\" window (7am-10pm UTC) purely so that multiple same-day events don't "
        "all share one identical timestamp. No claim is made about real payment-timing patterns (that is "
        "explicitly out of scope -- Phases.md Phase 4 territory). Drawn from the run's single seeded RNG, so "
        "still fully deterministic.' world/clock.py lines 36-44 states the same design-level point: 'Phase "
        "1's loop is per-day, not per-second ... so there is no real intraday clock to sample from ... this "
        "file makes no claim about *when during the day* things happen, only about which simulated day they "
        "happen on.' Memory.md's Phase 1 provenance table: 'Event time-of-day | uniform in [7:00, 22:59] "
        "UTC | Modeling assumption -- exists only so same-day events get distinct timestamps; no claim about "
        "real payment timing.'"
    ),
))

# --- world/agents/person.py --------------------------------------------------

register(ProvenanceEntry(
    constant_name="INCOME_NOISE_RANGE",
    location="world/agents/person.py:34",
    value="(0.95, 1.05)",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/agents/person.py line 34 (inline comment): 'MODELING ASSUMPTION: paychecks vary +/-5% around "
        "the nominal monthly figure (bonuses/deductions/rounding) -- a named simplification, not a cited "
        "payroll statistic.' Memory.md's Phase 1 provenance table: 'Income noise | +/-5% of nominal monthly "
        "income | Modeling assumption -- named simplification, not a payroll statistic.'"
    ),
))

register(ProvenanceEntry(
    constant_name="BASE_DAILY_SPEND_PROB",
    location="world/agents/person.py:48",
    value="0.35",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/agents/person.py lines 42-47: 'MODELING ASSUMPTION: base daily probability that a person "
        "even considers making a discretionary purchase today, before any balance/risk adjustment. 0.35 => "
        "roughly one purchase attempt every ~3 days per person on average, a plausible order of magnitude "
        "for routine daily-life spending ... Not derived from any transaction-frequency dataset -- Phase 3 "
        "candidate.'"
    ),
    rejected_alternatives=(
        "Research.md Part B: 'the Federal Reserve's Diary of Consumer Payment Choice (an annual, well-"
        "established public survey) was the most promising lead -- search results referenced a reported "
        "statistic that roughly half of consumers make zero payments on a given diary day (implying ~50% "
        "\"at least one payment today\", which would suggest a meaningfully higher base rate than 0.35). "
        "This was not adopted, for two honest reasons: (1) this session's WebFetch could not successfully "
        "retrieve or verify that number against any primary DCPC report PDF or HTML page despite several "
        "attempts (all DCPC PDFs returned unparseable binary content, and no HTML page found stated the "
        "figure directly) -- it exists only as an unverified WebSearch synthesis ...; (2) even if verified, "
        "DCPC counts ALL payments (bills, rent, transfers, recurring debits), while BASE_DAILY_SPEND_PROB "
        "specifically models a *discretionary* purchase attempt -- a materially narrower category than \"any "
        "payment\", so the two numbers aren't measuring the same thing even setting aside the verification "
        "problem.' Explicitly named in Research.md's closing summary as 'the DCPC zero-payment-day "
        "statistic', the second of the two headline considered-and-rejected numbers."
    ),
    confidence_note=(
        "The rejected DCPC figure is explicitly flagged in Research.md as existing 'only as an unverified "
        "WebSearch synthesis, which is too thin to act on for a code change (documented as thin per Rules.md "
        "#5, not treated as a citation)' -- again a caveat on the REJECTED alternative, not on the "
        "implemented value, which carries no citation of its own."
    ),
))

register(ProvenanceEntry(
    constant_name="RISK_MULTIPLIER_MIN",
    location="world/agents/person.py:55",
    value="0.7",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/agents/person.py lines 50-54: 'MODELING ASSUMPTION: risk_preference (Architecture.md's "
        "stated 0-1 Person trait) linearly scales spend probability between 0.7x (very cautious, "
        "risk_preference=0) and 1.6x (very impulsive, risk_preference=1). The specific multiplier range is "
        "a named, reasonable-looking choice, not an empirically fit elasticity -- Phase 3 candidate.'"
    ),
))

register(ProvenanceEntry(
    constant_name="RISK_MULTIPLIER_MAX",
    location="world/agents/person.py:56",
    value="1.6",
    provenance_type="modeling-assumption",
    status="implemented",
    source="world/agents/person.py lines 50-54 (shared comment block with RISK_MULTIPLIER_MIN).",
))

register(ProvenanceEntry(
    constant_name="BALANCE_FACTOR_MIN",
    location="world/agents/person.py:67",
    value="0.5",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/agents/person.py lines 58-66: 'MODELING ASSUMPTION: a person's balance relative to their own "
        "monthly income scales spend probability down when they are cash-strapped, but deliberately never "
        "to zero -- people still attempt purchases (rent, groceries) even when low on funds, which is "
        "exactly the situation that should sometimes produce a payment_failure. balance_ratio=0 (broke) -> "
        "0.5x; balance_ratio>=1 (at least a full month's income banked) -> 1.0x.'"
    ),
    notes=(
        "This is the specific mechanism connecting a Person's own visible state to their own behavior, per "
        "Architecture.md's simulation-loop requirement -- also the load-bearing constant behind this "
        "project's headline finding (README.md: monotonic balance/income-ratio -> failure-rate relationship)."
    ),
))

register(ProvenanceEntry(
    constant_name="BALANCE_FACTOR_SATURATION_RATIO",
    location="world/agents/person.py:68",
    value="1.0",
    provenance_type="modeling-assumption",
    status="implemented",
    source="world/agents/person.py lines 58-66 (shared comment block with BALANCE_FACTOR_MIN).",
))

register(ProvenanceEntry(
    constant_name="MAX_DAILY_SPEND_PROB",
    location="world/agents/person.py:73",
    value="0.9",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/agents/person.py lines 70-72: 'MODELING ASSUMPTION: cap on daily spend probability regardless "
        "of how favorable balance/risk look, so no person is deterministic. Arbitrary but stated cap, not "
        "derived from data.'"
    ),
))

register(ProvenanceEntry(
    constant_name="PURCHASE_FRACTION_RANGE",
    location="world/agents/person.py:80",
    value="(0.005, 0.12)",
    provenance_type="modeling-assumption",
    status="implemented",
    source=(
        "world/agents/person.py lines 75-79: 'MODELING ASSUMPTION: a discretionary purchase is sized as a "
        "fraction of the person's own monthly income, drawn from a wide range (0.5%-12% of income) and then "
        "jittered multiplicatively, to get a right-skewed spread (many small purchases, occasional larger "
        "ones) without claiming to match any real merchant-spend distribution. Phase 3 candidate.'"
    ),
    notes=(
        "Research.md Part A §1 reports a real, well-supported, NOT-acted-on finding directly against this "
        "constant's fixed-fraction design: BLS Consumer Expenditure Survey data shows spend/income ratio is "
        "'not flat across income levels' -- poorer people spend a LARGER share of income, not the same share "
        "-- but 'fixing it honestly would mean making purchase-amount-as-a-fraction-of-income itself a "
        "function of income level (a new behavioral mechanism), not swapping a single constant for another "
        "constant, which is outside this task's explicitly narrow Part B scope ... Recorded here as an "
        "honest, actionable finding for a future, properly-scoped Phase 3 continuation, not acted on now.' "
        "Not treated as a 'rejected alternative' in the sigma/DCPC sense (no specific replacement NUMBER was "
        "found and rejected here) -- it's a structural-mechanism gap, recorded as a note rather than a "
        "rejected numeric alternative."
    ),
))

register(ProvenanceEntry(
    constant_name="PURCHASE_FRACTION_JITTER",
    location="world/agents/person.py:81",
    value="(0.6, 1.6)",
    provenance_type="modeling-assumption",
    status="implemented",
    source="world/agents/person.py lines 75-79 (shared comment block with PURCHASE_FRACTION_RANGE).",
))

# --- world/agents/merchant.py -------------------------------------------------

register(ProvenanceEntry(
    constant_name="MERCHANT_CATEGORIES",
    location="world/agents/merchant.py:28",
    value='("groceries", "transport", "utilities", "retail", "dining")',
    provenance_type="placeholder",
    status="implemented",
    source=(
        "world/agents/merchant.py lines 23-27: 'PLACEHOLDER: category is a cosmetic label only (does not "
        "affect any probability or behavior in Phase 1) used purely so stats/report.py and the output CSVs "
        "have something more legible than an opaque merchant_id to group by. Not research-grounded, not "
        "claimed to reflect any real merchant-category mix -- swap or extend freely.' Memory.md's Phase 1 "
        "provenance table: 'Merchant category | uniform random pick from a fixed 5-item list | Placeholder "
        "-- cosmetic label only, no behavioral effect.'"
    ),
    notes=(
        "Research.md Part C.1 (fraud proposal) notes this would be 'the first mechanism that actually uses "
        "it behaviorally' if a Merchant-category-linked fraud-risk multiplier were ever built -- see the "
        "proposed FRAUD_MERCHANT_CATEGORY_LINK note under status=proposed entries; not itself a separate "
        "catalog entry since Research.md never assigns it its own value or provenance label distinct from "
        "this one."
    ),
))


# =============================================================================
# PROPOSED constants (14) -- Research.md Part C's design-only fraud/credit/
# loan proposals. NOT implemented -- matches financial_system/bridges/
# registry.py's BLOCKED status for these same three domains.
# =============================================================================

# --- C.1 Fraud (Research.md Part C.1) ---------------------------------------

register(ProvenanceEntry(
    constant_name="FRAUD_PERSON_FRAUD_PROPENSITY",
    location="not implemented -- proposed field Person.fraud_propensity, Research.md Part C.1",
    value="not implemented -- no value exists in code; proposed as a hidden 0-1-ish trait, shape unspecified",
    provenance_type="modeling-assumption",
    status="proposed",
    source=(
        "Research.md Part C.1: 'a hidden fraud_propensity trait (not visible to any decision logic the way "
        "risk_preference is, otherwise it would leak into spend-probability decisions and defeat the point "
        "of a fraud signal being *detectable from behavior*, not given away for free) -- MODELING ASSUMPTION "
        "for its existence/shape (there is no cited distribution for \"how fraud-prone is a given person,\" "
        "because fraud is mostly not initiated by the legitimate account holder in the first place -- see "
        "below).'"
    ),
))

register(ProvenanceEntry(
    constant_name="FRAUD_COMPROMISE_EVENT_DAILY_PROBABILITY",
    location="not implemented -- proposed per-account-per-day 'compromise event' probability, Research.md "
    "Part C.1 item 1",
    value="not implemented -- no value exists; Research.md explicitly declines to propose one",
    provenance_type="placeholder",
    status="proposed",
    source=(
        "Research.md Part C.1, event-generation logic item 1: 'Each day, a small, low, per-account "
        "probability of a \"compromise event\" starting (PLACEHOLDER -- no source found gives a real "
        "per-account-per-day compromise probability; this would need to be picked and explicitly marked as "
        "a placeholder pending better data, not invented and presented as calibrated).'"
    ),
))

register(ProvenanceEntry(
    constant_name="FRAUD_SIGNAL_CHOICE_VELOCITY_AND_AMOUNT_ANOMALY",
    location="not implemented -- proposed signal choice for fraud_attempt generation, Research.md Part C.1 "
    "item 2",
    value="not implemented -- qualitative signal choice, no numeric constant proposed",
    provenance_type="research-grounded",
    status="proposed",
    source=(
        "Research.md Part C.1 item 2: 'generate a burst of fraud_attempt transactions at elevated "
        "**velocity** (multiple attempts in a short window) and at **amount** patterns skewed away from that "
        "person's own historical normal range -- both are the two most consistently cited fraud signals in "
        "the literature (Bhattacharyya et al. 2011; Dal Pozzolo et al. 2017/2018; Part A §2 above). "
        "RESEARCH-GROUNDED for the *signal choice* (velocity + amount-anomaly are real, well-cited "
        "features), MODELING ASSUMPTION for the exact functional form connecting \"compromised\" to a "
        "specific attempt-rate/amount-distribution (no source gives that specific curve).'"
    ),
    citation_verbatim="Bhattacharyya, S., Jha, S.",
    confidence_note=(
        "Research.md Part A §2: 'These two academic citations were located and their existence/content "
        "confirmed via WebSearch's summaries and secondary references, not a firsthand full-text read of "
        "the papers -- flagged per the methodological caveat above; the specific factor list is corroborated "
        "across multiple independent secondary descriptions of both papers, which is why it's reported with "
        "reasonable confidence despite not being a direct quote.'"
    ),
))

register(ProvenanceEntry(
    constant_name="FRAUD_COMPROMISE_TO_ATTEMPT_FUNCTIONAL_FORM",
    location="not implemented -- the specific curve connecting a compromise event to attempt-rate/amount "
    "distribution, Research.md Part C.1 item 2",
    value="not implemented -- no functional form proposed with specific numbers",
    provenance_type="modeling-assumption",
    status="proposed",
    source=(
        "Research.md Part C.1 item 2 (same passage as FRAUD_SIGNAL_CHOICE above): 'MODELING ASSUMPTION for "
        "the exact functional form connecting \"compromised\" to a specific attempt-rate/amount-distribution "
        "(no source gives that specific curve).'"
    ),
))

register(ProvenanceEntry(
    constant_name="FRAUD_RATE_CALIBRATION_TARGET",
    location="not implemented -- proposed calibration target for overall fraud mechanism output, Research.md "
    "Part C.1 item 3",
    value="not implemented as a mechanism; the cited TARGET is 17.6 basis points of transaction value (2023), "
    "up from 7.8 basis points (2011)",
    provenance_type="research-grounded",
    status="proposed",
    source=(
        "Research.md Part A §2 / Part C.1 item 3, citing Federal Reserve Bank of Kansas City, 'New Data on "
        "Card-Present and Card-Not-Present Fraud Rates in the United States', Feb 25 2026 "
        "(kansascityfed.org/research/payments-system-research-briefings/new-data-on-card-present-and-card-"
        "not-present-fraud-rates-in-the-united-states/): 'Overall fraud losses (2023): 17.6 basis points of "
        "transaction value ... up steadily from 7.8 basis points in 2011.' Part C.1 item 3: 'Overall fraud "
        "rate, once implemented, should be checkable against the real, well-sourced target: ~17.6 basis "
        "points of transaction value for 2023 ... This is genuinely the single cleanest calibration target "
        "in all of Part A.'"
    ),
    citation_verbatim="17.6 basis points of transaction value",
    confidence_note=(
        "Research.md Part A §2: 'fetched directly; figures independently confirmed in the page text, not "
        "just a search snippet' -- this is one of the STRONGEST-verified citations in the whole document, "
        "not a WebSearch-synthesis case."
    ),
))

register(ProvenanceEntry(
    constant_name="FRAUD_DETECTION_BLOCK_PROBABILITY",
    location="not implemented -- proposed probability a fraud_attempt is caught/blocked before completing, "
    "Research.md Part C.1 item 4",
    value="not implemented -- no value exists; Research.md explicitly declines to propose one",
    provenance_type="placeholder",
    status="proposed",
    source=(
        "Research.md Part C.1 item 4: 'A fraud_attempt should be probabilistically caught/blocked before "
        "completing (mirroring real detection systems) -- but Part A's search for a real, generalizable "
        "false-positive/detection-rate number came up thin ... Any detection-probability constant here "
        "would have to be a labeled PLACEHOLDER, not dressed up as research-grounded.'"
    ),
    rejected_alternatives=(
        "Research.md Part A §2: 'Reported false-positive rates in recent ML-based fraud-detection research "
        "vary enormously by paper and dataset (some report false-positive rates as low as ~5x10^-5 on "
        "curated, heavily-preprocessed benchmark datasets such as the well-known Kaggle \"Credit Card Fraud "
        "Detection\" dataset). This project treats these specific numbers as **not usable** for anything "
        "beyond noting that a detection/false-positive tradeoff exists in the literature -- benchmark "
        "datasets are known to be unrepresentative of real-world class imbalance and concept drift (a point "
        "Dal Pozzolo et al. make explicitly), so quoting a specific false-positive rate as if it generalizes "
        "would be exactly the kind of overclaiming Rules.md #5 warns against.'"
    ),
))

# --- C.2 Credit scoring (Research.md Part C.2) ------------------------------

register(ProvenanceEntry(
    constant_name="CREDIT_SCORE_INITIAL_DISTRIBUTION",
    location="not implemented -- proposed Person.credit_score field, seeded at world-generation time, "
    "Research.md Part C.2",
    value="not implemented -- proposed range 300-850, seeded from the Fed's 2007 published national FICO "
    "distribution (~2% below 499, 5% in 500-549, 8% in 550-599, 12% in 600-649, 15% in 650-699, 18% in "
    "700-749, 27% in 750-799, 13% at 800+)",
    provenance_type="research-grounded",
    status="proposed",
    source=(
        "Research.md Part A §3, citing Federal Reserve Board, Report to Congress on Credit Scoring and Its "
        "Effects on the Availability and Affordability of Credit, 2007 "
        "(federalreserve.gov/boarddocs/RptCongress/creditscore/general_tables.htm): 'roughly 2% of scored "
        "consumers below 499, 5% in 500-549, 8% in 550-599, 12% in 600-649, 15% in 650-699, 18% in 700-749, "
        "27% in 750-799, and 13% at 800+ -- a distribution that is noticeably left-skewed toward the high "
        "end.' Part C.2: 'a new credit_score field (300-850 range, matching both FICO and VantageScore 4.0's "
        "stated ranges per Part A §3), initialized at world-generation time from a distribution seeded by "
        "the 2007 Fed Report to Congress's published national distribution -- RESEARCH-GROUNDED for the "
        "*initial* distribution shape.'"
    ),
    citation_verbatim="roughly 2% of scored consumers below 499, 5%",
    confidence_note=(
        "Research.md Part A §3: 'Honest caveat: this is 2007 data, nearly two decades old, and the report "
        "itself is proprietary-FICO-adjacent (the task brief explicitly asked to avoid \"proprietary FICO "
        "internals\" -- this report is the Fed's own public regulatory analysis of that data, not FICO's own "
        "methodology, so it's used here only as a distributional shape reference, not a scoring-formula "
        "reference). A materially more current, free, public score-distribution breakdown was not found in "
        "this session's search budget -- reported as a real gap, not papered over.'"
    ),
))

register(ProvenanceEntry(
    constant_name="CREDIT_SCORE_MOVEMENT_MAGNITUDE_PER_MISSED_PAYMENT",
    location="not implemented -- proposed score-movement magnitude, Research.md Part C.2 item 1",
    value="not implemented -- no value exists; proprietary scoring internals make one uncitable",
    provenance_type="modeling-assumption",
    status="proposed",
    source=(
        "Research.md Part C.2 item 1: 'Score should move (mostly downward, in small increments) in response "
        "to a Person's own payment_failure transactions ... MODELING ASSUMPTION for the exact magnitude of "
        "each score movement (no source gives a \"score points lost per missed payment\" figure suitable for "
        "citation -- score-formula internals are proprietary, which is exactly why the task brief said to "
        "avoid FICO internals).'"
    ),
))

register(ProvenanceEntry(
    constant_name="CREDIT_DELINQUENCY_TRANSITION_RATE_TARGET",
    location="not implemented -- proposed aggregate-rate check for a future delinquency mechanism, "
    "Research.md Part C.2 item 2",
    value="not implemented as a mechanism; the cited TARGET range is roughly 1.48% (mortgages) to 7.10% "
    "(credit cards) transitioning into 90+-day serious delinquency, per FRBNY Q1 2026",
    provenance_type="research-grounded",
    status="proposed",
    source=(
        "Research.md Part A §3, citing Federal Reserve Bank of New York, 'Household Debt Balances Rise "
        "Slightly as Delinquency Transition Rates Hold Steady', May 12 2026 (newyorkfed.org/newsevents/news/"
        "research/2026/20260512): 'mortgages 1.48% (up from 1.22% in Q1 2025), HELOC 1.15% (up from 0.88%), "
        "auto loans 2.97% (up from 2.94%), credit cards 7.10% (up from 7.04%), overall across all debt types "
        "2.83% (up from 2.45%).' Part C.2 item 2: 'a rate target this mechanism could be checked against "
        "does exist ... roughly 7.10% of credit-card balances transition into 90+-day serious delinquency in "
        "a given period, vs. 1.48% for mortgages and 2.97% for auto ... per-debt-type transition rates in "
        "the 1-8% range (not flat, and not uniform across debt/product type) is the real, cited target "
        "shape. RESEARCH-GROUNDED for this aggregate check.'"
    ),
    citation_verbatim="cards 7.10% (up from 7.04%)",
    confidence_note=(
        "Research.md Part A §3: 'The report also notes a methodology change: the series switched from "
        "Equifax Risk Score 3.0 to VantageScore 4.0 starting 2026:Q1 -- both range 300-850 and are described "
        "as similarly distributed in purpose, but this is exactly the kind of \"the label changed under the "
        "data\" fact worth recording rather than silently assuming continuity.'"
    ),
))

register(ProvenanceEntry(
    constant_name="CREDIT_SCORE_RECOVERY_RATE",
    location="not implemented -- proposed score-recovery rate for a clean payment record, Research.md Part "
    "C.2 item 3",
    value="not implemented -- no value exists; Research.md explicitly declines to propose one",
    provenance_type="placeholder",
    status="proposed",
    source=(
        "Research.md Part C.2 item 3: 'Score recovery over time (for a Person with a clean payment record) "
        "would need its own rate -- Part A's search did not turn up a clean, generalizable \"recovery "
        "half-life\" statistic (proprietary scoring internals again), so this would have to be a named "
        "PLACEHOLDER.'"
    ),
))

# --- C.3 Loan / interest mechanics (Research.md Part C.3) -------------------

register(ProvenanceEntry(
    constant_name="LOAN_INTEREST_RATE_STRUCTURE",
    location="not implemented -- proposed interest_rate = base_rate + risk_spread(person) structure, "
    "Research.md Part C.3 item 1",
    value="not implemented; cited elasticity ~5 basis points APR per 100 basis points of regional default "
    "risk for credit-card-type unsecured credit, vs. ~30 basis points for mortgages",
    provenance_type="research-grounded",
    status="proposed",
    source=(
        "Research.md Part A §4, citing Federal Reserve, FEDS Notes, 'Examining the Relationship Between Loan "
        "Pricing and Credit Risk', Sept 24 2025 (federalreserve.gov/econres/notes/feds-notes/examining-the-"
        "relationship-between-loan-pricing-and-credit-risk-20250924.html): 'a 100-basis-point increase in "
        "regional default risk is associated with roughly a 30-basis-point increase in jumbo mortgage rates, "
        "but only about a 5-basis-point increase in credit-card APRs.' Part C.3 item 1: 'interest_rate = "
        "base_rate + risk_spread(person) ... RESEARCH-GROUNDED for the *structure* (rate = base + risk-based "
        "spread is exactly how the Fed's own Sept 2025 FEDS Note describes real consumer lending), with the "
        "specific *elasticity* citable per loan type: roughly 5 basis points of APR spread per 100 basis "
        "points of regional default risk for credit-card-type unsecured credit (vs. ~30bps for mortgages).'"
    ),
    citation_verbatim="roughly 5 basis points of APR",
))

register(ProvenanceEntry(
    constant_name="LOAN_RISK_SPREAD_PERSON_LEVEL_TRANSLATION",
    location="not implemented -- proposed step translating the regional-default-risk elasticity above into "
    "a per-person credit-score-based spread, Research.md Part C.3 item 1",
    value="not implemented -- no per-person functional form proposed with specific numbers",
    provenance_type="modeling-assumption",
    status="proposed",
    source=(
        "Research.md Part C.3 item 1 (same passage as LOAN_INTEREST_RATE_STRUCTURE): 'though it's a "
        "regional-default-risk elasticity, not a per-individual-credit-score elasticity, so translating it "
        "into a per-person spread function would still involve a MODELING ASSUMPTION step.'"
    ),
))

register(ProvenanceEntry(
    constant_name="LOAN_BASE_RATE_PLAUSIBILITY_BOUND",
    location="not implemented -- proposed sanity-check range for a chosen base_rate, Research.md Part C.3 "
    "item 2",
    value="not implemented as a mechanism; the cited sanity-check RANGE is 8.73% (record low, May 2022) to "
    "19.21% (record high, November 1981), FRED series TERMCBPER24NS",
    provenance_type="research-grounded",
    status="proposed",
    source=(
        "Research.md Part A §4, citing FRED, 'Finance Rate on Personal Loans at Commercial Banks, 24 Month "
        "Loan' (fred.stlouisfed.org/series/TERMCBPER24NS): 'historical range roughly 8.73% (record low, May "
        "2022) to 19.21% (record high, November 1981); most recently reported at 11.65% (November 2025).' "
        "Part C.3 item 2: 'base_rate itself could be checked against G.19's real historical range for "
        "24-month personal loans (8.73%-19.21%, Part A §4) as a plausibility bound for whatever base rate "
        "this simulation picks -- RESEARCH-GROUNDED as a sanity-check range, not as a specific value (the "
        "simulation has no real-world-mapped time axis to place itself on that 1972-2025 series).'"
    ),
    citation_verbatim="historical range roughly 8.73% (record",
))

register(ProvenanceEntry(
    constant_name="LOAN_DEFAULT_DELINQUENCY_TARGET",
    location="not implemented -- proposed aggregate-rate check for Loan.status transitions, Research.md "
    "Part C.3 item 3",
    value="not implemented as a mechanism; the cited TARGET range is roughly 2.6%-5.5% delinquency "
    "(corresponding charge-off roughly 3.7%-6.2%) across full credit cycles, for card-type unsecured credit",
    provenance_type="research-grounded",
    status="proposed",
    source=(
        "Research.md Part A §4: 'Historical Fed Bulletin data (1990s-2000s) put credit-card *delinquency "
        "rates* (not just transitions) in a roughly 2.6%-5.5% range across the last three decades' full "
        "credit cycles (a 2008-crisis peak just above 5.5% delinquency / just above 6% net charge-off; more "
        "recent 2024 cycle peak 3.2% delinquency / 4.6% charge-off; pre-pandemic baseline roughly 2.6% "
        "delinquency / 3.7% charge-off).' Part C.3 item 3: 'Default/delinquency probability, if a Loan's "
        "status transitions probabilistically, has real target ranges from Part A §4 ... RESEARCH-GROUNDED "
        "as an aggregate-rate target, same caveat as C.2's item 2 about not specifying individual-level "
        "functional form.'"
    ),
    citation_verbatim="in a roughly 2.6%-5.5% range across the last three decades' full credit",
))

register(ProvenanceEntry(
    constant_name="LOAN_CAPITAL_CONSTRAINT_MODEL_CHOICE",
    location="not implemented -- proposed 'loanable funds' constraint design choice, Research.md Part C.3 "
    "(new agent/data-model state section)",
    value="not implemented; the cited real-world fact used to inform this design choice is that U.S. reserve "
    "requirement ratios have been 0% for all depository institutions since March 26, 2020",
    provenance_type="research-grounded",
    status="proposed",
    source=(
        "Research.md Part A §5, citing Federal Reserve Board, 'Reserve Requirements' "
        "(federalreserve.gov/monetarypolicy/reservereq.htm): 'as of March 26, 2020, the Federal Reserve "
        "Board reduced all reserve requirement ratios to zero percent, eliminating reserve requirements for "
        "all U.S. depository institutions -- this is current, standing policy, not a temporary pandemic-era "
        "footnote that later reversed.' Part C.3: 'Part A §5 found that a classical fractional-reserve "
        "constraint would actually be *less* realistic for a present-day simulation than an unconstrained "
        "model ... so any capital constraint added here should be modeled on Basel-style capital-adequacy/"
        "Liquidity-Coverage-Ratio concepts, not a pre-2020 reserve-ratio model -- an explicit, cited "
        "correction to what a naive \"add bank reserve requirements\" design might otherwise assume.'"
    ),
    citation_verbatim="the Federal Reserve Board reduced all reserve requirement",
    notes=(
        "This research finding is ALSO reported in Research.md Part A §5 as requiring NO code change to the "
        "currently-implemented world/agents/bank.py `bank_reserve` account (see this catalog's 'Excluded "
        "items' notes in provenance/README.md for why bank_reserve itself has no separate catalog entry): "
        "'there's no lending mechanism yet for a reserve *requirement* to meaningfully constrain ... the "
        "current unconstrained, monotonically-non-decreasing reserve account is, if anything, closer to "
        "2020s reality than a classical fractional-reserve constraint would be.'"
    ),
))
