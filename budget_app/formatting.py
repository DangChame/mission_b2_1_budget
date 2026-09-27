"""출력 형식 — 콘솔에 보기 좋게 찍는 일만 담당한다. (보너스 3)

외부 라이브러리 없이 문자열 폭을 직접 계산해서 칸을 맞춘다.

한글 때문에 생기는 문제
    len('점심') 은 2 지만, 터미널에서 차지하는 자리는 4칸이다.
    한글·한자·가나는 영문자의 두 배 폭을 쓰기 때문이다.
    그래서 len() 으로 칸을 맞추면 한글이 섞인 줄만 밀린다.

    unicodedata.east_asian_width 가 글자마다 폭 종류를 알려준다.
    'W'(Wide) 나 'F'(Fullwidth) 면 2칸, 나머지는 1칸으로 센다.
"""

from __future__ import annotations

import unicodedata
from typing import Iterable, Sequence


def display_width(text: str) -> int:
    """터미널에서 이 문자열이 차지하는 칸 수."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text: str, width: int, align: str = "left") -> str:
    """display_width 기준으로 빈칸을 채워 폭을 맞춘다."""
    gap = max(0, width - display_width(text))
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def won(amount: int) -> str:
    """1234567 → '1,234,567원'"""
    return f"{amount:,}원"


def table(headers: Sequence[str], rows: Iterable[Sequence[str]],
          aligns: Sequence[str] | None = None) -> str:
    """머리글과 줄들을 받아 정렬된 표 문자열을 만든다."""
    body = [[str(c) for c in row] for row in rows]
    if not body:
        return ""
    cols = len(headers)
    aligns = list(aligns or ["left"] * cols)

    # 각 열의 폭 = 그 열에 들어가는 가장 넓은 값
    widths = [display_width(h) for h in headers]
    for row in body:
        for i in range(cols):
            widths[i] = max(widths[i], display_width(row[i]))

    line = "  ".join(pad(h, widths[i], aligns[i]) for i, h in enumerate(headers))
    rule = "  ".join("-" * w for w in widths)
    out = [line, rule]
    for row in body:
        out.append("  ".join(pad(row[i], widths[i], aligns[i]) for i in range(cols)))
    return "\n".join(out)


def bar(ratio: float, width: int = 24) -> str:
    """0.43 → '##########--------------' 예산 사용률을 눈으로 보여준다."""
    filled = max(0, min(width, round(ratio * width)))
    return "#" * filled + "-" * (width - filled)
