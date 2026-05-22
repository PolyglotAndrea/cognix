"""Lightweight deterministic memory extraction.

This module intentionally avoids a model dependency. It extracts only high
confidence facts that are safe to write automatically after the memory-write
policy allows persistence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_URL_RE = re.compile(r"https?://[^\s，。；,;]+", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedFact:
    entity_type: str
    entity_id: str
    key: str
    value: str
    confidence: float = 0.8
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryExtractor:
    """Extract stable atomic facts from user messages and task context."""

    def extract(
        self,
        user_message: str,
        assistant_message: str = "",
        *,
        workspace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[ExtractedFact]:
        text = user_message.strip()
        if not text:
            return []

        facts: list[ExtractedFact] = []
        facts.extend(self._extract_urls(text, metadata=metadata))
        facts.extend(self._extract_preferences(text))
        facts.extend(self._extract_defaults(text))
        facts.extend(self._extract_auth_context(text))
        return self._dedupe(facts)

    def _extract_urls(
        self,
        text: str,
        *,
        metadata: dict[str, Any] | None,
    ) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        for url in _URL_RE.findall(text):
            label = self._url_label(text, url)
            key = "url"
            if any(token in text for token in ("入口", "后台", "页面", "地址", "target", "url", "URL")):
                key = "entry_url"
            facts.append(
                ExtractedFact(
                    entity_type="workspace_resource",
                    entity_id=self._slug(label) or "default",
                    key=key,
                    value=url,
                    confidence=0.9,
                    metadata={"label": label, **(metadata or {})},
                )
            )
        return facts

    def _extract_preferences(self, text: str) -> list[ExtractedFact]:
        patterns = [
            (r"(?:我|用户)?(?:现在)?(?:喜欢|偏好|更喜欢|习惯)(?:的是|是|：|:)?\s*([^。；\n]+)", "preference"),
            (r"(?:我|用户)?(?:不喜欢|不想要|避免)(?:的是|是|：|:)?\s*([^。；\n]+)", "negative_preference"),
            (r"(?:我|用户)?(?:只喝|只用|只要)\s*([^。；\n]+)", "preference"),
            (r"I (?:prefer|like|usually use|only use)\s+([^.;\n]+)", "preference"),
            (r"I (?:do not like|don't like|avoid)\s+([^.;\n]+)", "negative_preference"),
        ]
        facts: list[ExtractedFact] = []
        for pattern, key in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = self._clean_value(match.group(1))
                if self._valid_value(value):
                    facts.append(
                        ExtractedFact(
                            entity_type="user",
                            entity_id="default",
                            key=key,
                            value=value,
                            confidence=0.82,
                        )
                    )
        return facts

    def _extract_defaults(self, text: str) -> list[ExtractedFact]:
        patterns = [
            (r"(?:默认|以后都|后续都)(?:用|使用|输出|按)\s*([^。；\n]+)", "default_instruction"),
            (r"(?:输出格式|格式)(?:默认)?(?:是|为|：|:)\s*([^。；\n]+)", "output_format"),
            (r"(?:时区|timezone)(?:默认)?(?:是|为|：|:)\s*([^。；\n]+)", "timezone"),
            (r"(?:语言|language)(?:默认)?(?:是|为|：|:)\s*([^。；\n]+)", "language"),
        ]
        facts: list[ExtractedFact] = []
        for pattern, key in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = self._clean_value(match.group(1))
                if self._valid_value(value):
                    facts.append(
                        ExtractedFact(
                            entity_type="workspace",
                            entity_id="default",
                            key=key,
                            value=value,
                            confidence=0.78,
                        )
                    )
        return facts

    def _extract_auth_context(self, text: str) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        if any(token in text for token in ("已授权", "合法授权", "我确认有合法权限", "授权确认")):
            facts.append(
                ExtractedFact(
                    entity_type="workspace",
                    entity_id="default",
                    key="authorization_statement",
                    value=self._sentence_with(text, ("已授权", "合法授权", "合法权限", "授权确认")),
                    confidence=0.72,
                )
            )
        if any(token in text for token in ("已有登录态", "当前浏览器已有", "已登录", "登录方式")):
            facts.append(
                ExtractedFact(
                    entity_type="workspace",
                    entity_id="default",
                    key="login_context",
                    value=self._sentence_with(text, ("已有登录态", "当前浏览器已有", "已登录", "登录方式")),
                    confidence=0.72,
                )
            )
        return facts

    @staticmethod
    def _url_label(text: str, url: str) -> str:
        before = text.split(url, 1)[0][-40:]
        match = re.search(r"([\w\u4e00-\u9fff/-]{2,24})(?:入口|后台|页面|地址|URL|url)?[：:\s]*$", before)
        return match.group(1) if match else "workspace-url"

    @staticmethod
    def _sentence_with(text: str, needles: tuple[str, ...]) -> str:
        parts = re.split(r"[。；\n]", text)
        for part in parts:
            if any(needle in part for needle in needles):
                return MemoryExtractor._clean_value(part)
        return MemoryExtractor._clean_value(text[:160])

    @staticmethod
    def _clean_value(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" ：:，,。.;")

    @staticmethod
    def _valid_value(value: str) -> bool:
        if len(value) < 2 or len(value) > 300:
            return False
        if value in {"无", "没有", "none", "null"}:
            return False
        return True

    @staticmethod
    def _slug(value: str) -> str:
        value = value.strip().lower()
        value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value)
        return value.strip("-")[:40]

    @staticmethod
    def _dedupe(facts: list[ExtractedFact]) -> list[ExtractedFact]:
        seen: set[tuple[str, str, str, str]] = set()
        deduped: list[ExtractedFact] = []
        for fact in facts:
            key = (fact.entity_type, fact.entity_id, fact.key, fact.value)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(fact)
        return deduped
