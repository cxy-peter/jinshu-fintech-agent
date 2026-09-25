"""Replays bind candidate, baseline, corpus, sample inputs and evaluator source.
Single-runtime validation does not implement a distributed atomic publisher.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()).hexdigest()


def policy_payload(skill):
    return {k: skill.get(k) for k in ("_id", "family", "dept_id", "action", "trigger", "version", "expected_terms")}


def evaluator_hash() -> str:
    root = Path(__file__).parent
    files = ["release_contract.py", "loop.py", "agents.py", "retrieval.py", "skills.py", "policy.py", "rewrite_contract.py"]
    return digest({p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files})


async def replay_binding(container, skill, traces):
    docs = sorted(await container.store.list_documents(), key=lambda r: r["_id"])
    chunks = sorted(await container.store.list_all_chunks(), key=lambda r: r["_id"])
    active = sorted((await container.store.list_skills(status="active")), key=lambda r: r["_id"])
    baseline = [{**policy_payload(s), "gray_percent": s.get("gray_percent")} for s in active if s.get("family") == skill.get("family")]
    return {"candidate": digest(policy_payload(skill)), "corpus": digest({"docs": docs, "chunks": chunks}),
            "baseline": digest(baseline), "evaluator": evaluator_hash(),
            "samples": digest([{k: t.get(k) for k in ("_id", "query", "workflow", "params", "skill_plan", "last_user_query")} for t in traces])}
