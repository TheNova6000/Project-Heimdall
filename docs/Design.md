# Design

## Framing

This UI's job is to make a judge (or a finance/risk ops user) trust a decision
in under 5 seconds, then let them drill into the full evidence trail in one more
click. Every design choice serves "explainable, bounded, gated" — the bar
Track 1 states explicitly and the others imply. This is a case-review dashboard
for someone deciding whether to trust an automated verdict, not a marketing
surface — so it should read as instrumentation, not a product landing page.

## Explicitly not reusing

Discovery.AI's `chat.html` is a conversational, single-thread interface, and its
landing page carries a WASM fluid-simulation background purely as a visual
flourish. Neither serves this project: the financial dashboard is a
multi-case, multi-agent review surface, and a credibility-driven demo for a
buildathon judge should not open on a decorative animation. Build a new,
separate frontend under `financial_system/frontend/`; reuse only Cytoscape.js
for graph rendering (already a proven dependency, no reason to replace it) and
the "no build step, vanilla HTML/JS/CSS" convention Discovery.AI already
established.

## Color — semantic first, brand second

Every color in this UI encodes a decision state. Nothing is decorative.

| Token | Hex | Meaning |
|---|---|---|
| `--allow` | `#1a7f4e` (dark green) | Policy ALLOW / low risk / reconciled / recovered |
| `--review` | `#b45309` (amber) | Policy REVIEW / medium risk / exception unresolved |
| `--deny` | `#b91c1c` (red) | Policy DENY / high risk / unrecoverable |
| `--investigating` | `#2554c7` (blue) | Discovery.AI investigation in progress |
| `--fact` | `#1f2937` (near-black) | FACT-tier evidence text |
| `--inference` | `#4b5563` (gray) | INFERENCE-tier text |
| `--hypothesis` | `#6b7280` italic | HYPOTHESIS-tier text, always visually distinct from FACT |
| `--bg` | `#f8f9fb` (light) / `#0f1115` (dark) | page background |
| `--surface` | `#ffffff` / `#181b21` | card background |

Decision badges (ALLOW/REVIEW/DENY, and Risk HIGH/MEDIUM/LOW) always pair color
with a text label — never color alone, for accessibility and because a judge
screenshotting the demo shouldn't lose meaning in grayscale.

## Typography

System font stack, no web font load, matching Discovery.AI's no-build-step
approach: `-apple-system, "Segoe UI", Roboto, sans-serif` for UI chrome.
`ui-monospace, "Cascadia Code", Consolas, monospace` for anything that's
literally financial-record data — amounts, IDs, UTRs, evidence snippets. This
mirrors how a ledger reads: prose is sans, numbers and identifiers are mono, so
a judge's eye can separate "the system's claim" from "the raw fact behind it"
at a glance.

Scale: 13px base (dense, dashboard-appropriate, not marketing-page large),
15px for verdict card headlines, 11px uppercase-tracked for section labels.

## Layout

- **Case list** (left rail): every `AgentVerdict`/Compound Case, sorted newest
  first, each row showing subject id, decision badge, one-line reason.
- **Case detail** (center): the `AgentVerdict` card(s) for the selected case —
  decision, reason, `metrics` as small stat chips, `decision_score` as a labeled
  bar (never an unlabeled progress bar — always show the number), and a
  separate, visually distinct block for `investigation_confidence` when an
  investigation backs the verdict, so the two numbers from `ARCHITECTURE.md` §4
  are never visually conflated.
- **Evidence / graph panel** (right rail, toggle between two views): a flat
  evidence list (FACT/INFERENCE/HYPOTHESIS tiered, per §Epistemic status) and a
  Cytoscape graph view centered on the subject, edges colored by relation
  family (composition/temporal/causal/dependency/interaction/classification/
  financial).
- **Metrics bar** (top, persistent): the three headline numbers from `PRD.md`
  (Risk precision/recall, Controller match rate, Recovery rate), always visible
  — not buried in a settings page. This is the buildathon's actual ask, so it's
  the one thing that should never require a click to see.

## Motion

Minimal. A state transition (verdict → policy → action → verification) may
animate as a short (200ms) badge cross-fade, nothing more. No idle animation,
no parallax, no loading flourishes beyond a plain spinner during an active
`open_investigation()` call — the tone is instrumentation, not a product demo
reel, and unnecessary motion undercuts the "credible, defensible" read a risk
tool needs.

## Dark mode

Supported via `prefers-color-scheme`, tokens above already define both. Not
optional — buildathon judges may review at night, and semantic colors need to
hold their meaning (green=allow, red=deny) in both.
