from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


HOOK_TERMS = {
    "como", "por que", "porque", "segredo", "erro", "nunca", "sempre", "verdade",
    "atenção", "imagine", "descobri", "aprendi", "você", "ninguém", "primeiro", "isso",
    "how", "why", "secret", "mistake", "never", "always", "truth", "imagine", "you",
    "cómo", "por qué", "secreto", "error", "nunca", "siempre", "verdad", "imagina",
}
FILLER_TERMS = {"é", "né", "tipo", "assim", "ahn", "hum", "uh", "um", "like", "you know"}
EMOTION_TERMS = {
    "absurdo", "incrível", "medo", "ódio", "amor", "surpresa", "chocante", "polêmico",
    "problema", "conflito", "risco", "pior", "melhor", "impossível", "ridículo", "engraçado",
    "amazing", "fear", "love", "hate", "shocking", "controversial", "worst", "best",
}
VALUE_TERMS = {
    "passo", "dica", "método", "estratégia", "aprendi", "funciona", "resultado", "explicar",
    "razão", "exemplo", "lesson", "tip", "method", "strategy", "works", "result", "example",
}
PAYOFF_TERMS = {
    "por isso", "então", "resultado", "conclusão", "no fim", "foi assim", "therefore", "so", "result",
}
PROMO_TERMS = {
    "se inscreva", "inscreva-se", "deixa o like", "me segue", "link na bio", "patrocin", "subscribe", "follow me",
}
WEAK_STARTS = {"e", "mas", "aí", "daí", "ele", "ela", "isso", "então", "and", "but", "so", "because"}
STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "é", "em", "um", "uma", "que", "pra", "para",
    "com", "por", "no", "na", "nos", "nas", "se", "eu", "você", "ele", "ela", "isso", "the", "a", "an", "and",
    "to", "of", "in", "is", "it", "that", "you", "this", "for", "on", "with", "as", "at", "be",
}

STYLE_WEIGHTS: dict[str, dict[str, float]] = {
    "auto": {"hook": .18, "context": .14, "completeness": .14, "clarity": .13, "emotion": .09, "novelty": .08, "pacing": .11, "shareability": .08, "boundary": .05},
    "viral": {"hook": .24, "context": .10, "completeness": .10, "clarity": .10, "emotion": .16, "novelty": .09, "pacing": .11, "shareability": .07, "boundary": .03},
    "educational": {"hook": .13, "context": .15, "completeness": .17, "clarity": .18, "emotion": .04, "novelty": .07, "pacing": .09, "shareability": .08, "boundary": .09},
    "podcast": {"hook": .18, "context": .17, "completeness": .16, "clarity": .12, "emotion": .11, "novelty": .07, "pacing": .08, "shareability": .06, "boundary": .05},
    "storytelling": {"hook": .17, "context": .12, "completeness": .18, "clarity": .10, "emotion": .15, "novelty": .08, "pacing": .07, "shareability": .07, "boundary": .06},
    "commentary": {"hook": .19, "context": .14, "completeness": .15, "clarity": .14, "emotion": .11, "novelty": .08, "pacing": .08, "shareability": .06, "boundary": .05},
}


@dataclass(slots=True)
class Candidate:
    candidate_id: int
    start: float
    end: float
    text: str
    local_score: float
    score_breakdown: dict[str, int] = field(default_factory=dict)
    reason: str = ""
    editorial_style: str = "auto"


@dataclass(slots=True)
class Highlight:
    candidate_id: int
    start: float
    end: float
    text: str
    title: str
    score: int
    reason: str
    selection_method: str
    score_breakdown: dict[str, int] = field(default_factory=dict)


def _value(word: Any, name: str, default: Any = None) -> Any:
    if isinstance(word, dict):
        return word.get(name, default)
    return getattr(word, name, default)


def duration_bounds(preset: str) -> tuple[float, float, float]:
    return {
        "short": (15.0, 30.0, 23.0), "15_30": (15.0, 30.0, 23.0),
        "30_45": (30.0, 45.0, 37.0), "medium": (30.0, 60.0, 44.0),
        "30_60": (30.0, 60.0, 44.0), "long": (45.0, 90.0, 65.0),
        "45_90": (45.0, 90.0, 65.0), "auto": (18.0, 75.0, 40.0),
    }.get(preset, (18.0, 75.0, 40.0))


def _sentences(words: list[Any]) -> list[list[Any]]:
    """Build speech units using punctuation and real word gaps.

    Whisper punctuation is not always reliable. A pause is therefore treated as
    a boundary too, while the hard limit is only a safety valve for transcripts
    without punctuation.
    """
    groups: list[list[Any]] = []
    current: list[Any] = []
    for index, word in enumerate(words):
        text = str(_value(word, "word", "")).strip()
        if not text:
            continue
        current.append(word)
        elapsed = float(_value(current[-1], "end", 0)) - float(_value(current[0], "start", 0))
        punctuation = bool(re.search(r"[.!?…][\"')\]]?$", text))
        next_word = words[index + 1] if index + 1 < len(words) else None
        pause = (
            float(_value(next_word, "start", 0)) - float(_value(word, "end", 0))
            if next_word is not None else 0.0
        )
        natural_pause = pause >= 0.72 and len(current) >= 3
        if (punctuation and len(current) >= 3) or natural_pause or elapsed >= 12.0:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _tokens(text: str) -> list[str]:
    return [item for item in re.findall(r"[\wÀ-ÿ]+", text.lower()) if item]


def _stem(token: str) -> str:
    for suffix in ("mente", "ções", "ção", "ando", "endo", "indo", "ados", "adas", "ado", "ada", "ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[:-len(suffix)]
    return token


def _semantic_terms(text: str) -> set[str]:
    return {_stem(token) for token in _tokens(text) if token not in STOPWORDS and len(token) >= 3}


def semantic_similarity(first: str, second: str) -> float:
    a, b = _semantic_terms(first), _semantic_terms(second)
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    jaccard = intersection / max(1, len(a | b))
    containment = intersection / max(1, min(len(a), len(b)))
    first_tokens = [_stem(token) for token in _tokens(first) if token not in STOPWORDS]
    second_tokens = [_stem(token) for token in _tokens(second) if token not in STOPWORDS]
    first_bigrams = set(zip(first_tokens, first_tokens[1:]))
    second_bigrams = set(zip(second_tokens, second_tokens[1:]))
    bigram = (
        len(first_bigrams & second_bigrams) / max(1, min(len(first_bigrams), len(second_bigrams)))
        if first_bigrams and second_bigrams else 0.0
    )
    return min(1.0, max(jaccard, containment * 0.82, bigram * 0.9))


def _infer_style(text: str, requested: str) -> str:
    requested = (requested or "auto").lower()
    if requested != "auto":
        return requested if requested in STYLE_WEIGHTS else "auto"
    normalized = text.lower()
    if sum(term in normalized for term in VALUE_TERMS) >= 2:
        return "educational"
    if sum(term in normalized for term in EMOTION_TERMS) >= 2 or text.count("!") + text.count("?") >= 2:
        return "viral"
    if any(term in normalized for term in ("quando eu", "naquele dia", "depois disso", "foi aí", "eu lembro")):
        return "storytelling"
    return "podcast"


def _score_candidate(text: str, start: float, end: float, style: str) -> tuple[float, dict[str, int], str, str]:
    normalized = re.sub(r"[^\wÀ-ÿ?!%]+", " ", text.lower()).strip()
    tokens = normalized.split()
    duration = max(1.0, end - start)
    density = len(tokens) / duration
    target_density = 2.45
    pacing_factor = max(0.0, 1.0 - min(1.0, abs(density - target_density) / 2.0))
    filler_hits = sum(1 for term in FILLER_TERMS if re.search(rf"\b{re.escape(term)}\b", normalized))
    hook_hits = sum(1 for term in HOOK_TERMS if term in " ".join(tokens[:22]))
    emotion_hits = sum(1 for term in EMOTION_TERMS if term in normalized)
    value_hits = sum(1 for term in VALUE_TERMS if term in normalized)
    payoff = any(term in " ".join(tokens[-30:]) for term in PAYOFF_TERMS)
    promo = any(term in normalized for term in PROMO_TERMS)
    numeric = bool(re.search(r"\b\d+[\d.,%]*\b", normalized))
    question = "?" in text
    exclamation = "!" in text
    complete_end = bool(re.search(r"[.!?…][\"')\]]?$", text.strip()))
    weak_start = bool(tokens and tokens[0] in WEAK_STARTS)
    deictic_start = bool(tokens and tokens[0] in {"ele", "ela", "isso", "esse", "essa", "aquilo", "it", "this", "that"})
    opening = min(1.0, hook_hits / 2 + .55 * question + .35 * exclamation + .25 * numeric)
    unique_ratio = len(set(tokens)) / max(1, len(tokens))
    length_quality = max(0.0, min(1.0, (len(tokens) - 18) / 45))

    breakdown = {
        "hook": int(max(18, min(99, 38 + 46 * opening + 5 * min(2, emotion_hits)))),
        "context": int(max(18, min(99, 84 - 30 * weak_start - 18 * deictic_start + 8 * complete_end + 5 * payoff))),
        "completeness": int(max(18, min(99, 42 + 32 * complete_end + 20 * payoff + 5 * (len(tokens) >= 25)))),
        "clarity": int(max(18, min(99, 54 + 30 * pacing_factor + 10 * length_quality - min(30, filler_hits * 5)))),
        "emotion": int(max(18, min(99, 34 + 17 * min(3, emotion_hits) + 12 * question + 10 * exclamation))),
        "novelty": int(max(18, min(99, 42 + 35 * unique_ratio + 7 * numeric + 4 * min(2, value_hits)))),
        "pacing": int(max(18, min(99, 35 + 55 * pacing_factor - min(18, filler_hits * 3)))),
        "shareability": int(max(18, min(99, 35 + 12 * hook_hits + 10 * emotion_hits + 9 * value_hits + 8 * numeric))),
        "boundary": int(max(18, min(99, 56 + 25 * complete_end - 24 * weak_start - 12 * deictic_start + 10 * payoff))),
    }
    penalty = min(42, int(filler_hits * 2.5 + 25 * promo + 10 * weak_start + (0 if complete_end else 7)))
    resolved_style = _infer_style(text, style)
    weights = STYLE_WEIGHTS.get(resolved_style, STYLE_WEIGHTS["auto"])
    weighted = sum(breakdown[key] * weight for key, weight in weights.items()) - penalty
    breakdown["penalty"] = penalty

    labels = {
        "hook": "gancho forte", "context": "contexto independente", "completeness": "conclusão completa",
        "clarity": "fala clara", "emotion": "carga emocional", "novelty": "ideia distinta",
        "pacing": "ritmo bom", "shareability": "alto potencial de compartilhamento", "boundary": "início e fim naturais",
    }
    strongest = sorted(labels, key=lambda key: breakdown[key], reverse=True)[:3]
    reason = " + ".join(labels[key] for key in strongest).capitalize() + "."
    return round(max(1.0, min(99.0, weighted)), 2), breakdown, reason, resolved_style


def build_candidates(words: Iterable[Any], preset: str = "auto", editorial_style: str = "auto") -> list[Candidate]:
    word_list = list(words)
    if not word_list:
        return []
    groups = _sentences(word_list)
    minimum, maximum, target = duration_bounds(preset)
    candidates: list[Candidate] = []
    candidate_id = 1

    for start_index in range(len(groups)):
        chosen: list[Any] = []
        windows: list[tuple[float, list[Any]]] = []
        for group in groups[start_index:]:
            chosen.extend(group)
            start = float(_value(chosen[0], "start", 0))
            end = float(_value(chosen[-1], "end", start))
            duration = end - start
            if duration > maximum + 3.0:
                break
            if duration >= minimum:
                windows.append((abs(duration - target), list(chosen)))
                if len(windows) >= 3 and duration >= target + 8:
                    break
        for _, selected in sorted(windows, key=lambda item: item[0])[:2]:
            start = float(_value(selected[0], "start", 0))
            end = float(_value(selected[-1], "end", start))
            text = " ".join(str(_value(word, "word", "")).strip() for word in selected).strip()
            score, breakdown, reason, resolved_style = _score_candidate(text, start, end, editorial_style)
            candidates.append(Candidate(candidate_id, start, end, text, score, breakdown, reason, resolved_style))
            candidate_id += 1

    if not candidates:
        start = float(_value(word_list[0], "start", 0))
        end = float(_value(word_list[-1], "end", start))
        text = " ".join(str(_value(word, "word", "")).strip() for word in word_list).strip()
        score, breakdown, reason, resolved_style = _score_candidate(text, start, end, editorial_style)
        candidates.append(Candidate(1, start, end, text, score, breakdown, reason, resolved_style))
    return candidates


def overlap_ratio(first: Candidate | Highlight, second: Candidate | Highlight) -> float:
    overlap = max(0.0, min(first.end, second.end) - max(first.start, second.start))
    shorter = max(0.001, min(first.end - first.start, second.end - second.start))
    return overlap / shorter


TITLE_LEAD_INS = (
    "bem", "bom", "então", "tipo", "assim", "na verdade", "olha", "gente",
    "eu acho que", "acho que", "well", "so", "actually", "you know",
)


def _without_title_lead_in(text: str) -> str:
    cleaned = text.strip(" .,!?:;-\n")
    changed = True
    while cleaned and changed:
        changed = False
        lowered = cleaned.lower()
        for prefix in sorted(TITLE_LEAD_INS, key=len, reverse=True):
            if lowered == prefix or lowered.startswith(prefix + " "):
                cleaned = cleaned[len(prefix):].lstrip(" ,.!?:;-")
                changed = True
                break
    return cleaned


def _compact_title(text: str, max_characters: int = 48, max_words: int = 8) -> str:
    clean = re.sub(r"\s+", " ", text).strip(" .,!?:;-\n")
    if not clean:
        return ""
    words = clean.split()
    selected: list[str] = []
    for word in words:
        candidate = " ".join([*selected, word])
        if selected and (len(selected) >= max_words or len(candidate) > max_characters):
            break
        selected.append(word)
    if not selected:
        selected = [words[0][:max_characters]]
    title = " ".join(selected).rstrip(".,;:")
    if len(selected) < len(words):
        title = title.rstrip("…") + "…"
    title = title[:max_characters].rstrip()
    return title[:1].upper() + title[1:]


def fallback_title(text: str, excluded_titles: Iterable[str] = ()) -> str:
    clean = re.sub(r"\s+", " ", text).strip(" .,!?:;-\n")
    if not clean:
        return "Momento em destaque"
    fragments = [
        _without_title_lead_in(fragment)
        for fragment in re.split(r"(?<=[.!?…])\s+|\s*[,;:]\s*", clean)
        if fragment.strip()
    ]
    words = clean.split()
    fragments.extend(" ".join(words[offset:offset + 9]) for offset in range(0, min(len(words), 27), 7))
    excluded = [value for value in excluded_titles if value]
    first_valid = ""
    for fragment in fragments:
        candidate = _compact_title(fragment)
        if len(candidate.split()) < 2:
            continue
        first_valid = first_valid or candidate
        if any(candidate.casefold() == value.casefold() for value in excluded):
            continue
        if any(semantic_similarity(candidate, value) >= 0.82 for value in excluded):
            continue
        return candidate
    return first_valid or _compact_title(clean) or "Momento em destaque"


class HighlightSelector:
    def __init__(self, settings: Any):
        self.settings = settings
        self.last_stats: dict[str, Any] = {}

    def select(self, words: list[Any], preset: str, count: int, language: str, editorial_style: str = "auto") -> list[Highlight]:
        candidates = build_candidates(words, preset, editorial_style)
        ranked = sorted(candidates, key=lambda item: item.local_score, reverse=True)
        self.last_stats = {"selector_version": 5, "candidate_count": len(candidates), "editorial_style": editorial_style}
        provider = str(self.settings.llm_provider or "heuristic").lower()
        llm_selections: list[Highlight] = []
        if provider not in {"", "none", "heuristic", "local"} and self.settings.llm_model:
            try:
                llm_selections = self._select_with_llm(ranked[:36], count, language, provider)
            except Exception:
                llm_selections = []

        selected = llm_selections[:]
        selected_ids = {item.candidate_id for item in selected}
        remaining = [item for item in ranked if item.candidate_id not in selected_ids]
        while remaining and len(selected) < count:
            def diversity_objective(candidate: Candidate) -> float:
                if not selected:
                    return candidate.local_score
                semantic = max(semantic_similarity(candidate.text, item.text) for item in selected)
                overlap = max(overlap_ratio(candidate, item) for item in selected)
                return candidate.local_score - semantic * 28.0 - overlap * 34.0

            candidate = max(remaining, key=diversity_objective)
            remaining.remove(candidate)
            if len(selected) >= count:
                break
            proposed = Highlight(
                candidate_id=candidate.candidate_id,
                start=candidate.start,
                end=candidate.end,
                text=candidate.text,
                title=fallback_title(candidate.text, [item.title for item in selected]),
                score=int(round(candidate.local_score)),
                reason=candidate.reason,
                selection_method=f"heuristic-v4:{candidate.editorial_style}",
                score_breakdown=candidate.score_breakdown,
            )
            if any(overlap_ratio(proposed, existing) >= 0.42 for existing in selected):
                continue
            if any(semantic_similarity(proposed.text, existing.text) >= 0.68 for existing in selected):
                continue
            selected.append(proposed)
            selected_ids.add(candidate.candidate_id)

        # If strict diversity removed too much, relax semantic dedupe but keep temporal overlap protection.
        if len(selected) < count:
            for candidate in ranked:
                if len(selected) >= count:
                    break
                if candidate.candidate_id in selected_ids:
                    continue
                proposed = Highlight(
                    candidate_id=candidate.candidate_id, start=candidate.start, end=candidate.end,
                    text=candidate.text, title=fallback_title(candidate.text, [item.title for item in selected]), score=int(round(candidate.local_score)),
                    reason=candidate.reason, selection_method=f"heuristic-v4:{candidate.editorial_style}",
                    score_breakdown=candidate.score_breakdown,
                )
                if all(overlap_ratio(proposed, existing) < 0.42 for existing in selected):
                    selected.append(proposed)
                    selected_ids.add(candidate.candidate_id)
        result = sorted(selected[:count], key=lambda item: item.score, reverse=True)
        used_titles: list[str] = []
        for item in result:
            compact = _compact_title(item.title)
            if not compact or any(
                compact.casefold() == existing.casefold() or semantic_similarity(compact, existing) >= 0.90
                for existing in used_titles
            ):
                compact = fallback_title(item.text, used_titles)
            item.title = compact or "Momento em destaque"
            used_titles.append(item.title)
        self.last_stats["selected_count"] = len(result)
        self.last_stats["selected_scores"] = [item.score for item in result]
        return result

    def _select_with_llm(self, candidates: list[Candidate], count: int, language: str, provider: str) -> list[Highlight]:
        import httpx
        compact = [{
            "candidate_id": item.candidate_id, "start": round(item.start, 2), "end": round(item.end, 2),
            "local_score": item.local_score, "score_breakdown": item.score_breakdown,
            "transcript": item.text[:1800],
        } for item in candidates]
        prompt = (
            "Você é o editor do SnowTV. Escolha trechos autossuficientes para Shorts. Priorize gancho, clareza, "
            "conclusão natural e diversidade. Não invente fatos. Retorne somente JSON no formato "
            '{"selections":[{"candidate_id":1,"title":"...","score":90,"reason":"..."}]}. '
            f"Idioma: {language}. Escolha no máximo {count}. Candidatos:\n" + json.dumps(compact, ensure_ascii=False)
        )
        if provider == "ollama":
            response = httpx.post(
                self.settings.llm_base_url.rstrip("/") + "/api/chat",
                json={"model": self.settings.llm_model, "stream": False, "format": "json", "messages": [{"role": "user", "content": prompt}]},
                timeout=self.settings.llm_timeout_seconds,
            )
            response.raise_for_status(); content = response.json()["message"]["content"]
        else:
            headers = {"Content-Type": "application/json"}
            if self.settings.llm_api_key:
                headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
            response = httpx.post(
                self.settings.llm_base_url.rstrip("/") + "/chat/completions", headers=headers,
                json={"model": self.settings.llm_model, "temperature": 0.2, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": prompt}]},
                timeout=self.settings.llm_timeout_seconds,
            )
            response.raise_for_status(); content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip())
        by_id = {candidate.candidate_id: candidate for candidate in candidates}
        selected: list[Highlight] = []
        for item in parsed.get("selections", []):
            candidate = by_id.get(int(item.get("candidate_id", -1)))
            if not candidate:
                continue
            highlight = Highlight(
                candidate_id=candidate.candidate_id, start=candidate.start, end=candidate.end, text=candidate.text,
                title=_compact_title(str(item.get("title") or fallback_title(candidate.text))),
                score=max(1, min(100, int(math.floor(float(item.get("score", candidate.local_score)))))),
                reason=str(item.get("reason") or "Seleção editorial da IA.")[:240], selection_method="llm",
                score_breakdown=candidate.score_breakdown,
            )
            if all(overlap_ratio(highlight, existing) < .34 and semantic_similarity(highlight.text, existing.text) < .56 for existing in selected):
                selected.append(highlight)
        return selected


def highlight_as_dict(highlight: Highlight) -> dict[str, Any]:
    return asdict(highlight)
