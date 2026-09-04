"""
Heimdall Beta API.

A thin, read-only FastAPI wrapper around the real, frozen financial_system
decision agents (Risk, Recovery, Controller). Every endpoint here imports and
calls the actual, unmodified decision functions live, against the real,
frozen financial_graph.db -- nothing is precomputed or baked into the
frontend. This file only reads from financial_system/; it never writes to
financial_graph.db or any of the frozen decision code.

The one exception is /api/ask, a stateless proxy to Anthropic's Messages API:
it forwards the caller's own API key (sent per-request in a header, never
stored, never logged) so the frontend's chat feature works without us
holding anyone's key server-side.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from financial_system.discovery_adapter.investigate import investigate_evidence
from financial_system.discovery_adapter.models import InvestigationRequest, InvestigationResult, InvestigationStatus
from financial_system.financial_graph.repository import GraphRepository
from financial_system.reconciliation.controller import run_controller_for_settlement
from financial_system.reconciliation.deterministic import reconcile_settlement
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.recovery.signals import compute_recovery_signals
from financial_system.risk.risk_agent import run_risk_for_device
from financial_system.risk.runner import devices_with_sharers
from financial_system.risk.scoring import risk_tier, score_signals
from financial_system.risk.signals import compute_device_risk_signals

from api.truman_env import get_environment

GRAPH_DB_PATH = Path(__file__).resolve().parent.parent / "financial_system" / "data" / "financial_graph.db"

app = FastAPI(title="Heimdall Beta API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://thenova6000.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _graph() -> GraphRepository:
    return GraphRepository(GRAPH_DB_PATH)


# Curated real entity ids -- picked once by hand from the real, frozen
# financial_graph.db for variety (every failure_reason category, a real
# fraud-ring-shaped device, a real accounting-gap settlement). This list
# only decides WHICH real cases the frontend's rail shows first; every
# endpoint below still queries the live database on every single request --
# nothing about the actual verdicts is cached or precomputed here.
CURATED = {
    "payments": [
        {"id": "pay_f63eecc054", "label": "insufficient_funds", "hint": "RETRY, 45% base rate"},
        {"id": "pay_c7141196c8", "label": "timeout", "hint": "RETRY, 80% base rate"},
        {"id": "pay_5738800427", "label": "risk_block", "hint": "ESCALATE, not recoverable"},
        {"id": "pay_ef36354524", "label": "issuer_declined", "hint": "RETRY, 20% base rate"},
        {"id": "pay_711592cb5c", "label": "expired", "hint": "ESCALATE, not recoverable"},
        {"id": "pay_e2a54272e6", "label": "technical_failure", "hint": "RETRY, 85% base rate"},
        {"id": "pay_2b68379960", "label": "authentication_failure", "hint": "RETRY, 55% base rate"},
        {"id": "pay_ac3faf06c9", "label": "succeeded", "hint": "no Recovery decision needed"},
    ],
    "devices": [
        {"id": "dev_0079", "label": "5 customers share this device", "hint": "HIGH risk, score ≈ 1.0"},
        {"id": "dev_0141", "label": "5 customers share this device", "hint": "HIGH risk, score ≈ 1.0"},
        {"id": "dev_0184", "label": "4 customers share this device", "hint": "HIGH risk, score ≈ 0.95"},
        {"id": "dev_0082", "label": "2 customers share this device", "hint": "LOW risk, score ≈ 0.05"},
    ],
    "settlements": [
        {"id": "sett_bac5b4c642", "label": "clean match", "hint": "PASS"},
        {"id": "sett_5ebacb3627", "label": "genuine accounting gap", "hint": "INVESTIGATE, unexplained"},
        {"id": "sett_069d9c7f26", "label": "duplicate line item, self-resolved", "hint": "RESOLVE"},
    ],
}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/cases")
def cases():
    return CURATED


@app.get("/api/graph/node/{node_id}")
def node(node_id: str):
    g = _graph()
    try:
        n = g.get_node(node_id)
        if not n:
            raise HTTPException(404, f"{node_id} not found in financial_graph.db")
        return {"id": n.node_id, "type": n.node_type, "properties": n.properties}
    finally:
        g.close()


@app.get("/api/graph/neighborhood/{node_id}")
def neighborhood(node_id: str):
    """The node itself, plus every node one hop away in either direction --
    real edges from the real graph, queried live."""
    g = _graph()
    try:
        center = g.get_node(node_id)
        if not center:
            raise HTTPException(404, f"{node_id} not found in financial_graph.db")
        out_edges = g.edges_from(node_id)
        in_edges = g.edges_to(node_id)
        node_ids = {node_id}
        edges = []
        for e in out_edges:
            node_ids.add(e.object_id)
            edges.append({"from": e.subject_id, "to": e.object_id, "rel": e.relation})
        for e in in_edges:
            node_ids.add(e.subject_id)
            edges.append({"from": e.subject_id, "to": e.object_id, "rel": e.relation})
        nodes = []
        for nid in node_ids:
            n = g.get_node(nid)
            if n:
                nodes.append({"id": n.node_id, "type": n.node_type, "properties": n.properties})
        return {"nodes": nodes, "edges": edges}
    finally:
        g.close()


@app.get("/api/recovery/{payment_id}")
def recovery(payment_id: str):
    g = _graph()
    try:
        if not g.get_node(payment_id):
            raise HTTPException(404, f"{payment_id} not found in financial_graph.db")
        verdict = run_recovery_for_payment(g, payment_id, investigate=False)
        return json.loads(verdict.model_dump_json())
    finally:
        g.close()


@app.get("/api/risk/{device_id}")
def risk(device_id: str):
    g = _graph()
    try:
        if not g.get_node(device_id):
            raise HTTPException(404, f"{device_id} not found in financial_graph.db")
        verdict = run_risk_for_device(g, device_id, investigate=False)
        return json.loads(verdict.model_dump_json())
    finally:
        g.close()


@app.get("/api/controller/{settlement_id}")
def controller(settlement_id: str):
    g = _graph()
    try:
        if not g.get_node(settlement_id):
            raise HTTPException(404, f"{settlement_id} not found in financial_graph.db")
        verdict = run_controller_for_settlement(g, settlement_id, investigate=False)
        return json.loads(verdict.model_dump_json())
    finally:
        g.close()


@app.get("/api/investigate/{subject_type}/{subject_id}")
def investigate(subject_type: str, subject_id: str):
    """Runs the REAL Discovery.AI investigation pass (investigate_evidence(),
    unmodified vendor code -- genuine multi-step decide_next_step /
    gather_evidence / synthesize_answer, not a scripted narrative) for the
    given subject, but ONLY when the real domain agent would actually trigger
    it: Recovery's unknown-category rule, Risk's HIGH-tier rule, Controller's
    UNEXPLAINED rule -- each re-derived here from the same real signal
    functions the agents themselves call, never guessed. If the deployment
    has no server-side LLM key configured, this returns the SAME honest
    'not executed' note investigate_evidence() already produces on its own --
    it is not a separate failure path, just that function's real behavior."""
    g = _graph()
    try:
        node = g.get_node(subject_id)
        if not node:
            raise HTTPException(404, f"{subject_id} not found in financial_graph.db")

        request = InvestigationRequest(
            subject_type=subject_type, subject_id=subject_id,
            question_text=f"Explain {subject_type} {subject_id}.",
        )

        if subject_type == "Settlement":
            fact = reconcile_settlement(g, subject_id)
            if fact.status != "UNEXPLAINED":
                return {"triggered": False,
                        "reason": f"Controller's own status is {fact.status} -- Discovery.AI is only "
                                  f"invoked when a settlement is genuinely UNEXPLAINED."}
            prefilled = InvestigationResult(
                request=request, status=InvestigationStatus.UNEXPLAINED,
                expected_amount=str(fact.expected_amount),
                actual_amount=str(fact.actual_amount) if fact.actual_amount is not None else None,
                unexplained_amount=str(fact.unexplained_amount) if fact.unexplained_amount is not None else None,
                facts=fact.facts, evidence=fact.evidence,
            )
        elif subject_type == "Device":
            sig = compute_device_risk_signals(g, subject_id)
            score, _ = score_signals(sig)
            tier = risk_tier(score)
            if tier != "HIGH":
                return {"triggered": False,
                        "reason": f"Risk's own tier is {tier} -- Discovery.AI is only invoked for a "
                                  f"HIGH-tier device."}
            prefilled = InvestigationResult(
                request=request, status=InvestigationStatus.UNEXPLAINED,
                facts=[f"device shared by {sig.n_sharers} customers"], evidence=sig.evidence,
            )
        elif subject_type == "Payment":
            sig = compute_recovery_signals(g, subject_id)
            if sig.known_category:
                return {"triggered": False,
                        "reason": f"Recovery already recognizes failure_reason={sig.failure_reason!r} -- "
                                  f"Discovery.AI is only invoked for a genuinely unrecognized category."}
            prefilled = InvestigationResult(
                request=request, status=InvestigationStatus.UNEXPLAINED, evidence=sig.evidence,
            )
        else:
            raise HTTPException(400, f"unsupported subject_type {subject_type!r}")

        try:
            result = investigate_evidence(request, prefilled, g)
        except Exception as e:  # noqa: BLE001 -- a missing optional LLM dependency degrades, never 500s
            return {"triggered": True,
                    "result": json.loads(prefilled.model_dump_json()),
                    "degraded_reason": f"4B raised {type(e).__name__}: {e}"}
        return {"triggered": True, "result": json.loads(result.model_dump_json())}
    finally:
        g.close()


# ---------------------------------------------------------------------------
# Truman environment: one real, server-held SimulationEngine, advanced one
# real day at a time. Every endpoint below queries or ticks the SAME live
# world (api/truman_env.py) -- nothing here is a second, fabricated dataset.
# Ephemeral: this environment resets to day 0 whenever the server process
# restarts (a Render free-tier redeploy, a cold-start after idling). That is
# a real, stated property of an in-memory demo environment, not a bug.
# ---------------------------------------------------------------------------

@app.get("/api/truman/state")
def truman_state():
    env = get_environment()
    g = env.graph()
    try:
        rows = g._conn.execute(
            "SELECT node_id, properties FROM graph_nodes WHERE node_type='Payment'"
        ).fetchall()
        failed_payments = sorted(
            row["node_id"] for row in rows
            if json.loads(row["properties"]).get("status") == "failed"
        )
        eligible_devices = devices_with_sharers(g)
    finally:
        g.close()
    return {
        "day": env.day, "max_days": env.engine.num_days,
        "seed": env.engine.seed, "population": env.engine.num_persons,
        "total_transactions": len(env.engine.transactions),
        "failed_payments": failed_payments,
        "eligible_devices": eligible_devices,
        "blocked_devices": sorted(env.blocked_devices),
        "recent_log": env.log[-10:],
    }


@app.post("/api/truman/tick")
def truman_tick():
    env = get_environment()
    return env.tick()


@app.get("/api/truman/graph/neighborhood/{node_id}")
def truman_neighborhood(node_id: str):
    env = get_environment()
    g = env.graph()
    try:
        center = g.get_node(node_id)
        if not center:
            raise HTTPException(404, f"{node_id} not found in the current Truman environment")
        out_edges = g.edges_from(node_id)
        in_edges = g.edges_to(node_id)
        node_ids = {node_id}
        edges = []
        for e in out_edges:
            node_ids.add(e.object_id)
            edges.append({"from": e.subject_id, "to": e.object_id, "rel": e.relation})
        for e in in_edges:
            node_ids.add(e.subject_id)
            edges.append({"from": e.subject_id, "to": e.object_id, "rel": e.relation})
        nodes = []
        for nid in node_ids:
            n = g.get_node(nid)
            if n:
                nodes.append({"id": n.node_id, "type": n.node_type, "properties": n.properties})
        return {"nodes": nodes, "edges": edges}
    finally:
        g.close()


@app.get("/api/truman/recovery/{payment_id}")
def truman_recovery(payment_id: str):
    env = get_environment()
    g = env.graph()
    try:
        if not g.get_node(payment_id):
            raise HTTPException(404, f"{payment_id} not found in the current Truman environment")
        verdict = run_recovery_for_payment(g, payment_id, investigate=False)
        return json.loads(verdict.model_dump_json())
    finally:
        g.close()


@app.get("/api/truman/risk/{device_id}")
def truman_risk(device_id: str):
    env = get_environment()
    g = env.graph()
    try:
        if not g.get_node(device_id):
            raise HTTPException(404, f"{device_id} not found in the current Truman environment")
        verdict = run_risk_for_device(g, device_id, investigate=False)
        return json.loads(verdict.model_dump_json())
    finally:
        g.close()


class AskBody(BaseModel):
    provider: str = "anthropic"   # "anthropic" | "groq" | "gemini"
    model: str | None = None
    max_tokens: int = 1024
    messages: list[dict]          # [{role: "user"|"assistant", content: str}, ...]
    system: str | None = None


PROVIDER_DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-5",
    "groq": "openai/gpt-oss-120b",
    "gemini": "gemini-3.7-flash",
}


async def _ask_anthropic(api_key: str, model: str, body: AskBody) -> str:
    payload = {"model": model, "max_tokens": body.max_tokens, "messages": body.messages}
    if body.system:
        payload["system"] = body.system
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text[:500])
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", []))


async def _ask_groq(api_key: str, model: str, body: AskBody) -> str:
    # Groq's chat-completions endpoint is OpenAI-compatible.
    msgs = ([{"role": "system", "content": body.system}] if body.system else []) + body.messages
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={"model": model, "max_tokens": body.max_tokens, "messages": msgs},
        )
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text[:500])
    data = resp.json()
    return data["choices"][0]["message"]["content"]


async def _ask_gemini(api_key: str, model: str, body: AskBody) -> str:
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
                for m in body.messages]
    payload = {"contents": contents}
    if body.system:
        payload["systemInstruction"] = {"parts": [{"text": body.system}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, params={"key": api_key}, headers={"content-type": "application/json"}, json=payload)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text[:500])
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


_PROVIDER_FN = {"anthropic": _ask_anthropic, "groq": _ask_groq, "gemini": _ask_gemini}


@app.post("/api/ask")
async def ask(body: AskBody, request: Request):
    """Stateless proxy: one endpoint, three upstream LLM providers
    (Anthropic / Groq / Gemini), response always normalized to {"text": ...}
    so the frontend never has to know each provider's own reply shape. The
    caller's own API key travels in the x-api-key header of THIS request and
    is forwarded as-is to the chosen provider -- never written to disk, a
    database, or a log line here. Multi-key fallback (comma-separated keys)
    is the frontend's job, one request per key attempt -- this endpoint only
    ever sees one key per call."""
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(400, "Missing x-api-key header -- add an API key in Settings")
    fn = _PROVIDER_FN.get(body.provider)
    if not fn:
        raise HTTPException(400, f"unknown provider {body.provider!r} -- use anthropic, groq, or gemini")
    model = body.model or PROVIDER_DEFAULT_MODEL[body.provider]
    text = await fn(api_key, model, body)
    return {"text": text}
