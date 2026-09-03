"""
Deterministic risk signals -- zero LLM, graph/deterministic intelligence only
(ARCHITECTURE.md §0, kinds 1-2). Computed per device with >=2 sharing
customers, since a device used by exactly one customer carries no network
signal at all.

Four signals, chosen to match what actually separates DATASET_DESIGN.md's two
device-sharing archetypes:
  - n_sharers: more accounts on one device is a stronger signal, but alone it's
    also true of a benign shared family device -- never decisive by itself.
  - min_account_age_days: documented in DATASET_DESIGN.md as a ring signal
    ("accounts created shortly before their payments"), but verified against
    the actual generator (generate_dataset.py's gen_customers()) to be
    disconnected from ring membership entirely -- account creation is
    independent of ring assignment in the real generated data. Kept as a
    signal (real-world meaningful, and harmless if it doesn't discriminate
    here) but weighted low in scoring.py rather than pretended it works.
  - max_burst_count: NOT total payments / total span -- a ring member's OTHER,
    ordinary purchases land on the same shared device and dilute that ratio
    to near-zero. Computed as the most payments falling within any 60-minute
    window instead, so a real burst is detected even embedded in a noisier
    history.
  - burst_amount_cov (coefficient of variation): computed within that same
    densest window, for the same reason -- whole-history variance is diluted
    by unrelated purchases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from financial_system.financial_graph.queries import edges_to_as_of
from financial_system.financial_graph.repository import GraphRepository

BURST_WINDOW_MINUTES = 60


@dataclass
class RiskSignals:
    device_id: str
    n_sharers: int
    sharer_customer_ids: list[str] = field(default_factory=list)
    n_payments: int = 0
    min_account_age_days: float | None = None
    max_burst_count: int = 0
    burst_amount_cov: float | None = None
    evidence: list[str] = field(default_factory=list)


def _payments_on_device(graph: GraphRepository, device_id: str,
                         as_of: datetime | None = None) -> list[tuple[str, object]]:
    """[(customer_id, payment_node), ...] for every payment made using this
    device -- every payment ever observed by default (unchanged from
    before Block 5), or only those at or before as_of when a caller
    explicitly opts into temporally-scoped observation (see
    financial_graph/queries.py::edges_to_as_of)."""
    results = []
    edges = (edges_to_as_of(graph, device_id, "used_device", as_of) if as_of is not None
             else graph.edges_to(device_id, "used_device"))
    for e in edges:
        payment = graph.get_node(e.subject_id)
        if not payment:
            continue
        cust_edges = graph.edges_to(e.subject_id, "initiated")
        if cust_edges:
            results.append((cust_edges[0].subject_id, payment))
    return results


def _densest_window(timestamps: list[datetime], window: timedelta) -> list[int]:
    """Indices (into `timestamps`) of the timestamps packed into the single
    most crowded window of the given size -- a simple O(n^2) sliding scan,
    fine at this dataset's scale (a handful to a few dozen payments/device)."""
    order = sorted(range(len(timestamps)), key=lambda i: timestamps[i])
    best: list[int] = []
    for i in range(len(order)):
        start = timestamps[order[i]]
        window_indices = [order[i]]
        for j in range(i + 1, len(order)):
            if timestamps[order[j]] - start <= window:
                window_indices.append(order[j])
            else:
                break
        if len(window_indices) > len(best):
            best = window_indices
    return best


def compute_device_risk_signals(graph: GraphRepository, device_id: str,
                                 as_of: datetime | None = None) -> RiskSignals:
    pairs = _payments_on_device(graph, device_id, as_of)
    sharer_ids = sorted({cid for cid, _ in pairs})
    n_sharers = len(sharer_ids)

    if n_sharers <= 1:
        return RiskSignals(device_id=device_id, n_sharers=n_sharers, sharer_customer_ids=sharer_ids,
                            n_payments=len(pairs))

    def payment_time(p) -> datetime | None:
        ts = p.properties.get("captured_at") or p.properties.get("created_at")
        return datetime.fromisoformat(ts) if ts else None

    evidence = [device_id] + [p.node_id for _, p in pairs] + sharer_ids

    ages = []
    for cid in sharer_ids:
        customer = graph.get_node(cid)
        created_at = datetime.fromisoformat(customer.properties["created_at"])
        cust_times = [t for c2, p in pairs if c2 == cid and (t := payment_time(p)) is not None]
        if cust_times:
            ages.append((min(cust_times) - created_at).total_seconds() / 86400)
    min_age_days = min(ages) if ages else None

    dated = [(t, Decimal(p.properties["amount"])) for _, p in pairs if (t := payment_time(p)) is not None]
    max_burst_count = 0
    burst_amount_cov = None
    if dated:
        ts_list = [t for t, _ in dated]
        window_idx = _densest_window(ts_list, timedelta(minutes=BURST_WINDOW_MINUTES))
        max_burst_count = len(window_idx)
        window_amounts = [dated[i][1] for i in window_idx]
        if len(window_amounts) >= 2:
            mean = sum(window_amounts) / len(window_amounts)
            if mean != 0:
                variance = sum((a - mean) ** 2 for a in window_amounts) / len(window_amounts)
                burst_amount_cov = float(variance.sqrt() / mean)

    return RiskSignals(
        device_id=device_id, n_sharers=n_sharers, sharer_customer_ids=sharer_ids,
        n_payments=len(pairs), min_account_age_days=min_age_days,
        max_burst_count=max_burst_count, burst_amount_cov=burst_amount_cov, evidence=evidence,
    )
