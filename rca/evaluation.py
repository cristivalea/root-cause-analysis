"""Evaluation of the two RAG parts of the application with RAGAS (explained in ragas_project.md).

1. The search: does ChromaDB bring back the past incidents and RCAs that should be found?
   Measured on data/evaluation/retrieval_questions.json with the RAGAS metrics that compare
   ids (IDBasedContextRecall, IDBasedContextPrecision). No LLM is involved, so the numbers are
   the same on every run. The same questions also go through a plain keyword search, the way a
   person searches by hand, to compare the two.
2. The hypotheses: does every hypothesis say only what its cited evidence says?
   Measured with the RAGAS Faithfulness metric, where an LLM (the judge) splits the hypothesis
   into statements and checks each one against the evidence.

The module only reads: it never changes the application data. Scripts and tests call these
functions; printing and writing files is left to scripts/evaluate_ragas.py.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sqlite3
import warnings
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Literal

# RAGAS sends anonymous usage statistics unless told not to. Set before ragas is imported.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from ragas import SingleTurnSample  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402
from ragas.llms.base import InstructorBaseRagasLLM  # noqa: E402
from ragas.metrics.collections import Faithfulness  # noqa: E402

with warnings.catch_warnings():
    # RAGAS 0.4 says these moved to ragas.metrics.collections, but they are not there yet.
    warnings.simplefilter("ignore", DeprecationWarning)
    from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall  # noqa: E402

from rca import judge, rag  # noqa: E402
from rca.config import DB_PATH, ROOT_DIR  # noqa: E402
from rca.models import RCARecord  # noqa: E402

QUESTIONS_PATH = ROOT_DIR / "data" / "evaluation" / "retrieval_questions.json"
ANSWER_KEY_PATH = ROOT_DIR / "data" / "evaluation" / "answer_key.json"
RCA_FOLDER = ROOT_DIR / "data" / "knowledge_base" / "rcas"

# The same number of results the investigation asks for (MAX_SIMILAR_INCIDENTS, MAX_PAST_RCAS).
DEFAULT_LIMIT = 5

# The judge is the larger model: in a test, gpt-oss-20b scored a fully supported answer 0.5
# three times out of three, gpt-oss-120b scored it 1.0 every time. A Gemini model can be chosen
# with RAGAS_JUDGE_MODEL (rca/judge.py), but its free tier allows only about 20 requests a day per
# model, and Faithfulness needs two or three requests for every hypothesis.
JUDGE_MODEL = os.getenv("RAGAS_JUDGE_MODEL", "openai/gpt-oss-120b")
JUDGE_MAX_TOKENS = 4096

Collection = Literal["historical_incidents", "historical_rcas"]
Method = Literal["semantic", "keyword"]

# Which list of the question holds the right answer for each collection.
RELEVANT_FIELD: dict[str, str] = {
    "historical_incidents": "relevant_incidents",
    "historical_rcas": "relevant_rcas",
}
COLLECTIONS: tuple[Collection, ...] = ("historical_incidents", "historical_rcas")

# Short common words a person would not type in a search box.
STOPWORDS = {
    "after", "again", "also", "and", "are", "during", "every", "fail", "fails", "for", "from",
    "into", "issue", "issues", "more", "not", "on", "some", "than", "that", "the", "then",
    "this", "when", "with", "without",
}


# --------------------------------------------------------------------------------------
# Part 1: the search
# --------------------------------------------------------------------------------------


@dataclass
class RetrievalResult:
    """One question searched in one collection: what came back and its scores."""

    question_id: str
    incident_id: str
    collection: Collection
    method: Method
    max_distance: float | None
    retrieved: list[str]
    relevant: list[str]
    misleading_found: list[str]
    recall: float | None  # None when the question has no right answer for this collection
    precision: float | None  # None when the search brought nothing back

    @property
    def expects_nothing(self) -> bool:
        """The right answer is an empty list: there is no useful past record."""
        return not self.relevant


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def semantic_candidates(question: dict, collection: Collection, limit: int = DEFAULT_LIMIT) -> list[tuple[str, float]]:
    """The closest records with their distance, before any threshold: (id, distance), closest first."""
    results = rag.query_collection(
        collection,
        question["query"],
        limit=limit,
        before_timestamp=int(_timestamp(question["before"]).timestamp()),
        max_distance=None,
    )
    return [(item["metadata"].get("incident_id") or item["metadata"].get("document_id") or item["id"], item["score"])
            for item in results]


def apply_threshold(candidates: list[tuple[str, float]], max_distance: float | None) -> list[str]:
    """Keep the records close enough. The same as passing the threshold to the search: the
    threshold only cuts the end of a list sorted by distance."""
    return [record_id for record_id, distance in candidates if max_distance is None or distance <= max_distance]


def semantic_search(question: dict, collection: Collection, limit: int = DEFAULT_LIMIT,
                    max_distance: float | None = rag.DEFAULT_MAX_DISTANCE) -> list[str]:
    """The search the application does: ChromaDB, by meaning, only records older than the incident."""
    return apply_threshold(semantic_candidates(question, collection, limit), max_distance)


def keywords(text: str) -> list[str]:
    """The words a person would type in a search box: the words of the incident title."""
    title = text.split("|")[0]
    words = re.findall(r"[a-z0-9]+", title.lower())
    return list(dict.fromkeys(word for word in words if len(word) >= 3 and word not in STOPWORDS))


def _rank_by_keywords(candidates: list[tuple[str, str, float]], words: list[str], limit: int) -> list[str]:
    """candidates are (id, text, time). The more title words a record contains, the higher it ranks;
    on a tie the newer record comes first, like a ticket list sorted by date."""
    scored = []
    for record_id, text, moment in candidates:
        lowered = text.lower()
        hits = sum(1 for word in words if re.search(rf"\b{re.escape(word)}\b", lowered))
        if hits:
            scored.append((-hits, -moment, record_id))
    return [record_id for _, _, record_id in sorted(scored)[:limit]]


def keyword_search(question: dict, collection: Collection, limit: int = DEFAULT_LIMIT,
                   db_path: Path = DB_PATH, rca_folder: Path = RCA_FOLDER) -> list[str]:
    """A plain search by words, as a person does it by hand in the ticket tool.

    It looks for the words of the incident title in the text of older records. It does not
    understand meaning: "connection pool exhausted" and "no free database connections" share no
    word, so it cannot match them.
    """
    words = keywords(question["query"])
    before = _timestamp(question["before"]).timestamp()
    candidates: list[tuple[str, str, float]] = []

    if collection == "historical_incidents":
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            rows = connection.execute("SELECT incident_id, detected_at, payload FROM incidents").fetchall()
        for incident_id, detected_at, payload in rows:
            moment = _timestamp(detected_at).timestamp()
            if moment < before:
                incident = json.loads(payload)
                candidates.append((incident_id, f"{incident['title']} {incident['description']}", moment))
    else:
        for path in sorted(rca_folder.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            match = re.search(r"\*\*Completion Date:\*\*\s*(\S+)", text)
            if match and _timestamp(match.group(1)).timestamp() < before:
                candidates.append((path.stem, text, _timestamp(match.group(1)).timestamp()))

    return _rank_by_keywords(candidates, words, limit)


def _score(metric, retrieved: list[str], relevant: list[str]) -> float | None:
    """One RAGAS id metric on one sample, or None when the score has no meaning: recall when
    there is nothing to find, precision when nothing came back. RAGAS would print a warning
    and return NaN for these, so they are answered here."""
    if (isinstance(metric, IDBasedContextRecall) and not relevant) or (
            isinstance(metric, IDBasedContextPrecision) and not retrieved):
        return None
    sample = SingleTurnSample(retrieved_context_ids=retrieved, reference_context_ids=relevant)
    value = asyncio.run(metric.single_turn_ascore(sample))
    return None if value is None or math.isnan(value) else float(value)


def score_retrieval(question: dict, collection: Collection, method: Method, retrieved: list[str],
                    max_distance: float | None) -> RetrievalResult:
    relevant = list(question[RELEVANT_FIELD[collection]])
    return RetrievalResult(
        question_id=question["question_id"],
        incident_id=question["incident_id"],
        collection=collection,
        method=method,
        max_distance=max_distance if method == "semantic" else None,
        retrieved=retrieved,
        relevant=relevant,
        misleading_found=[item for item in retrieved if item in question.get("misleading_records", [])],
        recall=_score(IDBasedContextRecall(), retrieved, relevant),
        precision=_score(IDBasedContextPrecision(), retrieved, relevant),
    )


def evaluate_retrieval(questions: list[dict], method: Method = "semantic",
                       max_distance: float | None = rag.DEFAULT_MAX_DISTANCE,
                       limit: int = DEFAULT_LIMIT, db_path: Path = DB_PATH) -> list[RetrievalResult]:
    """Every question, searched in both collections with one method."""
    results = []
    for question in questions:
        for collection in COLLECTIONS:
            if method == "semantic":
                retrieved = semantic_search(question, collection, limit, max_distance)
            else:
                retrieved = keyword_search(question, collection, limit, db_path)
            results.append(score_retrieval(question, collection, method, retrieved, max_distance))
    return results


def evaluate_thresholds(questions: list[dict], thresholds: list[float],
                        limit: int = DEFAULT_LIMIT) -> list[RetrievalResult]:
    """The semantic search scored for several thresholds. Each question is searched once and
    every threshold is applied to the same results, so Ollama is asked once per question."""
    results = []
    for question in questions:
        for collection in COLLECTIONS:
            candidates = semantic_candidates(question, collection, limit)
            for threshold in thresholds:
                retrieved = apply_threshold(candidates, threshold)
                results.append(score_retrieval(question, collection, "semantic", retrieved, threshold))
    return sorted(results, key=lambda item: item.max_distance)


@dataclass
class RetrievalSummary:
    """The averages of one method on one collection."""

    method: Method
    collection: Collection
    max_distance: float | None
    questions: int
    recall: float | None  # average over the questions that have a right answer
    precision: float | None  # average over the searches that brought something back
    empty_expected: int  # questions whose right answer is "nothing"
    empty_correct: int  # ... and the search really brought nothing back
    misleading: int  # searches that brought back a record planted to mislead


def _average(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(mean(present), 3) if present else None


def summarize_retrieval(results: list[RetrievalResult]) -> list[RetrievalSummary]:
    summaries = []
    groups: dict[tuple, list[RetrievalResult]] = {}
    for result in results:
        groups.setdefault((result.method, result.collection, result.max_distance), []).append(result)
    for (method, collection, max_distance), group in groups.items():
        expects_nothing = [item for item in group if item.expects_nothing]
        summaries.append(RetrievalSummary(
            method=method,
            collection=collection,
            max_distance=max_distance,
            questions=len(group),
            recall=_average([item.recall for item in group]),
            precision=_average([item.precision for item in group]),
            empty_expected=len(expects_nothing),
            empty_correct=sum(1 for item in expects_nothing if not item.retrieved),
            misleading=sum(1 for item in group if item.misleading_found),
        ))
    return summaries


# --------------------------------------------------------------------------------------
# Part 2: the hypotheses
# --------------------------------------------------------------------------------------


@dataclass
class FaithfulnessSample:
    """One hypothesis and the evidence it cites, in the shape the Faithfulness metric reads."""

    rca_id: str
    incident_id: str
    hypothesis_id: str
    user_input: str
    response: str
    contexts: list[str]
    cited: list[str]


@dataclass
class Verdict:
    statement: str
    supported: bool
    reason: str


@dataclass
class FaithfulnessResult:
    sample: FaithfulnessSample
    score: float | None  # None when the judge found no statement to check
    verdicts: list[Verdict] = field(default_factory=list)


def faithfulness_samples(record: RCARecord) -> list[FaithfulnessSample]:
    """One sample per hypothesis of the RCA. The context is the evidence the hypothesis cites,
    for and against it, and nothing else: the question is whether the hypothesis stays inside
    its own evidence. The evidence against is included because a hypothesis also talks about it
    ("the failover happened before the errors"); without it those true sentences were judged
    unsupported in the first run."""
    evidence = {item.evidence_id: item for item in record.evidence}
    samples = []
    for hypothesis in record.hypotheses:
        if not any(evidence_id in evidence for evidence_id in hypothesis.supporting_evidence):
            continue  # no evidence for it; the guardrail does not let this happen
        cited = [evidence_id for evidence_id in dict.fromkeys(hypothesis.supporting_evidence + hypothesis.contradicting_evidence)
                 if evidence_id in evidence]
        samples.append(FaithfulnessSample(
            rca_id=record.rca_id,
            incident_id=record.incident_id,
            hypothesis_id=hypothesis.hypothesis_id,
            user_input=f"What could have caused incident {record.incident_id}?",
            response=" ".join([hypothesis.candidate_root_cause, *hypothesis.reasons]),
            contexts=[
                f"{evidence_id} ({evidence[evidence_id].type}, {evidence[evidence_id].citation}): "
                f"{evidence[evidence_id].description}"
                for evidence_id in cited
            ],
            cited=cited,
        ))
    return samples


def make_judge(model: str = JUDGE_MODEL, cache_dir: Path | None = None) -> InstructorBaseRagasLLM:
    """The LLM that judges, through the OpenAI-compatible address of Google AI Studio (a Gemini model)
    or of Groq (any other model), see rca/judge.py.

    With cache_dir, every answer of the judge is kept on disk, so a second run on the same
    hypotheses asks Groq nothing.
    """
    from openai import AsyncOpenAI
    from ragas.cache import DiskCacheBackend

    api_key, base_url = judge.connection(model)
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=6)
    cache = DiskCacheBackend(cache_dir=str(cache_dir)) if cache_dir else None
    # gpt-oss thinks before it answers and the thinking counts in max_tokens. With the RAGAS
    # default of 1024 the answer was sometimes cut to nothing and Groq refused it as invalid JSON.
    return llm_factory(model, client=client, cache=cache, max_tokens=JUDGE_MAX_TOKENS)


async def judge_faithfulness(metric: Faithfulness, sample: FaithfulnessSample) -> FaithfulnessResult:
    """The same three steps as Faithfulness.ascore, kept apart so the statements and the
    verdicts of the judge can be saved and read by a person, not only the final number."""
    statements = await metric._create_statements(sample.user_input, sample.response)
    if not statements:
        return FaithfulnessResult(sample, None)
    verdicts = await metric._create_verdicts(statements, "\n".join(sample.contexts))
    score = metric._compute_score(verdicts)
    return FaithfulnessResult(
        sample,
        None if math.isnan(score) else round(float(score), 3),
        [Verdict(item.statement, bool(item.verdict), item.reason) for item in verdicts.statements],
    )


def evaluate_faithfulness(records: list[RCARecord], judge: InstructorBaseRagasLLM,
                          pause_seconds: float = 2.0) -> list[FaithfulnessResult]:
    """Judge every hypothesis of the given RCAs, one after the other.

    The pause keeps the run under the Groq free tier limit (tokens per minute)."""
    metric = Faithfulness(llm=judge)

    async def run() -> list[FaithfulnessResult]:
        results = []
        for record in records:
            for sample in faithfulness_samples(record):
                results.append(await judge_faithfulness(metric, sample))
                await asyncio.sleep(pause_seconds)
        return results

    return asyncio.run(run())


def story_incidents(path: Path = ANSWER_KEY_PATH) -> list[str]:
    """The incidents investigated in the 13 demo stories, from the answer key."""
    answer_key = json.loads(path.read_text(encoding="utf-8"))
    return [story["target_incident"] for story in answer_key.values()]
