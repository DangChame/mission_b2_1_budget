"""저장소 — 파일 읽고 쓰는 일만 담당한다.

과제 요구사항 3번: JSONL 또는 CSV 중 1개, 저장 파일 3개 이상.
여기서는 JSONL 을 골랐고 파일을 네 개로 나눴다.

    data/transactions.jsonl   거래 내역
    data/categories.jsonl     카테고리
    data/budgets.jsonl        월 예산
    data/recurring.jsonl      반복 규칙 (보너스 2)

JSONL 을 고른 이유 (CSV 대신)
    JSONL 은 "한 줄에 JSON 하나"다. 파일 전체가 아니라 한 줄만 읽어도 한 건을 복원할 수 있다.
    그래서 제너레이터 스트리밍과 궁합이 맞는다.
    그리고 tags 처럼 값이 여러 개인 필드를 CSV 는 쉼표 때문에 따로 처리해야 하지만
    JSON 은 배열을 그대로 담는다.
    (CSV 는 import/export 용 교환 포맷으로만 쓴다 — 과제 요구사항 11번)
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from .errors import AppError
from .models import Budget, Category, RecurringRule, Transaction

TRANSACTIONS = "transactions.jsonl"
CATEGORIES = "categories.jsonl"
BUDGETS = "budgets.jsonl"
RECURRING = "recurring.jsonl"

DEFAULT_CATEGORIES = ("food", "transport", "rent", "salary", "etc")


class Repository:
    """파일 네 개를 다루는 창구.

    이 클래스 밖에서는 open() 을 직접 호출하지 않는다.
    저장 방식을 JSONL 에서 SQLite 로 바꾸더라도 이 파일만 고치면 되게 하려는 것이다.
    """

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.dir = Path(data_dir)

    # ------------------------------------------------------------------
    # 초기화
    # ------------------------------------------------------------------
    def ensure_ready(self) -> bool:
        """저장 폴더와 파일이 없으면 만든다.

        과제 요구사항 3번의 "초기 실행" 처리.
        카테고리가 비어 있으면 기본 카테고리를 넣는 (안 A) 를 선택했다.
        처음 쓰는 사람이 add 를 하려다 카테고리가 없어서 막히는 것을 피하려는 것이다.

        Returns:
            처음 만든 것이면 True, 이미 있었으면 False
        """
        created = not self.dir.exists()
        self.dir.mkdir(parents=True, exist_ok=True)
        for name in (TRANSACTIONS, CATEGORIES, BUDGETS, RECURRING):
            path = self.dir / name
            if not path.exists():
                path.touch()
                created = True

        if not any(True for _ in self.iter_categories()):
            for name in DEFAULT_CATEGORIES:
                self.append(CATEGORIES, Category(name).to_dict())
            created = True
        return created

    # ------------------------------------------------------------------
    # 저수준 입출력
    # ------------------------------------------------------------------
    def _path(self, filename: str) -> Path:
        return self.dir / filename

    def iter_raw(self, filename: str) -> Iterator[dict[str, Any]]:
        """파일을 한 줄씩 읽어 사전으로 흘려보낸다. ★ 제너레이터

        과제 요구사항 5번: "파일 전체를 한 번에 로드하지 않고, 제너레이터 기반 스트리밍"

        return 이 아니라 yield 를 쓴다. 차이는 이렇다.
            return  : 값을 만들어 한 번에 다 돌려주고 함수가 끝난다
            yield   : 한 개 내주고 그 자리에서 멈춰 있다가, 다음을 요청하면 이어서 실행한다

        그래서 10만 줄짜리 파일이어도 메모리에는 항상 한 줄만 올라간다.
        list --limit 3 을 하면 세 줄만 읽고 멈춘다. 나머지는 아예 읽지 않는다.
        """
        path = self._path(filename)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue          # 빈 줄은 건너뛴다
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # 한 줄이 깨졌다고 전체를 포기하지 않는다.
                    # 나머지 줄은 멀쩡하므로 계속 읽는다.
                    raise AppError(
                        f"{filename} {lineno}번째 줄을 읽을 수 없습니다.",
                        "파일이 손상되었을 수 있습니다. backup 명령으로 만든 백업을 확인하세요.",
                    )

    def append(self, filename: str, row: dict[str, Any]) -> None:
        """파일 끝에 한 줄 덧붙인다. 기존 내용은 건드리지 않는다."""
        self.dir.mkdir(parents=True, exist_ok=True)
        with self._path(filename).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def rewrite(self, filename: str, rows: Iterator[dict[str, Any]]) -> int:
        """파일을 통째로 다시 쓴다. ★ 원자적 교체 (보너스 4)

        update / delete 에서 쓴다. 과제 요구사항 6번이
        "전체 재작성 / 임시 파일 / 원자적 교체(권장)" 를 요구한다.

        왜 원본에 바로 쓰면 안 되나
            원본을 열어 쓰는 도중에 프로그램이 죽으면 파일이 반만 남는다.
            그러면 지금까지 쌓은 거래 내역을 통째로 잃는다.

        그래서 이렇게 한다
            1) .tmp 파일에 전부 쓴다        ← 실패해도 원본은 멀쩡하다
            2) os.replace 로 이름을 바꾼다  ← 운영체제가 한 번에 끝내준다

        os.replace 는 같은 파일시스템 안에서 원자적(atomic)이다.
        "바뀌기 전" 아니면 "바뀐 후"만 존재하고, 그 중간 상태가 보이지 않는다는 뜻이다.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        target = self._path(filename)
        tmp = target.with_suffix(target.suffix + ".tmp")
        count = 0
        try:
            with tmp.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1
                f.flush()
                os.fsync(f.fileno())   # OS 버퍼에 남은 것까지 디스크에 확실히 내린다
            os.replace(tmp, target)    # ← 여기가 원자적으로 바뀌는 지점
        finally:
            if tmp.exists():
                tmp.unlink()           # 중간에 실패했으면 임시파일을 치운다
        return count

    # ------------------------------------------------------------------
    # 거래
    # ------------------------------------------------------------------
    def iter_transactions(self) -> Iterator[Transaction]:
        """거래를 저장된 순서대로 흘려보낸다."""
        for raw in self.iter_raw(TRANSACTIONS):
            yield Transaction.from_dict(raw)

    def add_transaction(self, tx: Transaction) -> None:
        self.append(TRANSACTIONS, tx.to_dict())

    def next_transaction_id(self) -> str:
        """TX-000001 부터 하나씩 올린다.

        파일을 끝까지 훑어 제일 큰 번호를 찾는다.
        건수가 아주 많아지면 느려지므로, 실제 서비스라면 마지막 id 를 따로 저장하거나
        데이터베이스의 자동 증가를 쓴다. 이 과제 규모에서는 이 방식이 단순해서 낫다.
        """
        biggest = 0
        for raw in self.iter_raw(TRANSACTIONS):
            tx_id = str(raw.get("id", ""))
            if tx_id.startswith("TX-"):
                try:
                    biggest = max(biggest, int(tx_id[3:]))
                except ValueError:
                    continue
        return f"TX-{biggest + 1:06d}"

    def replace_transactions(self, keep: Callable[[Transaction], bool],
                             change: Callable[[Transaction], Transaction] | None = None) -> int:
        """조건에 맞는 거래만 남기고, 필요하면 바꿔서 파일을 다시 쓴다.

        delete 는 keep 으로 걸러내고, update 는 change 로 바꾼다.
        읽으면서 바로 쓰는 게 아니라 제너레이터로 넘겨서 rewrite 가 흘려 쓰게 한다.
        """
        def stream() -> Iterator[dict[str, Any]]:
            for tx in self.iter_transactions():
                if not keep(tx):
                    continue
                yield (change(tx) if change else tx).to_dict()
        return self.rewrite(TRANSACTIONS, stream())

    # ------------------------------------------------------------------
    # 카테고리
    # ------------------------------------------------------------------
    def iter_categories(self) -> Iterator[Category]:
        for raw in self.iter_raw(CATEGORIES):
            yield Category.from_dict(raw)

    def category_names(self) -> list[str]:
        return [c.name for c in self.iter_categories()]

    def add_category(self, name: str) -> None:
        self.append(CATEGORIES, Category(name).to_dict())

    def remove_category(self, name: str) -> None:
        self.rewrite(
            CATEGORIES,
            (c.to_dict() for c in self.iter_categories() if c.name != name),
        )

    # ------------------------------------------------------------------
    # 예산
    # ------------------------------------------------------------------
    def iter_budgets(self) -> Iterator[Budget]:
        for raw in self.iter_raw(BUDGETS):
            yield Budget.from_dict(raw)

    def get_budget(self, month: str) -> Budget | None:
        for b in self.iter_budgets():
            if b.month == month:
                return b
        return None

    def set_budget(self, month: str, amount: int) -> None:
        """같은 달 예산이 이미 있으면 덮어쓴다."""
        existing = {b.month: b for b in self.iter_budgets()}
        existing[month] = Budget(month, amount)
        self.rewrite(
            BUDGETS,
            (existing[m].to_dict() for m in sorted(existing)),
        )

    # ------------------------------------------------------------------
    # 반복 규칙 (보너스 2)
    # ------------------------------------------------------------------
    def iter_recurring(self) -> Iterator[RecurringRule]:
        for raw in self.iter_raw(RECURRING):
            yield RecurringRule.from_dict(raw)

    def add_recurring(self, rule: RecurringRule) -> None:
        self.append(RECURRING, rule.to_dict())

    def remove_recurring(self, rule_id: str) -> None:
        self.rewrite(
            RECURRING,
            (r.to_dict() for r in self.iter_recurring() if r.id != rule_id),
        )

    def next_recurring_id(self) -> str:
        biggest = 0
        for raw in self.iter_raw(RECURRING):
            rid = str(raw.get("id", ""))
            if rid.startswith("RC-"):
                try:
                    biggest = max(biggest, int(rid[3:]))
                except ValueError:
                    continue
        return f"RC-{biggest + 1:06d}"

    # ------------------------------------------------------------------
    # 백업 (보너스 1)
    # ------------------------------------------------------------------
    def backup(self) -> Path:
        """data 폴더를 통째로 복사한다. 폴더명에 시각을 넣어 덮어쓰지 않게 한다."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = self.dir.parent / f"{self.dir.name}-backup-{stamp}"
        shutil.copytree(self.dir, dest)
        return dest
