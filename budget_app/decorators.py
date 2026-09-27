"""데코레이터 — 모든 명령이 공통으로 하는 일을 한곳에 모은다.

과제 요구사항: "공통 관심사(예외 처리/로그/시간 측정) 데코레이터를 1개 이상 구현하고 실제 적용"

데코레이터가 무엇인가
    함수를 받아서, 그 함수를 감싼 새 함수를 돌려주는 함수다.

    @log_call
    def add(...): ...

    위는 아래와 똑같다.
        add = log_call(add)

    그래서 add() 를 부르면 실제로는 감싼 쪽이 먼저 돌고,
    그 안에서 원래 add 가 불린다.

왜 쓰나 — 이게 핵심이다
    로그를 남기고 싶다고 치자. 데코레이터가 없으면 명령 함수 15개마다
    맨 앞에 로그 쓰는 코드를 복사해 넣어야 한다.
    나중에 로그 형식을 바꾸면 15군데를 다 고쳐야 한다.

    데코레이터로 빼두면 그 일을 하는 코드는 여기 한 곳뿐이다.
    그리고 명령 함수는 "본래 할 일"만 남아서 읽기 쉬워진다.

    이렇게 여러 곳에 흩어지기 쉬운 공통 기능을 따로 떼어내는 것을
    관심사의 분리(separation of concerns) 라고 한다.
"""

from __future__ import annotations

import functools
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

from .errors import AppError

F = TypeVar("F", bound=Callable[..., Any])

# 로그를 쌓을 파일. set_log_path 로 바꿀 수 있다.
_log_path: Path | None = None
_verbose = False


def configure(log_path: Path | None = None, verbose: bool = False) -> None:
    """cli 가 시작할 때 한 번 불러 로그 위치와 상세 출력 여부를 정한다."""
    global _log_path, _verbose
    _log_path = log_path
    _verbose = verbose


def _write_log(line: str) -> None:
    if _log_path is None:
        return
    try:
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        with _log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        # 로그를 못 남기는 것 때문에 프로그램이 죽으면 안 된다.
        # 로그는 부수적인 일이므로 조용히 넘어간다.
        pass


def log_call(func: F) -> F:
    """언제 어떤 명령이 실행됐는지 파일에 남긴다.

    @functools.wraps 를 붙이는 이유
        데코레이터로 감싸면 함수의 이름이 감싼 쪽 이름(wrapper)으로 바뀐다.
        그러면 --help 에 엉뚱한 이름이 나오고 디버깅도 어려워진다.
        wraps 는 원래 함수의 이름과 설명문을 그대로 옮겨준다.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_log(f"[{stamp}] CALL {func.__name__}")
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            _write_log(f"[{stamp}] FAIL {func.__name__} {type(exc).__name__}: {exc}")
            raise
        _write_log(f"[{stamp}] DONE {func.__name__}")
        return result
    return wrapper  # type: ignore[return-value]


def timed(func: F) -> F:
    """실행 시간을 잰다. --verbose 를 줬을 때만 화면에 보여준다.

    time.perf_counter 를 쓰는 이유
        time.time() 은 벽시계라 사용자가 시스템 시각을 바꾸면 음수가 나올 수 있다.
        perf_counter 는 단조 증가만 하므로 경과 시간 측정에 맞다.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            _write_log(f"          TIME {func.__name__} {elapsed:.1f}ms")
            if _verbose:
                print(f"[시간] {func.__name__} {elapsed:.1f}ms", file=sys.stderr)
    return wrapper  # type: ignore[return-value]


def handle_errors(func: F) -> F:
    """예외를 사람이 읽을 수 있는 메시지로 바꾸고 종료 코드를 정한다.

    과제 요구사항
        - 스택트레이스 출력 금지 → 원인 + 해결 힌트
        - 정상 종료 0, 오류 종료 0이 아닌 값

    예외를 두 종류로 나눠서 다르게 처리한다.
        AppError      : 우리가 예상하고 일부러 던진 것. 원인과 힌트를 그대로 보여준다
        그 밖의 예외   : 예상 못 한 것. 스택트레이스 대신 짧게만 알리고 로그에 남긴다
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> int:
        try:
            func(*args, **kwargs)
            return 0
        except AppError as exc:
            print(f"[오류] {exc.reason}", file=sys.stderr)
            if exc.hint:
                print(f"[힌트] {exc.hint}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\n[중단] 사용자가 취소했습니다.", file=sys.stderr)
            return 130          # 관례상 Ctrl+C 는 130
        except BrokenPipeError:
            # `list | head` 처럼 받는 쪽이 먼저 닫으면 난다. 오류가 아니다.
            return 0
        except Exception as exc:   # noqa: BLE001 - 마지막 그물
            print(f"[오류] 예상하지 못한 문제가 발생했습니다: {type(exc).__name__}", file=sys.stderr)
            print("[힌트] --verbose 옵션을 붙여 다시 실행하거나 data/app.log 를 확인하세요.",
                  file=sys.stderr)
            _write_log(f"          UNEXPECTED {type(exc).__name__}: {exc}")
            if _verbose:
                import traceback
                traceback.print_exc()
            return 2
    return wrapper  # type: ignore[return-value]
