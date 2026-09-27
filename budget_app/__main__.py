"""python -m budget_app 로 실행될 때의 진입점.

__main__.py 라는 이름이면 `python -m 패키지이름` 으로 실행된다.
과제 요구사항 1번이 요구하는 실행 형태다.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
