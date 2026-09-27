"""사용자에게 보여줄 오류를 정의한다.

과제 제약: "스택트레이스 출력 금지(원인 + 해결 힌트 출력)"

파이썬은 오류가 나면 기본으로 스택트레이스를 쏟아낸다. 개발자에게는 유용하지만
프로그램을 쓰는 사람에게는 무슨 말인지 알 수 없는 글자 덩어리다.
그래서 "예상 가능한 오류"는 이 AppError로 감싸서 던지고,
cli 쪽 데코레이터가 받아서 원인과 힌트 두 줄로 바꿔 출력한다.
"""

from __future__ import annotations


class AppError(Exception):
    """예상 가능한 오류. 원인(reason)과 해결 힌트(hint)를 함께 들고 다닌다."""

    def __init__(self, reason: str, hint: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.hint = hint


class ValidationError(AppError):
    """입력값이 규칙에 안 맞을 때. 예: 날짜 형식, 음수 금액"""


class NotFoundError(AppError):
    """찾는 데이터가 없을 때. 예: 존재하지 않는 id"""


class ConflictError(AppError):
    """지금 상태 때문에 할 수 없을 때. 예: 사용 중인 카테고리 삭제"""
