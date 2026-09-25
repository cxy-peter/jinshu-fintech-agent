"""Original-preserving, bounded rewrite validation; no model prompt changes."""
from __future__ import annotations
import re
import unicodedata

def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower().strip()

def protected_terms(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,:/-]\d+)*(?:\s*%|\s*天|\s*万元|\s*元)?|[a-z]+[-_]?[a-z]*\d+[a-z0-9_-]*|\b(?:iban|kyc|kyb|t\+1|fof|etf)\b", normalize(text)))

def bounded_queries(original: str, proposals: list[str]) -> tuple[list[str], list[dict]]:
    """Keep the literal request; reject entity/number/negation drift in model rewrites.

    This is a conservative lexical contract, not semantic equivalence proof.
    The maximum remains three queries. Original permissions/budgets are untouched.
    """
    result, decisions = [original], []
    a = normalize(original)
    negatives = re.compile(r"不包括|不包含|不要|不能|不得|不允许|没有|未提供|未满|排除|without|\bnot\b|\bnever\b", re.I)
    for proposal in proposals[:8]:
        reason = None
        if not isinstance(proposal, str) or not proposal.strip() or len(proposal) > max(500, len(original) + 200):
            reason = "invalid_or_unbounded_rewrite"
        else:
            b = normalize(proposal)
            if re.search(r"https?:|<|>|忽略.{0,12}(指令|要求)|system\s*prompt|ignore.{0,16}instruction", b):
                reason = "unsafe_rewrite"
            elif protected_terms(original) != protected_terms(proposal):
                reason = "entity_or_number_changed"
            elif bool(negatives.search(a)) != bool(negatives.search(b)) or (negatives.search(a) and a not in b):
                reason = "negation_clause_not_preserved"
            if not reason:
                combined = proposal if a in b else original + "；检索提示：" + proposal
                if combined not in result and len(result) < 3:
                    result.append(combined)
        decisions.append({"accepted": reason is None, "reason": reason or "original_preserved"})
    return result, decisions
