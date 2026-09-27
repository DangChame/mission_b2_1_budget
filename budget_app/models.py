"""데이터 모델 — 이 프로그램이 다루는 데이터의 모양을 정한다.

과제 요구사항 2번: dataclass 또는 그에 준하는 구조, 최소 2개 이상의 클래스.
여기서는 Transaction / Category / Budget / RecurringRule 네 개를 둔다.

dataclass를 쓰는 이유
    class Transaction:
        def __init__(self, id, type, date, ...):
            self.id = id
            ...
    이렇게 직접 쓰면 필드를 추가할 때마다 __init__ 을 고쳐야 한다.
    @dataclass 를 붙이면 필드만 적어도 __init__, __repr__, __eq__ 가 자동으로 만들어진다.

타입 힌트(: str, : int)를 붙이는 이유
    "이 함수는 무엇을 받아 무엇을 돌려주는가"를 코드에 적어두는 것이다.
    파이썬이 실행 중에 검사해주지는 않지만,
      - 에디터가 오타와 잘못된 사용을 미리 잡아준다
      - 읽는 사람이 함수 본문을 안 봐도 계약을 안다
    과제 목표 5번이 바로 이 이점을 설명하는 것이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any, Literal

# income(수입) 또는 expense(지출) 둘 중 하나만 허용한다.
# Literal 을 쓰면 "문자열이면 아무거나"가 아니라 "이 두 개 중 하나"라고 적을 수 있다.
TxType = Literal["income", "expense"]

TX_TYPES: tuple[str, ...] = ("income", "expense")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass
class Transaction:
    """거래 내역 한 건."""

    id: str                       # TX-000001 형식. 유일하다
    type: str                     # income / expense
    date: str                     # YYYY-MM-DD
    amount: int                   # 양수 정수 (원 단위)
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)

    # tags 에 왜 field(default_factory=list) 를 쓰나
    #   tags: list[str] = []  로 쓰면 그 빈 리스트 하나를 모든 인스턴스가 공유한다.
    #   한 거래에 태그를 추가하면 다른 거래에도 붙는 버그가 생긴다.
    #   default_factory=list 는 "인스턴스를 만들 때마다 새 리스트를 만들라"는 뜻이다.

    @property
    def month(self) -> str:
        """'2024-01-15' → '2024-01'. 월별 요약에서 쓴다."""
        return self.date[:7]

    def to_dict(self) -> dict[str, Any]:
        """JSONL 한 줄로 저장하기 위해 사전으로 바꾼다."""
        return {
            "id": self.id,
            "type": self.type,
            "date": self.date,
            "amount": self.amount,
            "category": self.category,
            "memo": self.memo,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Transaction":
        """저장된 사전을 다시 Transaction 으로 되돌린다."""
        return cls(
            id=str(raw["id"]),
            type=str(raw["type"]),
            date=str(raw["date"]),
            amount=int(raw["amount"]),
            category=str(raw["category"]),
            memo=str(raw.get("memo", "")),
            tags=list(raw.get("tags", [])),
        )


@dataclass
class Category:
    """카테고리 하나. 지금은 이름뿐이지만 나중에 색·아이콘을 붙일 자리를 남겨둔다."""

    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Category":
        return cls(name=str(raw["name"]))


@dataclass
class Budget:
    """한 달치 예산."""

    month: str      # YYYY-MM
    amount: int     # 양수 정수

    def to_dict(self) -> dict[str, Any]:
        return {"month": self.month, "amount": self.amount}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Budget":
        return cls(month=str(raw["month"]), amount=int(raw["amount"]))


@dataclass
class RecurringRule:
    """매달 반복되는 내역 규칙. (보너스 2)

    예: 매달 25일에 월세 500000원 지출
    """

    id: str          # RC-000001
    day: int         # 1~31
    type: str
    amount: int
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "day": self.day,
            "type": self.type,
            "amount": self.amount,
            "category": self.category,
            "memo": self.memo,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RecurringRule":
        return cls(
            id=str(raw["id"]),
            day=int(raw["day"]),
            type=str(raw["type"]),
            amount=int(raw["amount"]),
            category=str(raw["category"]),
            memo=str(raw.get("memo", "")),
            tags=list(raw.get("tags", [])),
        )


def is_valid_date(text: str) -> bool:
    """YYYY-MM-DD 형식이면서 달력에 실제로 있는 날짜인가.

    정규식만으로는 2024-13-40 을 거를 수 없다. 형식은 맞기 때문이다.
    그래서 형식 검사 후 실제로 날짜를 만들어본다.
    """
    if not DATE_RE.match(text):
        return False
    try:
        y, m, d = (int(x) for x in text.split("-"))
        _date(y, m, d)
    except ValueError:
        return False
    return True


def is_valid_month(text: str) -> bool:
    """YYYY-MM 형식이면서 월이 1~12 범위인가."""
    if not MONTH_RE.match(text):
        return False
    month = int(text.split("-")[1])
    return 1 <= month <= 12
