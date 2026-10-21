# pii-guard-ko

글, 코드, 문서 파일을 공개하기 전에 한국 개인정보와 API 키가 섞여 있는지 찾아 주는 검사기입니다.
의존성 없는 파이썬 하나로 돌고, 인터넷에 아무것도 보내지 않으며, 찾은 값은 가려서만 보여 줍니다.

[English summary](#english)

## 왜 만들었나

정규식만 쓰는 검사기는 두 가지가 아쉬웠습니다.

- 놓치는 것: 확장자가 목록에 없는 파일(`.py`, `.env`, `NOTES` 같은 이름), 워드·엑셀 문서, CSV에서 머리글에만 "여권번호"라고 적힌 열, `연락처010...`처럼 한글에 붙은 번호.
- 잘못 잡는 것: 이미지 주소 속 13자리 숫자(`photo-1601...`)를 주민등록번호로, 입력칸 `placeholder="010-0000-0000"`을 휴대폰번호로, 밀리초 시각이나 주문번호를 주민등록번호로.

그래서 형식만 보지 않고 실제로 있을 수 있는 값인지 따져 봅니다.

- 주민·외국인등록번호: 생년월일이 실제 날짜인지, 체크섬이 맞는지 (2020년 10월 이후 번호는 체크섬이 없어서 문맥과 같이 봄)
- 카드번호: Luhn과 카드사 번호대(IIN). 시험용 카드 번호는 뺌
- 사업자등록번호: 국세청 검증식
- 전화번호: 실제 국번만, `0000`·`1234-5678`처럼 예시로 쓰는 번호는 뺌
- 주소(URL), 파일 경로, 해시, 소수, 버전 속 숫자는 뺌
- "주문번호", `created_at`, `request_id` 같은 말이 앞에 있으면 붙은 숫자는 개인정보로 보지 않음

## 설치

```
pip install pii-guard-ko            # 글 검사만
pip install "pii-guard-ko[images]"  # 사진 GPS 검사까지 (Pillow)
```

저장소에서 바로 쓰려면 `pip install -e .`

## 쓰는 법

```
pii-guard-ko scan 원고/                # 폴더 전체
pii-guard-ko scan memo.txt data.csv    # 파일 여러 개
cat draft.md | pii-guard-ko scan -     # 표준 입력
pii-guard-ko scan 원고/ --json         # 다른 도구에서 읽을 JSON
pii-guard-ko scan 원고/ --redact 가림/  # 찾은 값을 [휴대폰번호]처럼 바꾼 사본
pii-guard-ko scan 사진/ --images       # 사진 EXIF GPS
pii-guard-ko strip-gps 사진/           # GPS·작성자 정보를 지운 사본(이름.clean.jpg)
```

출력 예:

```
memo.txt:6:5  확실  휴대폰번호  010-****-**78  구분자 있는 휴대폰
memo.txt:10:5  의심  유선전화  0*-***-***1  유선(기관·가게일 수 있음)
확실 · 검사한 파일 14개 · 찾은 파일 6개 · 확실 12 · 의심 3 · 건너뜀 0
```

종료 코드: `0` 깨끗 · `1` 의심만 · `2` 확실 1건 이상 · `3` 도구 오류.
CI나 커밋 훅에서 `2`일 때 막으면 됩니다.

일부러 공개한 값(가게 대표 번호 등)이 있는 줄은 끝에 `pii-guard-ko: ignore`를 적으면 건너뜁니다.

## 잡는 것

| 종류 | 확실 | 의심 |
|---|---|---|
| 주민등록번호·외국인등록번호 | 체크섬 맞음, 또는 하이픈+문맥 | 하이픈만, 붙은 13자리+체크섬 |
| 휴대폰번호 | 구분자 있음, 붙은 11자리+문맥 | 붙은 11자리 |
| 유선전화 | | 늘 의심 (기관·가게 번호가 많음) |
| 이메일 | 개인 메일 도메인 | 회사·기관 도메인 |
| 카드번호 | Luhn+구분자 또는 문맥 | 붙은 숫자 |
| 계좌번호 | 은행·계좌 문맥 | 붙은 숫자+계좌 문맥 |
| 사업자등록번호 | | 체크섬 맞음 |
| 여권번호·운전면허번호 | 형식+문맥 | |
| 차량번호 | 차량 문맥 | 형식만 |
| 동·호수 | 아파트 ○○동 ○○○호 꼴 | |
| 도로명주소·이름 칸·생년월일 칸·공인 IP | | 늘 의심 |
| API 키·토큰 | 주요 서비스 키 형식, 개인 키 블록, 주소 속 비밀번호 | JWT, `api_key = "..."` 꼴 |
| 사진 | GPS | 작성자·기기 일련번호 |

읽는 파일: 텍스트로 읽히는 파일은 확장자와 상관없이 모두 (UTF-8, UTF-16, CP949).
HTML은 태그와 스타일을 걷어 내고 본문, 주석, `href`·`content`·`alt` 값을 봅니다. 스크립트 안은 메일과 키만 봅니다.
`.docx`, `.xlsx`, `.pptx`, `.hwpx`, `.odt`는 안의 글만 꺼내서 봅니다 (가린 사본은 만들지 않음).

## 한계

- 사람 이름과 문장 속 주소는 칸 이름(`성명:`, `예금주:`)이 있을 때만 잡습니다.
- 사진 속 글자(스크린샷의 번호 등)는 보지 않습니다.
- PDF, HWP(옛 형식)는 읽지 않습니다.
- 규칙 기반이라 완벽하지 않습니다. 공개 전 마지막 확인용으로 쓰고, 결과는 사람이 한 번 더 보세요.

## 시험

```
pip install -e ".[test]"
pytest
```

시험에 쓰는 번호는 `tests/bench.py`가 실행할 때마다 만들어 냅니다. 체크섬이 맞는 번호를 파일에 적어 두지 않기 위해서입니다.

## English

`pii-guard-ko` scans text files, office documents and photos for Korean personal data
(resident and foreigner registration numbers, phone numbers, card and bank account numbers,
business registration numbers, passport and driver's license numbers) and for API keys.
It is pure Python with no dependencies (Pillow is optional for photo GPS), works offline,
and only ever prints masked values.

It validates instead of pattern-matching alone: birth dates and checksums for registration
numbers, Luhn plus issuer ranges for cards, the official check digit for business numbers,
real area codes for phones. Numbers inside URLs, paths, hashes, versions, placeholders and
fields such as `order_id` or `created_at` are ignored.

```
pip install pii-guard-ko
pii-guard-ko scan ./docs --json
```

Exit codes: 0 clean, 1 suspicious only, 2 at least one sure hit, 3 error.
License: MIT.
