"""CLI — 명령줄 입력을 해석하고 화면에 출력한다.

이 파일만 print() 와 input() 을 쓴다.
service 와 repository 는 화면을 모른다. 그래서 나중에 웹으로 바꿔도 그 둘은 그대로 쓴다.

과제 요구사항 1번
    - python -m budget_app <command> [options]
    - 모든 명령은 --help 로 사용법이 나와야 한다  → argparse 가 자동으로 만들어준다
    - 옵션 표기는 -- 로 통일
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .decorators import configure, handle_errors, log_call, timed
from .errors import AppError, ValidationError
from .formatting import bar, table, won
from .models import TX_TYPES
from .prompts import ask
from .repository import Repository
from .service import BudgetService


# ======================================================================
# 명령 구현
# 세 데코레이터를 순서대로 붙인다. 아래에서 위로 감싸진다.
#   @log_call  실행 기록을 남기고
#   @timed     걸린 시간을 재고
#   그 안에서 본래 일을 한다
# 예외 처리(@handle_errors)는 main 한 곳에만 붙여 종료 코드를 정한다.
# ======================================================================

@log_call
@timed
def cmd_add(svc: BudgetService, args: argparse.Namespace) -> None:
    """거래 추가 — 대화형. 틀리면 그 항목만 다시 묻는다."""
    date = ask("날짜(YYYY-MM-DD): ", svc.validate_date)
    tx_type = ask(f"타입({'/'.join(TX_TYPES)}): ", svc.validate_type)
    category = ask("카테고리: ", svc.validate_category)
    amount = ask("금액(양수): ", svc.validate_amount)
    memo = ask("메모(선택): ", lambda s: s, allow_empty=True, empty_value="")
    tags = ask("태그(쉼표로 구분, 없으면 엔터): ",
               svc.parse_tags, allow_empty=True, empty_value=[])

    tx = svc.add_transaction(date=date, type=tx_type, category=category,
                             amount=amount, memo=memo, tags=tags)
    print(f"[저장 완료] id={tx.id}")


@log_call
@timed
def cmd_list(svc: BudgetService, args: argparse.Namespace) -> None:
    rows = svc.list_transactions(limit=args.limit)
    _print_transactions(rows)


@log_call
@timed
def cmd_search(svc: BudgetService, args: argparse.Namespace) -> None:
    rows = svc.search(
        date_from=args.date_from, date_to=args.date_to,
        category=args.category, type=args.type,
        keyword=args.q, tag=args.tag, limit=args.limit,
    )
    _print_transactions(rows)


@log_call
@timed
def cmd_update(svc: BudgetService, args: argparse.Namespace) -> None:
    before, after = svc.update_transaction(
        args.id, date=args.date, type=args.type, category=args.category,
        amount=args.amount, memo=args.memo, tags=args.tags,
    )
    print(f"[수정 완료] id={after.id}")
    for field in ("date", "type", "category", "amount", "memo", "tags"):
        old, new = getattr(before, field), getattr(after, field)
        if old != new:
            print(f"  {field}: {old!r} -> {new!r}")


@log_call
@timed
def cmd_delete(svc: BudgetService, args: argparse.Namespace) -> None:
    tx = svc.delete_transaction(args.id)
    print(f"[삭제 완료] id={tx.id} | {tx.date} | {tx.category} | {won(tx.amount)}")


@log_call
@timed
def cmd_summary(svc: BudgetService, args: argparse.Namespace) -> None:
    s = svc.summary(args.month, top=args.top)

    if s["count"] == 0:
        print(f"{s['month']} 데이터 없음")
        return

    print(f"총 수입: {won(int(s['income']))}")
    print(f"총 지출: {won(int(s['expense']))}")
    print(f"잔액: {won(int(s['balance']))}")

    if s["budget"] is not None:
        usage = float(s["usage"] or 0)
        print(f"예산: {won(int(s['budget']))} (사용률 {usage * 100:.1f}%)")
        print(f"       [{bar(usage)}]")
        if s["over"]:
            over = int(s["expense"]) - int(s["budget"])
            print(f"[경고] 예산을 {won(over)} 초과했습니다.")

    top = list(s["top"])  # type: ignore[arg-type]
    if top:
        print(f"\n지출 TOP {len(top)}")
        for rank, (category, total) in enumerate(top, 1):
            print(f"{rank}) {category} {won(total)}")


@log_call
@timed
def cmd_budget_set(svc: BudgetService, args: argparse.Namespace) -> None:
    b = svc.set_budget(args.month, args.amount)
    print(f"[저장 완료] {b.month} 예산 {won(b.amount)}")


@log_call
@timed
def cmd_budget_list(svc: BudgetService, args: argparse.Namespace) -> None:
    rows = list(svc.repo.iter_budgets())
    if not rows:
        print("등록된 예산이 없습니다.")
        return
    print(table(["월", "예산"],
                [[b.month, won(b.amount)] for b in sorted(rows, key=lambda x: x.month)],
                ["left", "right"]))


@log_call
@timed
def cmd_category_add(svc: BudgetService, args: argparse.Namespace) -> None:
    name = args.name or ask("카테고리명: ", lambda s: s)
    print(f"[저장 완료] category={svc.add_category(name)}")


@log_call
@timed
def cmd_category_list(svc: BudgetService, args: argparse.Namespace) -> None:
    names = svc.repo.category_names()
    if not names:
        print("등록된 카테고리가 없습니다.")
        return
    for name in names:
        print(f"- {name}")


@log_call
@timed
def cmd_category_remove(svc: BudgetService, args: argparse.Namespace) -> None:
    moved = svc.remove_category(args.name, args.replace_with)
    if moved:
        print(f"[삭제 완료] category={args.name} ({moved}건을 {args.replace_with} 로 옮김)")
    else:
        print(f"[삭제 완료] category={args.name}")


@log_call
@timed
def cmd_export(svc: BudgetService, args: argparse.Namespace) -> None:
    n = svc.export_csv(args.out, month=args.month,
                       date_from=args.date_from, date_to=args.date_to)
    print(f"[완료] {args.out} ({n} records)")


@log_call
@timed
def cmd_import(svc: BudgetService, args: argparse.Namespace) -> None:
    imported, skipped, reasons = svc.import_csv(args.date_from)
    print(f"[완료] imported={imported}, skipped={skipped}")
    for reason in reasons:
        print(f"  건너뜀 - {reason}")


@log_call
@timed
def cmd_backup(svc: BudgetService, args: argparse.Namespace) -> None:
    dest = svc.repo.backup()
    print(f"[백업 완료] {dest}")


@log_call
@timed
def cmd_recurring_add(svc: BudgetService, args: argparse.Namespace) -> None:
    rule = svc.add_recurring(day=args.day, type=args.type, category=args.category,
                             amount=args.amount, memo=args.memo, tags=args.tags)
    print(f"[저장 완료] id={rule.id} 매월 {rule.day}일 {rule.category} {won(rule.amount)}")


@log_call
@timed
def cmd_recurring_list(svc: BudgetService, args: argparse.Namespace) -> None:
    rows = list(svc.repo.iter_recurring())
    if not rows:
        print("등록된 반복 규칙이 없습니다.")
        return
    print(table(["id", "일자", "타입", "카테고리", "금액", "메모"],
                [[r.id, f"매월 {r.day}일", r.type, r.category, won(r.amount), r.memo]
                 for r in rows],
                ["left", "right", "left", "left", "right", "left"]))


@log_call
@timed
def cmd_recurring_remove(svc: BudgetService, args: argparse.Namespace) -> None:
    svc.repo.remove_recurring(args.id)
    print(f"[삭제 완료] id={args.id}")


@log_call
@timed
def cmd_recurring_apply(svc: BudgetService, args: argparse.Namespace) -> None:
    created = svc.apply_recurring(args.month)
    if not created:
        print(f"{args.month} 에 새로 만들 내역이 없습니다. (이미 반영됨)")
        return
    print(f"[완료] {len(created)}건 생성")
    _print_transactions(created)


# ======================================================================
# 출력 도우미
# ======================================================================

def _print_transactions(rows: list) -> None:
    if not rows:
        print("조건에 맞는 내역이 없습니다.")
        return
    print(table(
        ["id", "날짜", "타입", "카테고리", "금액", "메모", "태그"],
        [[t.id, t.date, t.type, t.category, won(t.amount), t.memo, ",".join(t.tags)]
         for t in rows],
        ["left", "left", "left", "left", "right", "left", "left"],
    ))
    print(f"\n{len(rows)}건")


# ======================================================================
# 파서
# ======================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m budget_app",
        description="나만의 용돈 기입장 — 표준 라이브러리만 사용",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="예시:\n"
               "  python -m budget_app add\n"
               "  python -m budget_app list --limit 5\n"
               "  python -m budget_app summary --month 2024-01 --top 3\n",
    )
    parser.add_argument("--data-dir", default="data",
                        help="저장 폴더 (기본: data)")
    parser.add_argument("--verbose", action="store_true",
                        help="실행 시간 등 상세 정보를 함께 출력")

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # --- add ---
    p = sub.add_parser("add", help="거래 추가 (대화형)")
    p.set_defaults(func=cmd_add)

    # --- list ---
    p = sub.add_parser("list", help="거래 목록 (최신순)")
    p.add_argument("--limit", type=int, default=20, help="몇 건까지 (기본: 20)")
    p.set_defaults(func=cmd_list)

    # --- search ---
    p = sub.add_parser("search", help="조건 검색 (최신순)")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="시작 날짜")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="끝 날짜")
    p.add_argument("--category", help="카테고리")
    p.add_argument("--type", choices=list(TX_TYPES), help="income / expense")
    p.add_argument("--q", help="메모 키워드")
    p.add_argument("--tag", help="태그")
    p.add_argument("--limit", type=int, default=None, help="몇 건까지")
    p.set_defaults(func=cmd_search)

    # --- update (안 A: 옵션 기반) ---
    p = sub.add_parser("update", help="거래 수정 (옵션 기반)")
    p.add_argument("--id", required=True, help="수정할 거래 id")
    p.add_argument("--date", metavar="YYYY-MM-DD")
    p.add_argument("--type", choices=list(TX_TYPES))
    p.add_argument("--category")
    p.add_argument("--amount")
    p.add_argument("--memo")
    p.add_argument("--tags", help="쉼표로 구분")
    p.set_defaults(func=cmd_update)

    # --- delete ---
    p = sub.add_parser("delete", help="거래 삭제")
    p.add_argument("--id", required=True, help="삭제할 거래 id")
    p.set_defaults(func=cmd_delete)

    # --- summary ---
    p = sub.add_parser("summary", help="월별 요약")
    p.add_argument("--month", required=True, metavar="YYYY-MM")
    p.add_argument("--top", type=int, default=3, help="지출 TOP N (기본: 3)")
    p.set_defaults(func=cmd_summary)

    # --- budget ---
    p = sub.add_parser("budget", help="월 예산 관리")
    bsub = p.add_subparsers(dest="sub", metavar="<set|list>")
    q = bsub.add_parser("set", help="월 예산 저장")
    q.add_argument("--month", required=True, metavar="YYYY-MM")
    q.add_argument("--amount", required=True)
    q.set_defaults(func=cmd_budget_set)
    q = bsub.add_parser("list", help="예산 목록")
    q.set_defaults(func=cmd_budget_list)

    # --- category ---
    p = sub.add_parser("category", help="카테고리 관리")
    csub = p.add_subparsers(dest="sub", metavar="<add|list|remove>")
    q = csub.add_parser("add", help="카테고리 추가")
    q.add_argument("--name", help="생략하면 대화형으로 물어본다")
    q.set_defaults(func=cmd_category_add)
    q = csub.add_parser("list", help="카테고리 목록")
    q.set_defaults(func=cmd_category_list)
    q = csub.add_parser("remove", help="카테고리 삭제")
    q.add_argument("--name", required=True)
    q.add_argument("--replace-with", dest="replace_with",
                   help="사용 중인 내역을 옮길 대체 카테고리")
    q.set_defaults(func=cmd_category_remove)

    # --- export ---
    p = sub.add_parser("export", help="CSV 내보내기 (기간 조건 필수)")
    p.add_argument("--out", required=True, metavar="FILE")
    p.add_argument("--month", metavar="YYYY-MM")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    p.set_defaults(func=cmd_export)

    # --- import ---
    p = sub.add_parser("import", help="CSV 가져오기")
    p.add_argument("--from", dest="date_from", required=True, metavar="FILE")
    p.set_defaults(func=cmd_import)

    # --- backup (보너스 1) ---
    p = sub.add_parser("backup", help="data 폴더를 타임스탬프 붙여 백업")
    p.set_defaults(func=cmd_backup)

    # --- recurring (보너스 2) ---
    p = sub.add_parser("recurring", help="매달 반복되는 내역 규칙")
    rsub = p.add_subparsers(dest="sub", metavar="<add|list|remove|apply>")
    q = rsub.add_parser("add", help="반복 규칙 추가")
    q.add_argument("--day", required=True, help="매월 며칠 (1~31)")
    q.add_argument("--type", required=True, choices=list(TX_TYPES))
    q.add_argument("--category", required=True)
    q.add_argument("--amount", required=True)
    q.add_argument("--memo", default="")
    q.add_argument("--tags", default=None)
    q.set_defaults(func=cmd_recurring_add)
    q = rsub.add_parser("list", help="반복 규칙 목록")
    q.set_defaults(func=cmd_recurring_list)
    q = rsub.add_parser("remove", help="반복 규칙 삭제")
    q.add_argument("--id", required=True)
    q.set_defaults(func=cmd_recurring_remove)
    q = rsub.add_parser("apply", help="특정 월에 반복 내역 생성")
    q.add_argument("--month", required=True, metavar="YYYY-MM")
    q.set_defaults(func=cmd_recurring_apply)

    return parser


@handle_errors
def _run(argv: list[str] | None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        # 명령을 안 줬거나 budget/category/recurring 만 주고 하위 명령을 빼먹은 경우
        parser.print_help()
        raise ValidationError("실행할 명령을 지정해주세요.",
                              "사용 가능한 명령은 위 목록을 참고하세요.")

    data_dir = Path(args.data_dir)
    configure(log_path=data_dir / "app.log", verbose=args.verbose)

    repo = Repository(data_dir)
    if repo.ensure_ready():
        print(f"[안내] 저장 폴더를 준비했습니다: {data_dir}/")

    args.func(BudgetService(repo), args)


def main(argv: list[str] | None = None) -> int:
    """종료 코드를 돌려준다. 정상 0, 오류는 0이 아닌 값."""
    return _run(argv)
