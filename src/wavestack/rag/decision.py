"""V1.2 story 8 (CAP-6): the System One decision layer of the RAG workshop.

What a decision is made with, never how the workshop shows it (`rag/lab.py` does):

- `NliClassifier`: `deberta_xsmall` (MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33, the
  ONNX quantized export), a zero-shot NLI run by `onnxruntime` and `tokenizers` (extra
  `decision`, no torch), the local default of the router and of the grounding check chosen by
  the bench of story 2 (`rapport-banc-system-one.md`). Its files are declared in
  `wavestack.toml` (`[rag_lab.decision.classifier]`) and downloaded by the application.
- `DecisionApi`: the decision API (OpenRouter's `/api/alpha/decisions`, the bench's endpoint),
  not a chat model: `noul` (the probability of « yes »), `choice` (a label, its probabilities
  and a confidence) and `score` (a grid of 2 to 10 levels). Its key is read from
  `OPENROUTER_API_KEY` (or the user's `HKCU\\Environment`), never shown nor written; only the
  host of `ALLOWED_HOSTS` is called. The shape of `choice` and `score` follows the alpha
  documentation (architectures.md) and was never called by the bench: it is read leniently.
- `decide`: the cascade rule. At or above the threshold the classifier decides alone; under
  it, the classifier refuses (the passage dropped, the sentence not grounded, its strategy kept
  with « sous le seuil ») or, with the cascade on, the SLM judge decides.

The instructions are the bench's exact wording (report, section 7), in fr, en and de.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ENDPOINT_URL = "https://openrouter.ai/api/alpha/decisions"
ALLOWED_HOSTS = ("openrouter.ai",)
KEY_ENV = "OPENROUTER_API_KEY"
QUESTION_KEY = "decision"
REQUEST_TIMEOUT_S = 30
PREMISE_SEP = "\n\n---\n\n"  # between the passages of a grounding premise (the bench's)
MAX_TOKENS = 512  # what the NLI classifier reads of a pair (the premise is cut first)
SCORE_LEVELS = (2, 10)
LANGS = ("fr", "en", "de")
TASKS = ("filter", "grounding")
AUTHORS = ("classifier", "judge")

# Report, section 7: the instructions of the bench, word for word.
INSTRUCTIONS: dict[str, dict[str, str]] = {
    "filter": {
        "fr": (
            "Ce passage contient-il l'information qui permet de répondre à la question ? "
            "Réponds oui seulement si le passage suffit à répondre."
        ),
        "en": (
            "Does this passage contain the information needed to answer the question? "
            "Answer yes only if the passage is enough to answer."
        ),
        "de": (
            "Enthält dieser Abschnitt die Information, die zur Beantwortung der Frage nötig "
            "ist? Antworte nur dann mit ja, wenn der Abschnitt zur Antwort ausreicht."
        ),
    },
    "grounding": {
        "fr": (
            "L'affirmation est-elle entièrement étayée par les passages ? Réponds non si elle "
            "ajoute ou change un fait, un chiffre ou une condition."
        ),
        "en": (
            "Is the claim fully supported by the passages? Answer no if it adds or changes a "
            "fact, a number or a condition."
        ),
        "de": (
            "Wird die Aussage von den Abschnitten vollständig gestützt? Antworte mit nein, "
            "wenn sie eine Tatsache, eine Zahl oder eine Bedingung hinzufügt oder ändert."
        ),
    },
}
# The bench's NLI hypothesis of the filter (the grounding's hypothesis is the claim itself).
NLI_HYPOTHESIS = {
    "fr": "Ce passage répond à la question : {q}",
    "en": "This passage answers the question: {q}",
    "de": "Dieser Abschnitt beantwortet die Frage: {q}",
}
YES_NO = {"fr": ("oui", "non"), "en": ("yes", "no"), "de": ("ja", "nein")}
# The judge has no grammar here (the workshop's model is asked as for any short task): one word.
JUDGE_SUFFIX = {
    "fr": "Réponds par un seul mot : oui ou non.",
    "en": "Answer with one word: yes or no.",
    "de": "Antworte mit einem Wort: ja oder nein.",
}

# The router's strategies: the search presets of the workshop, and the kinds each runs. The
# router only drops stages the chain has; it never adds one.
STRATEGIES = ("dense", "hybrid", "rerank")
STRATEGY_KINDS: dict[str, tuple[str, ...]] = {
    "dense": ("vector_search",),
    "hybrid": ("vector_search", "lexical_search", "fusion"),
    "rerank": ("vector_search", "rerank"),
}
# Not measured by the bench (story 2 measured the filter and the grounding only): proposals of
# the development, to review (spec of story 8). Zero-shot: premise the question, one hypothesis
# per strategy, the entailment logits compared.
ROUTER_HYPOTHESES: dict[str, dict[str, str]] = {
    "fr": {
        "dense": "Cette question se formule avec d'autres mots que ceux du document.",
        "hybrid": "Cette question cite un nom, un sigle, un code ou un nombre exact.",
        "rerank": "Cette question demande un détail précis parmi des passages proches.",
    },
    "en": {
        "dense": "This question is worded differently from the document.",
        "hybrid": "This question quotes an exact name, acronym, code or number.",
        "rerank": "This question asks for a precise detail among similar passages.",
    },
    "de": {
        "dense": "Diese Frage ist mit anderen Worten formuliert als das Dokument.",
        "hybrid": "Diese Frage nennt einen genauen Namen, ein Kürzel, einen Code oder eine Zahl.",
        "rerank": "Diese Frage verlangt ein genaues Detail unter ähnlichen Abschnitten.",
    },
}
ROUTER_INSTRUCTIONS = {
    "fr": "Quelle stratégie de recherche convient le mieux à cette question ?",
    "en": "Which search strategy suits this question best?",
    "de": "Welche Suchstrategie passt am besten zu dieser Frage?",
}
ROUTER_JUDGE_SUFFIX = {
    "fr": "Réponds par un seul mot parmi : {options}.",
    "en": "Answer with one word among: {options}.",
    "de": "Antworte mit einem Wort aus: {options}.",
}
_SENTENCES = re.compile(r"(?<=[.!?…])\s+|\n+")
_WORD = re.compile(r"[\w'-]+")


class DecisionError(Exception):
    """A decision that could not be made (the API refused, the cap reached): `text` says why
    (a `Message` or a string, never the key)."""

    def __init__(self, text: Any) -> None:
        super().__init__(str(text))
        self.text = text


# ---------- the cascade rule ----------


@dataclass
class Decision:
    """One decision: what was decided (`subject_text`), the verdict (`keep`/`drop`,
    `grounded`/`not_grounded`, or a strategy), the classifier's probability (of « yes », or of
    the strategy it chose; `None` when it failed), the threshold, who decided, whether the
    probability was under the threshold, and what the judge answered when it was asked."""

    subject_text: str
    verdict: str
    probability: float | None
    threshold: float
    author: str = "classifier"
    below: bool = False
    judge_text: str | None = None
    note: str | None = None  # `cascade_off`, `judge_unreadable`, `judge_unavailable`, `error`
    truncated: bool = False
    probabilities: dict[str, float] = field(default_factory=dict)
    chunk_id: int | None = None
    doc_id: str | None = None


def decide_binary(
    subject: str,
    probability: float | None,
    threshold: float,
    cascade: bool,
    judge: Callable[[], tuple[bool | None, str | None]] | None,
    yes: str,
    no: str,
) -> Decision:
    """At or above `threshold`, the classifier says yes alone; under it (or without a
    probability), it says no, unless the cascade asks the judge (`judge()`: its verdict, `None`
    when unreadable, and its raw answer). A judge that cannot be asked or reads badly leaves
    the classifier's no, with the reason in `note`."""
    if probability is not None and probability >= threshold:
        return Decision(subject, yes, probability, threshold)
    decision = Decision(subject, no, probability, threshold, below=True)
    if probability is None:
        decision.note = "error"
    if not cascade:
        decision.note = decision.note or "cascade_off"
        return decision
    if judge is None:
        decision.note = "judge_unavailable"
        return decision
    verdict, raw = judge()
    decision.judge_text = raw
    if verdict is None:  # no answer at all: the judge could not be asked (no model loaded)
        decision.note = "judge_unreadable" if raw is not None else "judge_unavailable"
        return decision
    decision.author, decision.verdict, decision.note = "judge", yes if verdict else no, None
    return decision


def decide_choice(
    subject: str,
    probabilities: Mapping[str, float],
    threshold: float,
    cascade: bool,
    judge: Callable[[], tuple[str | None, str | None]] | None,
) -> Decision:
    """The classifier's most probable label, alone at or above `threshold`; under it, kept
    (« sous le seuil ») unless the cascade asks the judge for a label among the same ones."""
    best = max(probabilities, key=lambda k: (probabilities[k], -list(probabilities).index(k)))
    p = probabilities[best]
    decision = Decision(subject, best, p, threshold, probabilities=dict(probabilities))
    if p >= threshold:
        return decision
    decision.below = True
    if not cascade:
        decision.note = "cascade_off"
        return decision
    if judge is None:
        decision.note = "judge_unavailable"
        return decision
    label, raw = judge()
    decision.judge_text = raw
    if label is None:
        decision.note = "judge_unreadable" if raw is not None else "judge_unavailable"
        return decision
    decision.author, decision.verdict = "judge", label
    return decision


def judge_word(answer: str, lang: str) -> bool | None:
    """The judge's yes or no: its first word, in `lang` (or English), else `None`."""
    words = _WORD.findall(answer.strip().lower())
    if not words:
        return None
    first = words[0]
    for yes, no in (YES_NO.get(lang, YES_NO["en"]), YES_NO["en"]):
        if first == yes:
            return True
        if first == no:
            return False
    return None


def judge_label(answer: str, labels: Sequence[str]) -> str | None:
    """The first of `labels` the judge's answer names as a word, else `None`."""
    words = _WORD.findall(answer.strip().lower())
    return next((w for w in words if w in labels), None)


def sentences(text: str, limit: int) -> tuple[list[str], int]:
    """The answer's sentences (at most `limit`), and how many there were in all."""
    found = [s.strip() for s in _SENTENCES.split(text) if s and s.strip()]
    return found[:limit], len(found)


def softmax(values: Sequence[float]) -> list[float]:
    top = max(values)
    exps = [math.exp(v - top) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


# ---------- the local classifier (extra `decision`) ----------


def installed() -> bool:
    """`onnxruntime` and `tokenizers` importable (extra `decision`), without importing them."""
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in ("onnxruntime", "tokenizers"))


class NliClassifier:
    """deberta_xsmall's zero-shot NLI, opened from its three files (config, tokenizer, ONNX).
    `p(entailment)` of (premise, hypothesis), the premise cut first past `MAX_TOKENS`."""

    def __init__(self, config_path: Path, tokenizer_path: Path, onnx_path: Path) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        cfg = json.loads(Path(config_path).read_text("utf-8"))
        self._entail = next(
            int(k) for k, v in cfg["id2label"].items() if str(v).lower().startswith("entail")
        )
        self._np = np
        self._tok = Tokenizer.from_file(str(tokenizer_path))
        self._tok.enable_truncation(max_length=MAX_TOKENS)
        self._tok.no_padding()
        self._session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        self._names = {i.name for i in self._session.get_inputs()}

    def _logits(self, premise: str, hypothesis: str) -> tuple[list[float], bool]:
        enc = self._tok.encode(premise, hypothesis)
        feeds = {
            "input_ids": [enc.ids],
            "attention_mask": [enc.attention_mask],
            "token_type_ids": [enc.type_ids],
        }
        arrays = {
            k: self._np.array(v, dtype=self._np.int64) for k, v in feeds.items() if k in self._names
        }
        logits = self._session.run(None, arrays)[0].tolist()[0]
        return [float(x) for x in logits], bool(enc.overflowing)

    def entailment(self, premise: str, hypothesis: str) -> tuple[float, bool]:
        logits, cut = self._logits(premise, hypothesis)
        return softmax(logits)[self._entail], cut

    def noul(self, task: str, lang: str, state: Mapping[str, str]) -> tuple[float, bool]:
        """The bench's reading: the filter's hypothesis is « this passage answers the
        question », the grounding's is the claim itself."""
        if task == "filter":
            q = NLI_HYPOTHESIS.get(lang, NLI_HYPOTHESIS["en"]).format(q=state["question"])
            return self.entailment(state["passage"], q)
        return self.entailment(state["premise"], state["claim"])

    def choice(self, question: str, options: Mapping[str, str]) -> tuple[dict[str, float], bool]:
        """Zero-shot: one hypothesis per label, the entailment logits softmaxed against each
        other (the single-label zero-shot of the Hugging Face pipeline)."""
        logits, cut = [], False
        for hypothesis in options.values():
            row, was_cut = self._logits(question, hypothesis)
            logits.append(row[self._entail])
            cut = cut or was_cut
        return dict(zip(options, softmax(logits), strict=True)), cut

    def close(self) -> None:
        self._session = None


# ---------- the decision API ----------


class ForbiddenHost(DecisionError):
    pass


def check_host(url: str) -> None:
    host = urlsplit(url).hostname
    if host not in ALLOWED_HOSTS:
        raise ForbiddenHost(f"hôte non autorisé : {host!r}")


def read_registry_key(name: str = KEY_ENV) -> str | None:  # pragma: no cover - Windows only
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            value, _ = winreg.QueryValueEx(k, name)
        return str(value) or None
    except OSError:
        return None


def read_key(
    environ: Mapping[str, str] | None = None,
    registry: Callable[[str], str | None] | None = None,
    name: str = KEY_ENV,
) -> str | None:
    """The key from the variable, else the user's registry; never printed anywhere."""
    environ = os.environ if environ is None else environ
    registry = registry or read_registry_key
    return environ.get(name) or registry(name) or None


def redact(text: object, key: str | None) -> str:
    out = str(text)
    return out.replace(key, "***") if key else out


@dataclass
class ApiAnswer:
    """What the API answered, its white list only: the value (`noul`: a probability; `choice`:
    a label; `score`: a level), the probabilities by label or level, the confidence, the
    tokens read, the cost in dollars (`None`: not given) and the model's version."""

    value: Any
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None
    input_tokens: int | None = None
    cost_usd: float | None = None
    model_returned: str | None = None
    latency_ms: int = 0


def _number(value: Any) -> float | None:
    ok = isinstance(value, int | float) and not isinstance(value, bool)
    return float(value) if ok and math.isfinite(value) else None


def _probabilities(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        p = _number(value)
        if p is not None and 0 <= p <= 1:
            out[str(key)] = p
    return out


def error_summary(status: int, payload: dict | None) -> str:
    """Status and the `error.code` / `error.message` of the body, nothing else."""
    out = f"HTTP {status}"
    err = (payload or {}).get("error")
    if isinstance(err, dict):
        code, message = err.get("code"), err.get("message")
        if isinstance(code, int | str) and not isinstance(code, bool):
            out += f" {code}"
        if isinstance(message, str):
            out += f" : {message}"
    elif isinstance(err, str):
        out += f" : {err}"
    return " ".join(out.split())[:200]


class DecisionApi:
    """One POST per decision. `http`: the client (the application's traced one, `net.factory`,
    behind the network guard); else one made by the same factory on `transport` (a fake in the
    tests; AD-15: no HTTP client outside `net.factory`). The key only ever lives in the
    Authorization header of the request."""

    def __init__(
        self,
        key: str,
        transport: Any = None,
        url: str = ENDPOINT_URL,
        clock: Callable[[], float] = time.perf_counter,
        http: Any = None,
    ) -> None:
        check_host(url)
        self._key, self._url, self._clock = key, url, clock
        if http is None:
            from wavestack.net.factory import create_client  # redirects never followed

            http = create_client(timeout=REQUEST_TIMEOUT_S, transport=transport)
        self._http = http

    @staticmethod
    def body(model: str, state: Mapping[str, Any], question: dict[str, Any]) -> dict[str, Any]:
        return {"model": model, "state": dict(state), "questions": {QUESTION_KEY: question}}

    def _post(self, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], int]:
        check_host(self._url)
        started = self._clock()
        try:
            r = self._http.post(
                self._url,
                content=json.dumps(body, ensure_ascii=False).encode(),
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
            )
        except Exception as exc:  # noqa: BLE001 - said in the stage, never raised as is
            raise DecisionError(redact(f"{type(exc).__name__} : {exc}", self._key)[:200]) from None
        latency = int((self._clock() - started) * 1000)
        try:
            payload = r.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            payload = None
        if r.status_code >= 400 or payload is None:
            raise DecisionError(redact(error_summary(r.status_code, payload), self._key))
        answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
        answer = answers.get(QUESTION_KEY)
        if not isinstance(answer, dict):
            raise DecisionError(f"HTTP {r.status_code} : réponse sans « answers.{QUESTION_KEY} »")
        return payload, answer, latency

    @staticmethod
    def _answer(payload: dict[str, Any], answer: dict[str, Any], value: Any, latency: int):
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        tokens = usage.get("input_tokens")
        return ApiAnswer(
            value=value,
            probabilities=_probabilities(answer.get("probabilities")),
            confidence=_number(answer.get("confidence")),
            input_tokens=tokens
            if isinstance(tokens, int) and not isinstance(tokens, bool)
            else None,
            cost_usd=_number(usage.get("cost")),
            model_returned=payload.get("model") if isinstance(payload.get("model"), str) else None,
            latency_ms=latency,
        )

    def noul(self, model: str, state: Mapping[str, Any], instructions: str) -> ApiAnswer:
        """The probability of « yes » (`answers.decision.noul`, in [0, 1])."""
        body = self.body(model, state, {"type": "noul", "instructions": instructions})
        payload, answer, latency = self._post(body)
        p = _number(answer.get("noul"))
        if p is None or not 0 <= p <= 1:
            raise DecisionError("réponse « noul » illisible")
        return self._answer(payload, answer, p, latency)

    def choice(
        self, model: str, state: Mapping[str, Any], instructions: str, options: Mapping[str, str]
    ) -> ApiAnswer:
        """A label among `options` (label -> description), its probabilities and confidence;
        the label read from `choice` (or `label`), unknown labels refused."""
        question = {"type": "choice", "instructions": instructions, "options": dict(options)}
        payload, answer, latency = self._post(self.body(model, state, question))
        label = answer.get("choice", answer.get("label"))
        if not isinstance(label, str) or label not in options:
            raise DecisionError("réponse « choice » illisible")
        result = self._answer(payload, answer, label, latency)
        result.probabilities = {k: v for k, v in result.probabilities.items() if k in options}
        return result

    def score(
        self, model: str, state: Mapping[str, Any], instructions: str, levels: int
    ) -> ApiAnswer:
        """A level from 1 to `levels` (2 to 10), and the probabilities by level."""
        low, high = SCORE_LEVELS
        if not low <= levels <= high:
            raise ValueError(f"levels : de {low} à {high}")
        question = {"type": "score", "instructions": instructions, "levels": levels}
        payload, answer, latency = self._post(self.body(model, state, question))
        level = answer.get("score")
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= levels:
            raise DecisionError("réponse « score » illisible")
        return self._answer(payload, answer, level, latency)

    def close(self) -> None:
        self._http.close()


def choice_probability(answer: ApiAnswer) -> dict[str, float]:
    """The probabilities of a `choice` answer: those given, else the confidence on the label."""
    if answer.probabilities:
        return answer.probabilities
    p = answer.confidence if answer.confidence is not None else 1.0
    return {str(answer.value): p}


class CappedApi:
    """The decision API as a run uses it: each call refused once the session's spend has
    reached its cap (`refusal()`: why, else `None`, checked before anything is sent), and each
    answer's cost handed to `spent` (the session's registry of `consumption_updated`)."""

    def __init__(
        self,
        api: DecisionApi,
        refusal: Callable[[], Any],
        spent: Callable[[ApiAnswer], None],
    ) -> None:
        self._api, self._refusal, self._spent = api, refusal, spent

    def _call(self, method: str, *args: Any) -> ApiAnswer:
        why = self._refusal()
        if why is not None:
            raise DecisionError(why)
        answer = getattr(self._api, method)(*args)
        self._spent(answer)
        return answer

    def noul(self, model: str, state: Mapping[str, Any], instructions: str) -> ApiAnswer:
        return self._call("noul", model, state, instructions)

    def choice(
        self, model: str, state: Mapping[str, Any], instructions: str, options: Mapping[str, str]
    ) -> ApiAnswer:
        return self._call("choice", model, state, instructions, options)

    def score(
        self, model: str, state: Mapping[str, Any], instructions: str, levels: int
    ) -> ApiAnswer:
        return self._call("score", model, state, instructions, levels)
