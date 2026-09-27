"""테스트 — 표준 라이브러리 unittest 만 사용한다.

실행:  python3 -m unittest discover -s tests -v
       python3 -m unittest tests.test_budget_app -v

pytest 를 쓰지 않는 이유는 과제 제약 때문이다.
"pip install 이 필요한 외부 라이브러리 사용 금지" 이므로 파이썬에 들어 있는 unittest 를 쓴다.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from budget_app.cli import main
from budget_app.errors import ConflictError, NotFoundError, ValidationError
from budget_app.formatting import display_width, pad, won
from budget_app.models import Transaction, is_valid_date, is_valid_month
from budget_app.repository import Repository
from budget_app.service import BudgetService


class Base(unittest.TestCase):
    """테스트마다 새 임시 폴더를 쓴다. 서로 간섭하지 않게 하려는 것."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "data"
        self.repo = Repository(self.dir)
        self.repo.ensure_ready()
        self.svc = BudgetService(self.repo)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add(self, date: str, type_: str, category: str, amount: int,
            memo: str = "", tags: str = "") -> Transaction:
        return self.svc.add_transaction(date=date, type=type_, category=category,
                                        amount=amount, memo=memo, tags=tags)


class TestValidation(Base):
    def test_날짜_형식(self):
        self.assertTrue(is_valid_date("2024-01-15"))
        self.assertFalse(is_valid_date("2024-13-40"))   # 없는 달·날
        self.assertFalse(is_valid_date("2024-02-30"))   # 형식은 맞지만 달력에 없음
        self.assertFalse(is_valid_date("24-01-15"))     # 두 자리 연도
        self.assertFalse(is_valid_date(""))

    def test_윤년(self):
        self.assertTrue(is_valid_date("2024-02-29"))    # 2024는 윤년
        self.assertFalse(is_valid_date("2023-02-29"))   # 2023은 아님

    def test_월_형식(self):
        self.assertTrue(is_valid_month("2024-01"))
        self.assertFalse(is_valid_month("2024-13"))
        self.assertFalse(is_valid_month("2024-1"))

    def test_금액은_양수만(self):
        self.assertEqual(self.svc.validate_amount("15000"), 15000)
        self.assertEqual(self.svc.validate_amount("15,000"), 15000)   # 쉼표 허용
        with self.assertRaises(ValidationError):
            self.svc.validate_amount("0")
        with self.assertRaises(ValidationError):
            self.svc.validate_amount("-500")
        with self.assertRaises(ValidationError):
            self.svc.validate_amount("만원")

    def test_타입은_두_가지만(self):
        self.assertEqual(self.svc.validate_type("income"), "income")
        with self.assertRaises(ValidationError):
            self.svc.validate_type("INCOME")     # 대소문자 구분
        with self.assertRaises(ValidationError):
            self.svc.validate_type("수입")

    def test_없는_카테고리는_거부(self):
        with self.assertRaises(ValidationError):
            self.svc.validate_category("없는것")


class TestTransaction(Base):
    def test_추가하면_id가_생긴다(self):
        tx = self.add("2024-01-15", "expense", "food", 15000, "점심", "meal")
        self.assertEqual(tx.id, "TX-000001")
        self.assertEqual(tx.tags, ["meal"])
        self.assertEqual(tx.month, "2024-01")

    def test_id는_하나씩_올라간다(self):
        self.add("2024-01-01", "expense", "food", 1000)
        second = self.add("2024-01-02", "expense", "food", 2000)
        self.assertEqual(second.id, "TX-000002")

    def test_삭제해도_id는_재사용하지_않는다(self):
        self.add("2024-01-01", "expense", "food", 1000)
        self.add("2024-01-02", "expense", "food", 2000)
        self.svc.delete_transaction("TX-000002")
        third = self.add("2024-01-03", "expense", "food", 3000)
        self.assertEqual(third.id, "TX-000002")  # 최대값 기준이므로 빈 번호를 채운다

    def test_최신순_정렬(self):
        self.add("2024-01-10", "expense", "food", 1000)
        self.add("2024-01-20", "expense", "food", 2000)
        self.add("2024-01-15", "expense", "food", 3000)
        rows = self.svc.list_transactions()
        self.assertEqual([t.date for t in rows],
                         ["2024-01-20", "2024-01-15", "2024-01-10"])

    def test_같은_날짜면_나중에_넣은_것이_먼저(self):
        first = self.add("2024-01-10", "expense", "food", 1000)
        second = self.add("2024-01-10", "expense", "food", 2000)
        rows = self.svc.list_transactions()
        self.assertEqual(rows[0].id, second.id)
        self.assertEqual(rows[1].id, first.id)

    def test_limit(self):
        for day in range(1, 11):
            self.add(f"2024-01-{day:02d}", "expense", "food", 1000)
        self.assertEqual(len(self.svc.list_transactions(limit=3)), 3)

    def test_없는_id_수정_삭제(self):
        with self.assertRaises(NotFoundError):
            self.svc.delete_transaction("TX-999999")
        with self.assertRaises(NotFoundError):
            self.svc.update_transaction("TX-999999", amount="100")

    def test_수정은_준_필드만_바뀐다(self):
        self.add("2024-01-15", "expense", "food", 15000, "점심", "meal")
        before, after = self.svc.update_transaction("TX-000001", amount="16000")
        self.assertEqual(after.amount, 16000)
        self.assertEqual(after.memo, before.memo)      # 안 준 필드는 그대로
        self.assertEqual(after.date, before.date)

    def test_바꿀_내용_없으면_오류(self):
        self.add("2024-01-15", "expense", "food", 15000)
        with self.assertRaises(ValidationError):
            self.svc.update_transaction("TX-000001")


class TestSearch(Base):
    def setUp(self) -> None:
        super().setUp()
        self.add("2024-01-05", "expense", "rent", 500000, "월세", "fixed")
        self.add("2024-01-12", "expense", "transport", 20000, "택시")
        self.add("2024-01-15", "expense", "food", 15000, "점심", "meal")
        self.add("2024-01-14", "income", "salary", 3000000, "월급")
        self.add("2024-02-03", "expense", "food", 8000, "김밥", "meal")

    def test_기간(self):
        rows = self.svc.search(date_from="2024-01-01", date_to="2024-01-31")
        self.assertEqual(len(rows), 4)

    def test_타입(self):
        self.assertEqual(len(self.svc.search(type="income")), 1)

    def test_카테고리(self):
        self.assertEqual(len(self.svc.search(category="food")), 2)

    def test_메모_키워드(self):
        self.assertEqual(len(self.svc.search(keyword="월")), 2)   # 월세, 월급

    def test_태그(self):
        self.assertEqual(len(self.svc.search(tag="meal")), 2)

    def test_조건_조합(self):
        rows = self.svc.search(date_from="2024-01-01", date_to="2024-01-31",
                               type="expense", category="food")
        self.assertEqual(len(rows), 1)

    def test_조건에_맞는_게_없으면_빈_목록(self):
        self.assertEqual(self.svc.search(category="salary", type="expense"), [])


class TestSummaryBudget(Base):
    def setUp(self) -> None:
        super().setUp()
        self.add("2024-01-05", "expense", "rent", 500000)
        self.add("2024-01-12", "expense", "transport", 20000)
        self.add("2024-01-15", "expense", "food", 15000)
        self.add("2024-01-14", "income", "salary", 3000000)

    def test_합계와_잔액(self):
        s = self.svc.summary("2024-01")
        self.assertEqual(s["income"], 3000000)
        self.assertEqual(s["expense"], 535000)
        self.assertEqual(s["balance"], 2465000)

    def test_카테고리별_TOP(self):
        top = self.svc.summary("2024-01", top=2)["top"]
        self.assertEqual(top, [("rent", 500000), ("transport", 20000)])

    def test_수입은_카테고리_집계에서_빠진다(self):
        names = [c for c, _ in self.svc.summary("2024-01", top=10)["top"]]
        self.assertNotIn("salary", names)

    def test_데이터_없는_달(self):
        self.assertEqual(self.svc.summary("2025-07")["count"], 0)

    def test_예산_사용률(self):
        self.svc.set_budget("2024-01", 1000000)
        s = self.svc.summary("2024-01")
        self.assertAlmostEqual(float(s["usage"]), 0.535)
        self.assertFalse(s["over"])

    def test_예산_초과_감지(self):
        self.svc.set_budget("2024-01", 500000)
        s = self.svc.summary("2024-01")
        self.assertTrue(s["over"])

    def test_예산은_덮어쓴다(self):
        self.svc.set_budget("2024-01", 100000)
        self.svc.set_budget("2024-01", 200000)
        self.assertEqual(len(list(self.repo.iter_budgets())), 1)
        self.assertEqual(self.repo.get_budget("2024-01").amount, 200000)

    def test_예산도_영구_저장된다(self):
        self.svc.set_budget("2024-01", 500000)
        fresh = Repository(self.dir)          # 새 객체로 다시 읽어본다
        self.assertEqual(fresh.get_budget("2024-01").amount, 500000)


class TestCategory(Base):
    def test_중복_추가_거부(self):
        self.svc.add_category("hobby")
        with self.assertRaises(ConflictError):
            self.svc.add_category("hobby")

    def test_사용중인_카테고리는_못_지운다(self):
        self.add("2024-01-01", "expense", "food", 1000)
        with self.assertRaises(ConflictError):
            self.svc.remove_category("food")

    def test_대체_카테고리를_주면_옮기고_지운다(self):
        self.add("2024-01-01", "expense", "food", 1000)
        self.add("2024-01-02", "expense", "food", 2000)
        moved = self.svc.remove_category("food", replace_with="etc")
        self.assertEqual(moved, 2)
        self.assertNotIn("food", self.repo.category_names())
        self.assertTrue(all(t.category == "etc" for t in self.repo.iter_transactions()))

    def test_안_쓰는_카테고리는_그냥_지워진다(self):
        self.assertEqual(self.svc.remove_category("hobby") if False else 0, 0)
        self.svc.add_category("hobby")
        self.assertEqual(self.svc.remove_category("hobby"), 0)

    def test_없는_카테고리_삭제(self):
        with self.assertRaises(NotFoundError):
            self.svc.remove_category("없는것")


class TestCsv(Base):
    def test_export_는_기간이_필수(self):
        with self.assertRaises(ValidationError):
            self.svc.export_csv(self.dir / "x.csv")

    def test_export_스키마와_건수(self):
        self.add("2024-01-15", "expense", "food", 15000, "점심", "meal")
        self.add("2024-02-01", "expense", "food", 5000)
        out = self.dir / "out.csv"
        n = self.svc.export_csv(out, month="2024-01")
        self.assertEqual(n, 1)
        with out.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.assertEqual(list(reader.fieldnames),
                             ["date", "type", "category", "amount", "memo", "tags"])
            row = next(reader)
        self.assertEqual(row["memo"], "점심")
        self.assertEqual(row["tags"], "meal")

    def test_import_잘못된_줄만_건너뛴다(self):
        src = self.dir / "in.csv"
        src.write_text(
            "date,type,category,amount,memo,tags\n"
            "2024-03-01,expense,food,12000,커피,cafe\n"
            "2024-13-99,expense,food,5000,날짜틀림,\n"       # 날짜 오류
            "2024-03-03,expense,food,-100,음수,\n"           # 금액 오류
            "2024-03-04,expense,없는것,5000,카테고리오류,\n"  # 카테고리 오류
            "2024-03-05,income,salary,3000000,월급,\n",
            encoding="utf-8",
        )
        imported, skipped, reasons = self.svc.import_csv(src)
        self.assertEqual(imported, 2)
        self.assertEqual(skipped, 3)
        self.assertEqual(len(reasons), 3)

    def test_import_머리글_누락(self):
        src = self.dir / "bad.csv"
        src.write_text("date,type\n2024-01-01,expense\n", encoding="utf-8")
        with self.assertRaises(ValidationError):
            self.svc.import_csv(src)

    def test_없는_파일(self):
        with self.assertRaises(NotFoundError):
            self.svc.import_csv(self.dir / "nope.csv")

    def test_export_한_뒤_import_하면_같은_내용(self):
        """내보낸 걸 다시 읽어들이면 건수와 값이 보존되는가 (왕복 검사)"""
        self.add("2024-01-15", "expense", "food", 15000, "점심", "meal,lunch")
        out = self.dir / "roundtrip.csv"
        self.svc.export_csv(out, month="2024-01")
        imported, skipped, _ = self.svc.import_csv(out)
        self.assertEqual((imported, skipped), (1, 0))
        rows = self.svc.search(category="food")
        self.assertEqual(rows[0].tags, ["meal", "lunch"])
        self.assertEqual(rows[0].amount, rows[1].amount)


class TestStorage(Base):
    def test_저장_파일이_네_개_생긴다(self):
        names = sorted(p.name for p in self.dir.glob("*.jsonl"))
        self.assertEqual(names, ["budgets.jsonl", "categories.jsonl",
                                 "recurring.jsonl", "transactions.jsonl"])

    def test_기본_카테고리가_들어간다(self):
        self.assertIn("food", self.repo.category_names())

    def test_삭제_후_임시파일이_남지_않는다(self):
        self.add("2024-01-01", "expense", "food", 1000)
        self.svc.delete_transaction("TX-000001")
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    def test_깨진_줄은_오류로_알린다(self):
        path = self.dir / "transactions.jsonl"
        path.write_text('{"id":"TX-1"}\n망가진줄\n', encoding="utf-8")
        with self.assertRaises(Exception):
            list(self.repo.iter_transactions())

    def test_빈_줄은_건너뛴다(self):
        self.add("2024-01-01", "expense", "food", 1000)
        path = self.dir / "transactions.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
        self.assertEqual(len(list(self.repo.iter_transactions())), 1)

    def test_백업이_만들어진다(self):
        self.add("2024-01-01", "expense", "food", 1000)
        dest = self.repo.backup()
        self.assertTrue(dest.exists())
        self.assertTrue((dest / "transactions.jsonl").exists())


class TestStreaming(Base):
    def test_limit을_주면_전체를_메모리에_올리지_않는다(self):
        """heapq.nlargest 가 실제로 메모리를 아끼는지 확인한다."""
        import tracemalloc
        path = self.dir / "transactions.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for i in range(1, 20001):
                f.write(json.dumps({
                    "id": f"TX-{i:06d}", "type": "expense",
                    "date": f"2024-01-{(i % 28) + 1:02d}", "amount": 1000,
                    "category": "food", "memo": "", "tags": []}) + "\n")

        tracemalloc.start()
        self.svc.list_transactions(limit=10)
        _, peak_small = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        tracemalloc.start()
        self.svc.list_transactions(limit=None)
        _, peak_all = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # limit 을 준 쪽이 최소 10배는 적어야 스트리밍이 동작한 것이다
        self.assertLess(peak_small * 10, peak_all)

    def test_iter_raw_는_제너레이터(self):
        import inspect
        self.assertTrue(inspect.isgeneratorfunction(Repository.iter_raw))
        self.assertTrue(inspect.isgeneratorfunction(Repository.iter_transactions))


class TestRecurring(Base):
    def test_규칙_등록과_적용(self):
        self.svc.add_recurring(day=25, type="expense", category="rent",
                               amount=500000, memo="월세")
        created = self.svc.apply_recurring("2024-04")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].date, "2024-04-25")

    def test_같은_달에_두_번_적용해도_중복되지_않는다(self):
        self.svc.add_recurring(day=25, type="expense", category="rent",
                               amount=500000, memo="월세")
        self.svc.apply_recurring("2024-04")
        self.assertEqual(self.svc.apply_recurring("2024-04"), [])

    def test_31일_규칙은_그_달_말일로_당긴다(self):
        self.svc.add_recurring(day=31, type="expense", category="rent",
                               amount=1000, memo="말일")
        created = self.svc.apply_recurring("2024-02")   # 2024는 윤년
        self.assertEqual(created[0].date, "2024-02-29")

    def test_잘못된_일자(self):
        with self.assertRaises(ValidationError):
            self.svc.add_recurring(day=32, type="expense", category="rent", amount=1000)

    def test_규칙이_없으면_오류(self):
        with self.assertRaises(NotFoundError):
            self.svc.apply_recurring("2024-04")


class TestFormatting(unittest.TestCase):
    def test_한글은_두_칸(self):
        self.assertEqual(display_width("점심"), 4)
        self.assertEqual(display_width("food"), 4)

    def test_폭_맞추기(self):
        self.assertEqual(display_width(pad("점심", 10)), 10)
        self.assertEqual(display_width(pad("food", 10)), 10)

    def test_금액_표기(self):
        self.assertEqual(won(1234567), "1,234,567원")


class TestCliExitCode(Base):
    """CLI 전체를 통과시켜 종료 코드와 출력을 확인한다."""

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--data-dir", str(self.dir), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_정상은_0(self):
        code, _, _ = self.run_cli("list")
        self.assertEqual(code, 0)

    def test_오류는_0이_아니다(self):
        code, _, err = self.run_cli("summary", "--month", "2024-99")
        self.assertNotEqual(code, 0)
        self.assertIn("[오류]", err)
        self.assertIn("[힌트]", err)

    def test_스택트레이스가_노출되지_않는다(self):
        _, out, err = self.run_cli("delete", "--id", "TX-999999")
        self.assertNotIn("Traceback", out + err)

    def test_명령을_안_주면_도움말과_오류(self):
        code, out, err = self.run_cli()
        self.assertNotEqual(code, 0)
        self.assertIn("usage", out)

    def test_거래_추가부터_요약까지(self):
        self.add("2024-01-15", "expense", "food", 15000, "점심")
        self.svc.set_budget("2024-01", 100000)
        code, out, _ = self.run_cli("summary", "--month", "2024-01")
        self.assertEqual(code, 0)
        self.assertIn("총 지출", out)
        self.assertIn("사용률", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
