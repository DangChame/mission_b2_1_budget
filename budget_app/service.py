"""서비스 — 규칙과 계산을 담당한다.

계층을 이렇게 나눈다. 과제 요구사항 "모듈화(구조화)" 에 해당한다.

    cli.py         사람의 입력을 받아 해석한다          (무엇을 하라고 시켰나)
    service.py     규칙을 확인하고 계산한다 ← 여기      (그게 되는 일인가, 결과는 뭔가)
    repository.py  파일을 읽고 쓴다                    (어디에 저장하나)
    models.py      데이터의 모양을 정한다              (무엇을 다루나)

이렇게 나누면 좋은 점
    - service 는 print 를 하지 않는다. 그래서 나중에 웹으로 바꿔도 이 파일은 그대로 쓴다.
    - service 는 open 을 하지 않는다. 그래서 저장 방식을 바꿔도 이 파일은 그대로 쓴다.
    - 각 파일이 한 가지만 하므로 고칠 곳을 찾기 쉽다.
"""

from __future__ import annotations

import csv
import heapq
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Iterator

from .errors import ConflictError, NotFoundError, ValidationError
from .models import (
    TX_TYPES,
    Budget,
    RecurringRule,
    Transaction,
    is_valid_date,
    is_valid_month,
)
from .repository import Repository

# import/export CSV 스키마. 과제 요구사항 11번에서 고정하라고 한 것.
CSV_COLUMNS = ("date", "type", "category", "amount", "memo", "tags")
CSV_REQUIRED = ("date", "type", "category", "amount")


class BudgetService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    # ==================================================================
    # 검증 — 규칙에 맞는 값인지 확인한다
    # ==================================================================
    def validate_date(self, value: str) -> str:
        if not is_valid_date(value):
            raise ValidationError(
                "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).",
                "예: 2024-01-15",
            )
        return value

    def validate_month(self, value: str) -> str:
        if not is_valid_month(value):
            raise ValidationError(
                "월 형식이 올바르지 않습니다 (YYYY-MM).",
                "예: 2024-01",
            )
        return value

    def validate_type(self, value: str) -> str:
        if value not in TX_TYPES:
            raise ValidationError(
                f"타입은 income 또는 expense 여야 합니다. 입력값: {value!r}",
                "수입이면 income, 지출이면 expense 를 입력하세요.",
            )
        return value

    def validate_amount(self, value: str | int) -> int:
        """금액은 양수 정수여야 한다. 0과 음수는 막는다."""
        try:
            amount = int(str(value).replace(",", "").strip())
        except ValueError:
            raise ValidationError(
                f"금액은 숫자여야 합니다. 입력값: {value!r}",
                "예: 15000 (쉼표는 있어도 됩니다)",
            ) from None
        if amount <= 0:
            raise ValidationError(
                f"금액은 0보다 커야 합니다. 입력값: {amount}",
                "지출도 양수로 넣고 타입을 expense 로 구분합니다.",
            )
        return amount

    def validate_category(self, name: str) -> str:
        known = self.repo.category_names()
        if name not in known:
            raise ValidationError(
                f"등록되지 않은 카테고리입니다: {name!r}",
                f"사용 가능: {', '.join(known) or '(없음)'} / 추가: category add --name {name}",
            )
        return name

    @staticmethod
    def parse_tags(raw: str | None) -> list[str]:
        """'meal, lunch' → ['meal', 'lunch'].  빈 값이면 빈 리스트."""
        if not raw:
            return []
        return [t.strip() for t in raw.split(",") if t.strip()]

    # ==================================================================
    # 거래
    # ==================================================================
    def add_transaction(self, *, date: str, type: str, category: str,
                        amount: str | int, memo: str = "",
                        tags: str | list[str] | None = None) -> Transaction:
        tx = Transaction(
            id=self.repo.next_transaction_id(),
            type=self.validate_type(type),
            date=self.validate_date(date),
            amount=self.validate_amount(amount),
            category=self.validate_category(category),
            memo=memo or "",
            tags=tags if isinstance(tags, list) else self.parse_tags(tags),
        )
        self.repo.add_transaction(tx)
        return tx

    @staticmethod
    def _newest_first(stream: Iterable[Transaction], limit: int | None) -> list[Transaction]:
        """최신순 상위 N건을 고른다. ★ 스트리밍을 유지하는 방법

        '최신순' 은 날짜 내림차순이고, 같은 날짜면 나중에 넣은 것(= id 가 큰 것)이 먼저다.
        그런데 파일은 넣은 순서대로 쌓여 있으므로 정렬이 필요하다.

        여기에 문제가 하나 있다.
            sorted(stream) 를 쓰면 정렬을 위해 **모든 건을 메모리에 올려야** 한다.
            요구사항은 "파일 전체를 한 번에 로드하지 않는 스트리밍" 이므로 이건 어긋난다.

        그래서 heapq.nlargest 를 쓴다.
            이 함수는 크기 N 짜리 힙 하나만 들고 스트림을 한 번 훑는다.
            지금 힙에 있는 가장 작은 것보다 큰 값이 나올 때만 교체한다.
            결과적으로 **메모리에 올라가는 건 항상 N개뿐**이다.

            10만 건이 있어도 --limit 20 이면 20개만 들고 있는다.

        limit 를 안 주면 전부를 돌려줘야 하므로 그때는 어쩔 수 없이 전체 정렬을 한다.
        그래서 list 명령의 --limit 기본값을 20 으로 두었다.
        """
        key = lambda t: (t.date, t.id)     # noqa: E731
        if limit is None:
            return sorted(stream, key=key, reverse=True)
        return heapq.nlargest(limit, stream, key=key)

    def list_transactions(self, limit: int | None = None) -> list[Transaction]:
        """최신순으로 돌려준다. 파일을 한 줄씩 흘려 읽는다."""
        return self._newest_first(self.repo.iter_transactions(), limit)

    def search(self, *, date_from: str | None = None, date_to: str | None = None,
               category: str | None = None, type: str | None = None,
               keyword: str | None = None, tag: str | None = None,
               limit: int | None = None) -> list[Transaction]:
        """조건으로 거른다. 조건을 안 주면 전체.

        제너레이터를 파이프처럼 이어 붙인다.
        _stream_matching 이 한 건씩 흘려보내고, 여기서 정렬만 한다.
        """
        if date_from:
            self.validate_date(date_from)
        if date_to:
            self.validate_date(date_to)
        if type:
            self.validate_type(type)

        return self._newest_first(
            self._stream_matching(date_from, date_to, category, type, keyword, tag),
            limit,
        )

    def _stream_matching(self, date_from: str | None, date_to: str | None,
                         category: str | None, type: str | None,
                         keyword: str | None, tag: str | None) -> Iterator[Transaction]:
        """조건에 맞는 것만 흘려보낸다. ★ 제너레이터

        여기서 yield 를 쓰기 때문에 파일 전체가 메모리에 올라오지 않는다.
        날짜 비교를 문자열로 하는 이유: YYYY-MM-DD 는 사전순 정렬이 날짜순과 같다.
        """
        for tx in self.repo.iter_transactions():
            if date_from and tx.date < date_from:
                continue
            if date_to and tx.date > date_to:
                continue
            if category and tx.category != category:
                continue
            if type and tx.type != type:
                continue
            if keyword and keyword.lower() not in tx.memo.lower():
                continue
            if tag and tag not in tx.tags:
                continue
            yield tx

    def get_transaction(self, tx_id: str) -> Transaction:
        for tx in self.repo.iter_transactions():
            if tx.id == tx_id:
                return tx
        raise NotFoundError(
            f"없는 데이터입니다: id={tx_id}",
            "list 명령으로 존재하는 id 를 확인하세요.",
        )

    def delete_transaction(self, tx_id: str) -> Transaction:
        target = self.get_transaction(tx_id)       # 없으면 여기서 NotFoundError
        self.repo.replace_transactions(keep=lambda t: t.id != tx_id)
        return target

    def update_transaction(self, tx_id: str, **changes: str | None) -> tuple[Transaction, Transaction]:
        """옵션으로 준 필드만 바꾼다. (안 A — 옵션 기반, README 에 고정 명시)"""
        before = self.get_transaction(tx_id)
        patch: dict[str, object] = {}

        if changes.get("date") is not None:
            patch["date"] = self.validate_date(str(changes["date"]))
        if changes.get("type") is not None:
            patch["type"] = self.validate_type(str(changes["type"]))
        if changes.get("category") is not None:
            patch["category"] = self.validate_category(str(changes["category"]))
        if changes.get("amount") is not None:
            patch["amount"] = self.validate_amount(str(changes["amount"]))
        if changes.get("memo") is not None:
            patch["memo"] = str(changes["memo"])
        if changes.get("tags") is not None:
            patch["tags"] = self.parse_tags(str(changes["tags"]))

        if not patch:
            raise ValidationError(
                "바꿀 내용이 없습니다.",
                "--date --type --category --amount --memo --tags 중 하나 이상을 주세요.",
            )

        after = replace(before, **patch)   # dataclass 를 일부만 바꿔 새 객체를 만든다
        self.repo.replace_transactions(
            keep=lambda t: True,
            change=lambda t: after if t.id == tx_id else t,
        )
        return before, after

    # ==================================================================
    # 요약과 예산
    # ==================================================================
    def summary(self, month: str, top: int = 3) -> dict[str, object]:
        """한 달치 수입·지출·잔액과 카테고리별 지출 TOP N, 예산 대비 사용률."""
        self.validate_month(month)

        income = 0
        expense = 0
        per_category: Counter[str] = Counter()
        count = 0

        for tx in self.repo.iter_transactions():
            if tx.month != month:
                continue
            count += 1
            if tx.type == "income":
                income += tx.amount
            else:
                expense += tx.amount
                per_category[tx.category] += tx.amount

        budget = self.repo.get_budget(month)
        result: dict[str, object] = {
            "month": month,
            "count": count,
            "income": income,
            "expense": expense,
            "balance": income - expense,
            "top": per_category.most_common(top),
            "budget": budget.amount if budget else None,
            "usage": None,
            "over": False,
        }
        if budget and budget.amount > 0:
            usage = expense / budget.amount
            result["usage"] = usage
            result["over"] = expense > budget.amount
        return result

    def set_budget(self, month: str, amount: str | int) -> Budget:
        self.validate_month(month)
        value = self.validate_amount(amount)
        self.repo.set_budget(month, value)
        return Budget(month, value)

    # ==================================================================
    # 카테고리
    # ==================================================================
    def add_category(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValidationError("카테고리명이 비어 있습니다.", "예: category add --name food")
        if name in self.repo.category_names():
            raise ConflictError(f"이미 있는 카테고리입니다: {name}", "category list 로 확인하세요.")
        self.repo.add_category(name)
        return name

    def remove_category(self, name: str, replace_with: str | None = None) -> int:
        """사용 중인 카테고리는 그냥 못 지운다. (과제 요구사항 10번)

        쓰는 내역이 있으면
          - 대체 카테고리를 주면 그 카테고리로 옮기고 지운다
          - 안 주면 거부하고 몇 건이 걸리는지 알려준다
        """
        if name not in self.repo.category_names():
            raise NotFoundError(f"없는 카테고리입니다: {name}", "category list 로 확인하세요.")

        used = sum(1 for t in self.repo.iter_transactions() if t.category == name)
        if used and not replace_with:
            raise ConflictError(
                f"'{name}' 카테고리를 쓰는 내역이 {used}건 있어 삭제할 수 없습니다.",
                f"대체 카테고리를 지정하세요: category remove --name {name} --replace-with etc",
            )
        if used and replace_with:
            self.validate_category(replace_with)
            if replace_with == name:
                raise ValidationError("대체 카테고리가 삭제 대상과 같습니다.", "다른 카테고리를 지정하세요.")
            self.repo.replace_transactions(
                keep=lambda t: True,
                change=lambda t: replace(t, category=replace_with) if t.category == name else t,
            )
        self.repo.remove_category(name)
        return used

    # ==================================================================
    # CSV 가져오기 / 내보내기
    # ==================================================================
    def export_csv(self, out_path: str | Path, *, month: str | None = None,
                   date_from: str | None = None, date_to: str | None = None) -> int:
        """조건에 맞는 거래를 CSV 로 쓴다.

        과제 요구사항 11번: --month 또는 --from/--to 중 하나 이상을 필수로 받는다.
        조건 없이 전체를 내보내다가 수십만 건을 쏟는 사고를 막으려는 규칙으로 보인다.
        """
        if month:
            self.validate_month(month)
            date_from = f"{month}-01"
            date_to = f"{month}-31"
        elif not (date_from or date_to):
            raise ValidationError(
                "내보낼 기간을 지정해야 합니다.",
                "--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD 를 주세요.",
            )

        rows = self.search(date_from=date_from, date_to=date_to)
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # newline="" 은 csv 모듈이 줄바꿈을 직접 다루게 하려는 것.
        # 이걸 빼면 윈도우에서 줄 사이에 빈 줄이 하나씩 생긴다.
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(CSV_COLUMNS))
            writer.writeheader()
            for tx in rows:
                writer.writerow({
                    "date": tx.date,
                    "type": tx.type,
                    "category": tx.category,
                    "amount": tx.amount,
                    "memo": tx.memo,
                    "tags": ",".join(tx.tags),
                })
        return len(rows)

    def import_csv(self, src_path: str | Path) -> tuple[int, int, list[str]]:
        """CSV 를 읽어 거래를 일괄 등록한다.

        Returns:
            (등록 건수, 건너뛴 건수, 건너뛴 이유 목록)

        한 줄이 잘못됐다고 전체를 멈추지 않는다.
        잘못된 줄만 건너뛰고 이유를 모아 마지막에 보여준다.
        """
        path = Path(src_path)
        if not path.exists():
            raise NotFoundError(f"파일이 없습니다: {path}", "경로를 확인하세요.")

        imported = 0
        skipped: list[str] = []

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing = [c for c in CSV_REQUIRED if c not in (reader.fieldnames or [])]
            if missing:
                raise ValidationError(
                    f"CSV 머리글에 필수 열이 없습니다: {', '.join(missing)}",
                    f"필수 열: {', '.join(CSV_REQUIRED)}",
                )
            for lineno, row in enumerate(reader, 2):   # 2부터인 이유: 1번 줄은 머리글
                try:
                    self.add_transaction(
                        date=(row.get("date") or "").strip(),
                        type=(row.get("type") or "").strip(),
                        category=(row.get("category") or "").strip(),
                        amount=(row.get("amount") or "").strip(),
                        memo=(row.get("memo") or "").strip(),
                        tags=(row.get("tags") or "").strip(),
                    )
                    imported += 1
                except ValidationError as exc:
                    skipped.append(f"{lineno}번째 줄: {exc.reason}")
        return imported, len(skipped), skipped

    # ==================================================================
    # 반복 내역 (보너스 2)
    # ==================================================================
    def add_recurring(self, *, day: str | int, type: str, category: str,
                      amount: str | int, memo: str = "",
                      tags: str | None = None) -> RecurringRule:
        try:
            day_value = int(day)
        except ValueError:
            raise ValidationError(f"일자는 숫자여야 합니다: {day!r}", "1~31 사이 숫자") from None
        if not 1 <= day_value <= 31:
            raise ValidationError(f"일자는 1~31 이어야 합니다: {day_value}", "예: --day 25")

        rule = RecurringRule(
            id=self.repo.next_recurring_id(),
            day=day_value,
            type=self.validate_type(type),
            amount=self.validate_amount(amount),
            category=self.validate_category(category),
            memo=memo or "",
            tags=self.parse_tags(tags),
        )
        self.repo.add_recurring(rule)
        return rule

    def apply_recurring(self, month: str) -> list[Transaction]:
        """반복 규칙을 특정 월에 실제 거래로 만들어 넣는다.

        같은 규칙이 같은 달에 두 번 들어가지 않도록, 메모에 규칙 id 를 적어두고
        이미 있으면 건너뛴다.
        """
        self.validate_month(month)
        rules = list(self.repo.iter_recurring())
        if not rules:
            raise NotFoundError("등록된 반복 규칙이 없습니다.",
                                "recurring add --day 25 --type expense --category rent --amount 500000")

        already = {t.memo for t in self.repo.iter_transactions() if t.month == month}
        created: list[Transaction] = []

        import calendar
        last_day = calendar.monthrange(int(month[:4]), int(month[5:7]))[1]

        for rule in rules:
            marker = f"[{rule.id}] {rule.memo}".strip()
            if marker in already:
                continue      # 이미 이번 달에 만들었다
            # 31일 규칙인데 2월이면 그 달의 마지막 날로 당긴다
            day = min(rule.day, last_day)
            tx = self.add_transaction(
                date=f"{month}-{day:02d}",
                type=rule.type,
                category=rule.category,
                amount=rule.amount,
                memo=marker,
                tags=rule.tags,
            )
            created.append(tx)
        return created
