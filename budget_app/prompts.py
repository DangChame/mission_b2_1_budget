"""대화형 입력 — 사용자에게 묻고, 틀리면 다시 묻는다.

과제 요구사항 1번: "입력 기본 방식은 대화형", add 실행 시 필드를 순차 입력.
요구사항 2번: 형식 오류·음수 금액·없는 카테고리는 "재입력 요구 또는 오류 메시지".

여기서는 재입력 쪽을 택했다. 한 글자 틀렸다고 처음부터 다시 치게 하면 불편하기 때문이다.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from .errors import AppError, ValidationError

T = TypeVar("T")

MAX_RETRY = 3


def ask(label: str, validate: Callable[[str], T], *, allow_empty: bool = False,
        empty_value: T | None = None) -> T:
    """값을 물어보고 검증한다. 틀리면 이유와 힌트를 보여주고 다시 묻는다.

    Args:
        label: 화면에 보여줄 질문
        validate: 입력 문자열을 받아 값을 돌려주거나 ValidationError 를 던지는 함수
        allow_empty: 엔터만 쳐도 되는가 (선택 항목)
        empty_value: 비어 있을 때 쓸 값
    """
    for attempt in range(1, MAX_RETRY + 1):
        raw = input(label).strip()
        if not raw and allow_empty:
            return empty_value  # type: ignore[return-value]
        if not raw:
            print("[오류] 값을 입력해주세요.")
            continue
        try:
            return validate(raw)
        except AppError as exc:
            print(f"[오류] {exc.reason}")
            if exc.hint:
                print(f"[힌트] {exc.hint}")
            if attempt == MAX_RETRY:
                raise ValidationError(
                    f"입력을 {MAX_RETRY}번 연속으로 확인하지 못했습니다.",
                    "값을 확인한 뒤 다시 실행하세요.",
                ) from None
    raise AssertionError("도달할 수 없음")
