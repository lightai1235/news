"""数据契约与信源协议（SPEC §5.4 / §5.6）。

所有信源适配器实现 SourcePort，输出统一的 Candidate；
流水线各段之间只通过这些可 JSON 序列化的数据结构交换数据。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Protocol, runtime_checkable

KINDS = ("article", "video", "paper", "discussion", "wechat")


@dataclass
class Candidate:
    """一条候选内容。score/reason 由评分段填写，adapter 不填。"""

    url: str
    title: str
    kind: str
    source: str
    snippet: str = ""
    lang: str = "en"
    published: str = ""
    meta: dict = field(default_factory=dict)
    score: float | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind: {self.kind!r} (allowed: {KINDS})")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Candidate:
        return cls(**json.loads(text))


@dataclass
class Query:
    """一个词条的查询扩展结果（SPEC §5.3）：精确/概念/中文组 + 别名词表。"""

    title: str
    lang: str
    aliases: list[str] = field(default_factory=list)
    groups: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Query:
        return cls(**json.loads(text))


@runtime_checkable
class SourcePort(Protocol):
    """信源适配器协议。实现内部必须捕获一切异常并返回 []，禁止向流水线抛异常。"""

    name: str
    needs_key: bool

    def search(self, query: Query) -> list[Candidate]: ...


_REGISTRY: dict[str, SourcePort] = {}


def register(source: SourcePort) -> None:
    if source.name in _REGISTRY:
        raise ValueError(f"source already registered: {source.name}")
    _REGISTRY[source.name] = source


def registry() -> dict[str, SourcePort]:
    return dict(_REGISTRY)
