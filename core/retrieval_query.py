"""Shared, bounded lexical preparation for browser and server retrieval.

Aliases change matching terms, never source text or answers. They do not create
evidence. The JSON vocabulary is consumed by the browser as well, so FOF, full
width text and Chinese names do not have different behavior across entry points.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

LEXICON_PATH = Path(__file__).parent / 'web' / 'retrieval-lexicon.json'
_LEXICON_BYTES = LEXICON_PATH.read_bytes()
LEXICON = json.loads(_LEXICON_BYTES)
LEXICON_SIGNATURE = hashlib.sha256(_LEXICON_BYTES).hexdigest()[:16]
STOP_WORDS = frozenset(LEXICON['stop_words'])
STRICT_ALIASES = frozenset(LEXICON['strict_anchors'])
_HAN = r'\u3400-\u9fff'
_BASE_TERMS = re.compile(r'[a-z0-9_]{2,}|[' + _HAN + r']+')
_FORMAT = [re.compile(p, re.I) for p in LEXICON['format_patterns']]
_QUESTIONS = [re.compile(p, re.I) for p in LEXICON['question_patterns']]


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKC', str(text or '')).casefold()
    text = re.sub(r'(?<=[a-z])-\s*\n\s*(?=[a-z])', '', text)
    # PDF line wraps affect the index only; the source and its hash stay intact.
    text = re.sub(r'(?<=[' + _HAN + r'])\s*[\r\n]+\s*(?=[' + _HAN + r'])', '', text)
    return re.sub(r'\s+', ' ', text).strip()


_ALIAS_BY_FORM = {normalize(form): item for item in LEXICON['aliases'] for form in item['forms']}


def _form_pattern(form):
    escaped = re.escape(form).replace(r'\ ', r'\s+')
    if re.match(r'[a-z0-9]', form): escaped = r'(?<![a-z0-9_])' + escaped
    if re.search(r'[a-z0-9.]$', form): escaped += r'(?![a-z0-9_])'
    return escaped


_ALIASES = re.compile('|'.join(_form_pattern(f) for f in sorted(_ALIAS_BY_FORM, key=len, reverse=True)), re.I)


def alias_matches(text):
    return [(m, _ALIAS_BY_FORM[re.sub(r'\s+', ' ', m.group())]) for m in _ALIASES.finditer(normalize(text))]


def base_terms(text: str) -> Counter:
    result = []
    for match in _BASE_TERMS.findall(normalize(text)):
        if re.match(r'[a-z0-9_]', match):
            if match not in STOP_WORDS: result.append(match)
        elif len(match) == 1:
            if match not in STOP_WORDS: result.append(match)
        else:
            result.extend(match[i:i+2] for i in range(len(match)-1)
                          if match[i:i+2] not in STOP_WORDS
                          and match[i] not in STOP_WORDS and match[i+1] not in STOP_WORDS)
    return Counter(result)


def terms(text: str) -> Counter:
    """Body tokens include exact words AND a token for each attested alias."""
    result = base_terms(text)
    for _, item in alias_matches(text): result['concept_' + item['id']] += 1
    return result


def focus_query(query: str) -> str:
    value = normalize(query)
    for pattern in _FORMAT: value = pattern.sub(' ', value)
    for pattern in _QUESTIONS: value = pattern.sub(' ', value)
    value = re.sub(r'[，。！？；：、,!?;:\[\]（）()]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def plan_query(query: str) -> dict:
    focus = focus_query(query)
    matched = list(dict.fromkeys(item['id'] for _, item in alias_matches(focus)))
    # A matched spelling is ONE concept, not a set of independently mandatory
    # translations. Otherwise adding an alias makes the coverage denominator
    # grow and ironically lowers recall.
    canonical = _ALIASES.sub(lambda m: ' concept_' + _ALIAS_BY_FORM[re.sub(r'\s+', ' ', m.group())]['id'] + ' ', focus)
    wanted = set(base_terms(canonical))
    # Product/transaction identifiers must occur verbatim; an FOF substring in
    # ABCFOF999 must never be treated as the financial acronym.
    identifiers = sorted(t for t in wanted if not t.startswith('concept_') and
                         re.search(r'[a-z]', t) and re.search(r'\d', t))
    acronyms = sorted(t.casefold() for t in re.findall(r'(?<![A-Za-z0-9_])[A-Z]{2,12}(?![A-Za-z0-9_])',
                                                    unicodedata.normalize('NFKC', query)))
    unknown_acronyms = sorted(set(acronyms) & wanted)
    return {'original': query, 'focus': focus, 'terms': wanted,
            'anchors': {'concept_' + x for x in matched} | set(unknown_acronyms),
            'required_anchors': {'concept_' + x for x in matched if x in STRICT_ALIASES} | set(unknown_acronyms),
            'identifiers': identifiers, 'matched_aliases': matched,
            'comparison': bool(re.search(r'(?:与|和).*(?:区别|差异|不同)|\bvs\b|\bversus\b',query,re.I)),
            'definition': bool(re.search(r'是什么|什么是|定义|含义|意思|what is|what are|definition', query, re.I))}


def body_text(row: dict) -> str:
    text = row.get('text', row.get('content', ''))
    section = row.get('section', '')
    # A real subsection belongs to its paragraphs. A whole-document title must
    # not make every unrelated page a match (e.g. a FOF report's boilerplate).
    return (section + '\n' if section and section != row.get('title', '') else '') + text


def evidence_match(plan: dict, text: str, *, token_set=None) -> dict:
    actual = set(terms(text)) if token_set is None else set(token_set)
    wanted = plan['terms']; hits = wanted & actual
    coverage = len(hits) / max(1, len(wanted))
    anchors = plan['anchors']; anchor_hits = anchors & actual
    required = plan.get('required_anchors', anchors)
    identifiers_ok = all(identifier in actual for identifier in plan['identifiers'])
    # A named concept may be explained in very different wording. Its direct
    # occurrence is useful evidence even when the question has extra facets;
    # report that as topic-related evidence, never as semantic correctness.
    anchored = bool(required & actual)
    lexical_ok = bool(hits) and coverage >= .45 and (len(wanted) < 3 or len(hits) >= 2)
    accepted = bool(wanted) and identifiers_ok and (anchored if required else lexical_ok)
    if text.count('\ufffd') / max(1, len(text)) > .08: accepted = False
    return {'accepted': accepted, 'coverage': round(coverage, 4), 'matched_terms': sorted(hits),
            'matched_anchors': sorted(anchor_hits), 'scope': 'topic_related_not_answer_verification'}


def resolve_followup(query: str, history=()) -> dict:
    """Use a bounded user topic for an explicit follow-up, never an old answer.

    Saved-conversation ownership and revision checks belong to the caller. This
    helper only reads user messages from the history the caller has authorized.
    """
    value = normalize(query)
    follow = bool(re.match(r'^(?:那(?:么)?(?:它|这个|那个|这些|些)?|它|这个|那个|这些|上述|上面|继续|然后|还有呢|再(?:具体|详细)|what about (?:it|that)|and (?:its|their))', value))
    if not follow or len(query) > 180:
        return {'query': query, 'mode': 'current_question', 'used_history': False}
    current = plan_query(query)
    # A new explicitly named topic stands on its own. An actual pronoun plus a
    # facet ("那它怎么筛选基金经理") still needs the earlier user topic.
    explicit_pronoun=bool(re.match(r'^(?:那(?:么)?)?(?:它|这个|那个|这些)(?:的|怎么|如何|有|该|会|能|呢|为什么|还|要|所|是|和|与|[？?])',value))
    if (current['required_anchors'] or current['identifiers']) and not explicit_pronoun:
        return {'query': query, 'mode': 'current_question', 'used_history': False}
    prior = ''
    for message in reversed(list(history)[-8:]):
        if not isinstance(message, dict) or message.get('role') != 'user': continue
        candidate = str(message.get('content', ''))[:600]
        if not candidate.strip(): continue
        if re.match(r'^(?:那它|它|这个|那个|这些|继续|还有呢)', normalize(candidate)): continue
        prior = focus_query(candidate)[:240]
        if prior: break
    if not prior:
        return {'query': query, 'mode': 'current_question', 'used_history': False}
    return {'query': prior + '\n追问：' + query, 'mode': 'explicit_followup_last_user', 'used_history': True}
