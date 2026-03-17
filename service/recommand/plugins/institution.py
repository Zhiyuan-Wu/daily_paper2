"""Institution-based recommendation plugin."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from models.paper_recommand import PaperRecommandRequest
from service.recommand.plugins.base import RecommendationPlugin, clamp_score, limit_top_k
from service.recommand.repository import PaperRecommandRepository

_TEXT_NORMALIZER = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
_SPACE_NORMALIZER = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class InstitutionRule:
    key: str
    score: float
    aliases: tuple[str, ...]


_DEFAULT_INSTITUTION_RULES: tuple[InstitutionRule, ...] = (
    InstitutionRule("openai", 3.0, ("openai",)),
    InstitutionRule("google", 2.8, ("google", "google research", "google deepmind", "deepmind")),
    InstitutionRule("microsoft", 2.7, ("microsoft", "microsoft research", "msr")),
    InstitutionRule("meta", 2.6, ("meta", "meta ai", "facebook ai", "fair")),
    InstitutionRule("anthropic", 2.6, ("anthropic",)),
    InstitutionRule("nvidia", 2.5, ("nvidia", "nvidia research")),
    InstitutionRule("apple", 2.3, ("apple", "apple machine learning research")),
    InstitutionRule("amazon", 2.2, ("amazon", "amazon aws", "aws ai labs")),
    InstitutionRule("mit", 2.5, ("massachusetts institute of technology", "mit")),
    InstitutionRule("stanford", 2.5, ("stanford university", "stanford")),
    InstitutionRule(
        "berkeley",
        2.4,
        ("university of california berkeley", "uc berkeley", "berkeley"),
    ),
    InstitutionRule("cmu", 2.4, ("carnegie mellon university", "cmu")),
    InstitutionRule("oxford", 2.2, ("university of oxford", "oxford")),
    InstitutionRule("cambridge", 2.2, ("university of cambridge", "cambridge")),
    InstitutionRule("eth", 2.2, ("eth zurich", "ethz", "swiss federal institute of technology")),
    InstitutionRule("tsinghua", 2.4, ("tsinghua university", "清华大学")),
    InstitutionRule("peking", 2.2, ("peking university", "北京大学")),
    InstitutionRule("zhejiang", 1.9, ("zhejiang university", "浙江大学")),
    InstitutionRule("fudan", 1.9, ("fudan university", "复旦大学")),
    InstitutionRule("shanghai_jiao_tong", 1.9, ("shanghai jiao tong university", "上海交通大学")),
)


class InstitutionRecommendationPlugin(RecommendationPlugin):
    """Score recent papers by matching affiliations against a known institution list."""

    name = "institution"

    def __init__(
        self,
        repository: PaperRecommandRepository,
        *,
        freshness_window_days: int = 30,
        normalization_cap: float = 8.0,
        rules: tuple[InstitutionRule, ...] = _DEFAULT_INSTITUTION_RULES,
    ) -> None:
        self.repository = repository
        self.freshness_window_days = freshness_window_days
        self.normalization_cap = normalization_cap
        self.rules = tuple(_CompiledInstitutionRule.from_rule(rule) for rule in rules)

    def recommend(self, request: PaperRecommandRequest) -> dict[str, float]:
        if self.freshness_window_days <= 0 or self.normalization_cap <= 0:
            return {}

        now = request.resolved_now()
        window_start = now - timedelta(days=self.freshness_window_days)
        papers = self.repository.list_papers(fetched_from=window_start)
        if not papers:
            return {}

        affiliation_map = self.repository.get_affiliations_by_paper_ids([paper.id for paper in papers])
        scores: dict[str, float] = {}
        for paper in papers:
            raw_score = self._score_affiliations(affiliation_map.get(paper.id, []))
            normalized = clamp_score(raw_score / self.normalization_cap)
            if normalized > 0:
                scores[paper.id] = normalized

        return limit_top_k(scores, request.top_k)

    def _score_affiliations(self, affiliations: list[str]) -> float:
        matched_institutions: set[str] = set()
        total = 0.0
        for affiliation in affiliations:
            normalized = _normalize_text(affiliation)
            compact = normalized.replace(" ", "")
            if not normalized:
                continue
            for rule in self.rules:
                if rule.key in matched_institutions:
                    continue
                if rule.matches(normalized, compact):
                    matched_institutions.add(rule.key)
                    total += rule.score
        return total


@dataclass(frozen=True, slots=True)
class _CompiledInstitutionRule:
    key: str
    score: float
    aliases: tuple[str, ...]
    compact_aliases: tuple[str, ...]

    @classmethod
    def from_rule(cls, rule: InstitutionRule) -> "_CompiledInstitutionRule":
        aliases = tuple(alias for alias in (_normalize_text(item) for item in rule.aliases) if alias)
        compact_aliases = tuple(
            alias.replace(" ", "")
            for alias in aliases
            if " " in alias and len(alias.replace(" ", "")) >= 6
        )
        return cls(
            key=rule.key,
            score=rule.score,
            aliases=aliases,
            compact_aliases=compact_aliases,
        )

    def matches(self, normalized_text: str, compact_text: str) -> bool:
        padded_text = f" {normalized_text} "
        if any(f" {alias} " in padded_text for alias in self.aliases):
            return True
        return any(compact_alias in compact_text for compact_alias in self.compact_aliases)


def _normalize_text(value: str) -> str:
    lowered = value.strip().lower()
    if not lowered:
        return ""
    normalized = _TEXT_NORMALIZER.sub(" ", lowered)
    return _SPACE_NORMALIZER.sub(" ", normalized).strip()
