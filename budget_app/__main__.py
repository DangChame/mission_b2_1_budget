"""python -m budget_app 로 실행될 때의 진입점.

__main__.py 라는 이름이면 `python -m 패키지이름` 으로 실행된다.
과제 요구사항 1번이 요구하는 실행 형태다.

    python -m budget_app add        ← 권장. 패키지로 실행된다
    python budget_app add           ← 폴더를 스크립트로 실행. 아래에서 보정한다

두 번째 방식이 왜 문제인가
    폴더 이름을 그대로 주면 파이썬은 그 안의 __main__.py 만 실행하고
    "이게 budget_app 패키지의 일부"라는 정보는 넘겨주지 않는다.
    그래서 __package__ 가 비어 있고, from .cli import main 같은 상대 임포트가
    "부모 패키지를 모르겠다"며 실패한다.

    사용자가 -m 하나 빠뜨렸다고 스택트레이스를 보게 할 이유는 없으므로,
    그럴 때는 상위 폴더를 임포트 경로에 넣고 절대 임포트로 다시 시도한다.
"""

import sys

try:
    from .cli import main
except ImportError:                     # python budget_app 처럼 실행된 경우
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from budget_app.cli import main

if __name__ == "__main__":
    sys.exit(main())
