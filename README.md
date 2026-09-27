# 나만의 용돈 기입장

코디세이 AI 올인원 2기 · AI 도구학습 · **B2-1** (Python과 Git 심화)

터미널에서 쓰는 가계부입니다. 수입·지출을 기록하고, 검색하고, 월별로 요약하고,
예산을 넘으면 경고합니다. **표준 라이브러리만 사용합니다** — `pip install` 할 것이 없습니다.

```
$ python -m budget_app add
날짜(YYYY-MM-DD): 2024-01-15
타입(income/expense): expense
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000001
```

---

## 실행

파이썬 3.10 이상이면 설치 없이 바로 돌아갑니다.

```bash
git clone https://github.com/DangChame/mission_b2_1_budget.git
cd mission_b2_1_budget
python3 -m budget_app --help
```

처음 실행하면 `data/` 폴더와 저장 파일이 자동으로 만들어지고, 기본 카테고리 5개가 들어갑니다.

```bash
python3 -m unittest discover -s tests -t .    # 테스트 62개
```

---

## 명령

모든 명령은 `--help` 로 사용법을 볼 수 있습니다. 옵션은 전부 `--` 로 시작합니다.

| 명령 | 하는 일 |
|---|---|
| `add` | 거래 추가 (**대화형**) |
| `list --limit N` | 최신순 목록 |
| `search` | 조건 검색 — `--from --to --category --type --q --tag` |
| `update --id ID` | 거래 수정 (**옵션 기반**) |
| `delete --id ID` | 거래 삭제 |
| `summary --month YYYY-MM --top N` | 월별 요약 + 예산 사용률 |
| `budget set --month --amount` / `budget list` | 월 예산 |
| `category add / list / remove` | 카테고리 관리 |
| `export --out FILE --month` | CSV 내보내기 |
| `import --from FILE` | CSV 가져오기 |
| `backup` | data 폴더 백업 *(보너스)* |
| `recurring add / list / remove / apply` | 매달 반복 내역 *(보너스)* |

공통 옵션 — `--data-dir DIR` (저장 폴더 변경), `--verbose` (실행 시간 표시)

### update 방식은 「옵션 기반」으로 고정했습니다

과제 요구사항 6번이 **안 A(옵션) 와 안 B(대화형) 중 하나를 문서에 명확히 고정**하라고 해서 적어둡니다.

> **안 A — 옵션 기반을 선택했습니다.**
> ```bash
> python3 -m budget_app update --id TX-000001 --amount 16000 --memo "점심 김치찌개"
> ```
> 고를 이유는 두 가지입니다.
> ① **준 필드만 바뀝니다.** 대화형으로 하면 안 바꿀 항목도 다시 물어보게 되고, 엔터를 잘못 치면 값이 날아갑니다.
> ② **명령 한 줄이 기록으로 남습니다.** 무엇을 어떻게 고쳤는지 셸 히스토리에 그대로 남아 재현이 됩니다.

### 사용 예

```bash
python3 -m budget_app list --limit 5
python3 -m budget_app search --from 2024-01-01 --to 2024-01-31 --type expense
python3 -m budget_app search --tag meal --q 점심
python3 -m budget_app budget set --month 2024-01 --amount 500000
python3 -m budget_app summary --month 2024-01 --top 3
python3 -m budget_app export --out 2024-01.csv --month 2024-01
python3 -m budget_app import --from 2024-01.csv
```

```
$ python3 -m budget_app summary --month 2024-01 --top 3
총 수입: 3,000,000원
총 지출: 543,000원
잔액: 2,457,000원
예산: 500,000원 (사용률 108.6%)
       [########################]
[경고] 예산을 43,000원 초과했습니다.

지출 TOP 3
1) rent 500,000원
2) food 23,000원
3) transport 20,000원
```

---

## 구조

과제 요구사항이 **최소 3개 모듈**을 요구합니다. 책임에 따라 8개로 나눴습니다.

```
budget_app/
  __main__.py      python -m budget_app 진입점
  cli.py           명령줄 해석 + 화면 출력      ← print / input 은 여기서만
  service.py       규칙 검증 + 계산
  repository.py    파일 읽기·쓰기              ← open 은 여기서만
  models.py        데이터 구조 (dataclass)
  decorators.py    로그 · 시간 측정 · 예외 처리
  formatting.py    표 정렬 출력
  prompts.py       대화형 입력 + 재입력
  errors.py        사용자에게 보여줄 오류 정의
tests/
  test_budget_app.py   테스트 62개
```

계층을 이렇게 잡았습니다.

```
cli.py        무엇을 하라고 시켰나   (사람과 대화)
  ↓
service.py    그게 되는 일인가       (규칙과 계산)
  ↓
repository.py 어디에 저장하나        (파일 입출력)
  ↓
models.py     무엇을 다루나          (데이터 모양)
```

**위 계층은 아래를 알지만, 아래는 위를 모릅니다.**
`service.py` 에는 `print` 가 없고 `repository.py` 에는 규칙이 없습니다.
그래서 화면을 웹으로 바꾸면 `cli.py` 만, 저장을 DB로 바꾸면 `repository.py` 만 고치면 됩니다.

---

## 저장 방식

**JSONL** 을 골랐습니다. 파일은 네 개로 나눕니다.

```
data/transactions.jsonl    거래 내역
data/categories.jsonl      카테고리
data/budgets.jsonl         월 예산
data/recurring.jsonl       반복 규칙 (보너스)
data/app.log               실행 로그
```

```json
{"id":"TX-000001","type":"expense","date":"2024-01-15","amount":15000,"category":"food","memo":"점심","tags":["meal"]}
```

### CSV 대신 JSONL 을 쓴 이유

| | JSONL | CSV |
|---|---|---|
| 한 줄만 읽어도 한 건 복원 | **가능** | 가능 |
| `tags` 같은 값 여러 개 | **배열 그대로** | 쉼표가 구분자와 겹쳐 따로 처리 필요 |
| 필드 추가 | 그 줄에만 키 추가 | 머리글 전체 변경 |

CSV 는 `import` / `export` 의 **교환 포맷**으로만 씁니다. 엑셀에서 열어야 하니까요.

CSV 스키마는 과제 요구사항대로 고정했습니다. UTF-8, 머리글 포함.

| 열 | 필수 | 설명 |
|---|:--:|---|
| `date` | Y | YYYY-MM-DD |
| `type` | Y | income / expense |
| `category` | Y | 등록된 카테고리 |
| `amount` | Y | 양수 정수 |
| `memo` | N | 문자열 |
| `tags` | N | 쉼표 구분 |

---

## 신경 쓴 것 네 가지

### 1. 제너레이터 — 파일을 통째로 안 읽습니다

요구사항 5번이 *"파일 전체를 한 번에 로드하지 않고, 제너레이터 기반 스트리밍"* 입니다.

`repository.iter_raw()` 는 `return` 이 아니라 **`yield`** 를 씁니다.
한 줄 내주고 그 자리에 멈춰 있다가, 다음을 요청하면 이어서 실행합니다.
그래서 파일이 몇 줄이든 **메모리에는 항상 한 줄만** 올라갑니다.

문제는 "최신순" 입니다. 정렬을 하려면 전부 봐야 하니 `sorted()` 를 쓰면 결국 다 메모리에 올라갑니다.
그래서 **`heapq.nlargest`** 를 씁니다. 크기 N짜리 힙 하나만 들고 스트림을 한 번 훑습니다.

**실제로 측정한 값입니다.** (5만 건 · 6.4MB)

| | 최대 메모리 |
|---|---|
| `list --limit 20` | **183 KB** |
| `limit` 없이 전체 | 27.2 MB |

**152배 차이**입니다. `tests/test_budget_app.py` 의 `TestStreaming` 이 이걸 검사합니다.

### 2. 데코레이터 — 공통 관심사를 한곳에

명령 함수 15개가 전부 로그를 남기고 시간을 잽니다. 그 코드를 함수마다 복사하면
로그 형식을 바꿀 때 15군데를 고쳐야 합니다.

```python
@log_call      # 언제 무슨 명령이 실행됐는지 data/app.log 에
@timed         # 걸린 시간 측정 (--verbose 면 화면에도)
def cmd_add(svc, args): ...
```

예외 처리(`@handle_errors`)는 `main` 한 곳에만 붙여 종료 코드를 정합니다.

### 3. 원자적 교체 — 쓰다가 죽어도 데이터가 안 날아갑니다

`update` / `delete` 는 파일을 다시 씁니다. 원본에 바로 쓰다가 프로그램이 죽으면
**파일이 반만 남아서 지금까지 쌓은 내역을 통째로 잃습니다.**

```python
1) .tmp 파일에 전부 쓴다        ← 실패해도 원본은 멀쩡
2) os.replace 로 이름을 바꾼다  ← 운영체제가 한 번에 끝낸다
```

`os.replace` 는 같은 파일시스템에서 **원자적**입니다. "바뀌기 전" 아니면 "바뀐 후"만 있고
그 중간이 보이지 않는다는 뜻입니다.

### 4. 타입 힌트 — 계약을 코드에 적습니다

```python
def add_transaction(self, *, date: str, type: str, category: str,
                    amount: str | int, memo: str = "",
                    tags: str | list[str] | None = None) -> Transaction:
```

본문을 안 봐도 **무엇을 받아 무엇을 돌려주는지** 알 수 있습니다.
파이썬이 실행 중에 검사해주지는 않지만, 에디터가 오타와 잘못된 사용을 미리 잡아줍니다.

---

## 오류 처리

과제 제약이 **스택트레이스 금지, 원인 + 해결 힌트** 입니다.

```
$ python3 -m budget_app add
날짜(YYYY-MM-DD): 2024-13-40
[오류] 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
[힌트] 예: 2024-01-15
날짜(YYYY-MM-DD):
```

대화형에서는 **틀린 항목만 다시 묻습니다.** 처음부터 다시 치게 하지 않습니다. (최대 3회)

| 종료 코드 | 언제 |
|---|---|
| `0` | 정상 |
| `1` | 예상한 오류 (형식 오류, 없는 id, 사용 중인 카테고리 등) |
| `2` | 예상 못 한 오류 / 잘못된 명령 |
| `130` | Ctrl+C |

---

## 테스트

```bash
python3 -m unittest discover -s tests -t .
```

```
Ran 62 tests in 0.327s
OK
```

`unittest` 를 쓰는 이유는 과제 제약 때문입니다. pytest 는 `pip install` 이 필요합니다.

검사하는 것 — 날짜·금액·타입·카테고리 검증, 윤년, id 채번, 최신순 정렬,
검색 조건 조합, 예산 초과 감지, 카테고리 삭제 규칙, CSV 왕복(export→import),
**스트리밍 메모리 측정**, 반복 규칙 말일 처리, 종료 코드, 스택트레이스 비노출.

---

## 보너스 과제

| # | 내용 | 상태 |
|---|---|:--:|
| 1 | **백업** — `backup` 이 타임스탬프 붙은 폴더로 복사 | ✅ |
| 2 | **반복 내역** — `recurring` 으로 월세·월급 자동 생성 | ✅ |
| 3 | **테이블 정렬** — 외부 라이브러리 없이 한글 폭까지 계산 | ✅ |
| 4 | **저장 원자성** — 임시 파일 + `os.replace` | ✅ |

보너스 3은 한글 때문에 조금 손이 갑니다.
`len('점심')` 은 2지만 터미널에서는 **4칸**을 씁니다.
`unicodedata.east_asian_width` 로 글자마다 폭을 재서 칸을 맞춥니다.

보너스 2의 `recurring apply` 는 **31일 규칙을 2월에 적용하면 말일로 당깁니다.**
2024년 2월이면 29일이 됩니다 (윤년).

---

## 요구사항 대조

과제 PDF의 요구사항과 코드 위치를 하나씩 맞춰본 표는
**[docs/요구사항_대조표.md](docs/요구사항_대조표.md)** 에 있습니다.
