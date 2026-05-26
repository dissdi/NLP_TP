# Sprint 1 Runbook — 사용자 로컬/Colab 실행 가이드

**작성:** 2026-05-26
**대상:** Sprint 1 — P0 27항목 MVP corpus 구축
**예상 시간:** 사용자 본인 환경에서 ~3~5시간 (네트워크 속도·HTTP sleep에 따라)

---

## 0. 왜 사용자가 직접 돌리나

Sprint 0은 Cowork 샌드박스에서 진행했지만, 현재(2026-05-26 후반) 샌드박스 네트워크에서 cnu.ac.kr 도메인 접근이 차단됨(`ProxyError 403`). 라이브 크롤링은 사용자 로컬 또는 Colab Free에서 실행해야 함. **코드·러너 스크립트는 모두 준비됨.**

산출물은 `data/sprint1/`에 떨어지고, 결과는 다음 채팅에서 Phase C(정제·청킹) 또는 Phase D-1(LLM Q&A 생성)에 그대로 이어짐.

---

## 1. 환경 준비

### 1-1. 의존성

이미 `environment.yml` / `requirements.txt`에 정의된 베이스 외 **HWP 처리용 추가 도구**가 필요:

```bash
# 베이스 (Sprint 0과 동일)
pip install -r requirements.txt
# 또는 conda env create -f environment.yml

# HWP 처리 (Sprint 1 추가)
pip install pyhwp                   # hwp5txt 명령 제공 — 경로 (b)

# 학칙(1.3) 표 구조 보존이 중요하면 추가로:
# Ubuntu/WSL: sudo apt install libreoffice
# macOS     : brew install --cask libreoffice
# Windows   : LibreOffice MSI 인스톨러
```

`hwp5txt`가 PATH에 잡히는지 확인:

```bash
which hwp5txt   # Linux/macOS
where hwp5txt   # Windows
```

### 1-2. Colab에서 돌릴 때

```python
!pip install -q -r /content/NLP_TP/requirements.txt
!pip install -q pyhwp
!apt-get install -y libreoffice >/dev/null 2>&1  # 학칙 변환용 (선택)
%cd /content/NLP_TP
!python -m scripts.sprint1_runner day1
```

Colab은 GPU 없이도 충분(크롤링은 CPU+네트워크 작업).

---

## 2. Sprint 1 진입 직전 체크 (Sprint 0 §7)

이 체크 한 번 돌리고 통과해야 본격 진입.

### 2-1. 사전 inspect

```bash
python -m scripts.sprint1_pre_inspect
# 자세히 보고 싶으면 --verbose
```

기대 결과: `dorm`·`gymn`·`health`·`cnustudent` 모두 어댑터 A의 셀렉터로 매칭됨. 매칭 안 되는 CMS가 있으면 `crawler/adapters/a_plus.py`의 `CONTENT_CONTAINER_CANDIDATES`에 추가 후 재실행.

### 2-2. HWP spike (선택)

게시판 첨부 1개로 (a) LibreOffice 경로와 (b) hwp5txt 경로 품질 비교:

```bash
# 백마광장 첨부 URL 하나로 spike
python -m crawler.hwp_pipeline spike \
  "https://plus.cnu.ac.kr/_prog/_board/common/download.php?code=sub07_0702&ntt_no=...&atch_no=..."
```

(URL은 inspect로 게시물 상세 페이지를 열어 첨부 링크 hover로 찾으면 됨.)

판단 기준:
- 텍스트 신뢰도 — preview 깨짐·누락 없는 쪽
- 표 구조 — (a)만 가능. 학칙·규정같이 표 많은 문서는 (a) 권장
- 자동화 — 게시판 첨부 다수 처리는 (b)가 가벼움

기본값: `hwp5txt` 우선, 실패하면 LibreOffice 폴백 (`crawl_hwp(prefer="hwp5txt")`).

---

## 3. Day별 실행

### 3-1. 일괄 실행 (한 번에 전부)

```bash
# Linux/macOS/WSL
bash scripts/run_sprint1.sh

# Windows
scripts\run_sprint1.bat
```

### 3-2. Day별 분리 실행 (권장 — 중간 점검 가능)

```bash
python -m scripts.sprint1_runner day1
# 결과: data/sprint1/day1/chunks.jsonl, logs/sprint1/day1.log
# 잠깐 확인 후 다음 Day

python -m scripts.sprint1_runner day2
python -m scripts.sprint1_runner day3
python -m scripts.sprint1_runner day4
python -m scripts.sprint1_process_attachments day4  # HWP/PDF 첨부 후처리
python -m scripts.sprint1_runner day5
```

### 3-3. 특정 task만

```bash
# 디버깅 또는 재실행
python -m scripts.sprint1_runner day2 --only 5.4_sub07_0702
python -m scripts.sprint1_runner day1 --dry-run   # URL 목록만
```

---

## 4. Day별 산출물 (예상)

| Day | 작업 | 대상 | 예상 시간 | 예상 글자수 |
|---|---|---|---|---|
| 1 | 어댑터 A·B 대량 1차 | 도메인 1·2·4 (7 task) | 20~30분 | ~50,000 |
| 2 | 백마광장 백본 4 카테고리 + 6·8 | 9 task + 4 게시판 | 60~90분 | ~280,000 |
| 3 | 어댑터 C·D + FAQ | 도메인 3·7·9 (13 task) | 30~40분 | ~70,000 |
| 4 | 셔틀 + 장학 FAQ + 학칙 HWP | 3 task + 첨부 후처리 | 20~40분 | ~30,000 (학칙 제외 ~10,000) |
| 5 | 1.2 졸업요건 (공통 + 5학과) | 6 task | 15~25분 | ~30,000 |
| **합계** | — | 27 P0 항목 | **~3~5시간** | **~460,000 (목표 490k의 94%)** |

각 Day 직후 `data/sprint1/<day>/chunks.jsonl` 한 줄씩 열어서 내용 확인 권장.

---

## 5. 트러블슈팅

### 5-1. 어떤 task가 0 청크로 끝남
- `data/sprint1/<day>/errors.json` 확인
- `logs/sprint1/<day>.log` 확인
- 흔한 원인:
  - URL이 추정값 (`sprint1_targets.json` notes에 "URL 추정"이라고 적힌 항목들)
  - 페이지 구조가 어댑터 A 셀렉터 4종으로 매칭 안 됨 → 해당 URL로 `python -m crawler.adapters.a_plus inspect URL` 돌려서 본문 컨테이너 찾고 `CONTENT_CONTAINER_CANDIDATES`에 추가
  - cnucoop, 학과 사이트는 CMS 다양 — fallback 인정 (Sprint 2로 미루기 OK)

### 5-2. 429 / 5xx 응답
- `crawler/http.py`의 `DEFAULT_SLEEP`를 0.8 → 1.5~2.0초로 늘리고 재시도
- IP 차단이 의심되면 잠깐 쉬었다가 재실행 (학교 IP에서 너무 빠르게 돌리지 말 것)

### 5-3. HWP 추출 실패
- `hwp5txt` 명령 없으면: `pip install pyhwp`
- HWPX 파일은 `pyhwp` 미지원 → LibreOffice 경로 사용 (`--hwp-prefer libreoffice`)
- 둘 다 실패하면: 수동으로 한글오피스에서 PDF로 export → `data/sprint1/day4/hwp/` 안에 복사 → `python -m crawler.pdf_pipeline crawl <local-pdf-path>`

### 5-4. 학칙(1.3) 어떻게 처리되나
- Day 4의 `1.3_학칙_HWP_list` task는 plus/_prog/rule 페이지를 어댑터 B로 돌림
- 페이지 자체에 메뉴/리스트만 있고 본문은 HWP 첨부 → 첨부 URL은 chunk.notes에 들어감
- `sprint1_process_attachments day4`로 HWP 다운로드·추출이 일어남
- **표 구조가 중요한 학칙 본문은 LibreOffice 경로 권장:**
  ```bash
  python -m scripts.sprint1_process_attachments day4 --hwp-prefer libreoffice --kinds hwp
  ```

### 5-5. 백마광장 페이지 수가 너무 많아 시간 폭주
- `sprint1_targets.json`에서 해당 task의 `pages`·`max_total` 줄이기
- 기본값 sub07_0702는 pages=8, max_total=150 — 평가셋 시드 가치 높아 넉넉히 잡음

---

## 6. Sprint 1 Exit 검증

전체 Day 끝나면 무조건 1회 실행:

```bash
python -m scripts.sprint1_verify
```

생성물:
- `logs/sprint1/report.md` — Sprint 1 결과 마크다운 리포트
- `logs/sprint1/coverage.json` — 도메인·카테고리별 청크/글자수 (다음 단계 핸드오프)

**Exit 기준:**
1. 총 글자수가 §10-2 추정(490k)의 **≥70%** 확보
2. 도메인별 청크 수 분포가 §7-2 평가표와 크게 어긋나지 않음 (e.g. 도메인 5가 ≥40% — 백마광장 백본)
3. P0 27 항목 중 ≥22개가 청크를 만들었음 (errors.json 확인)

위 셋 다 OK면 Phase C(정제·청킹) 또는 Phase D-1(Q&A 자동 생성)로 핸드오프.

---

## 7. 다음 단계로 핸드오프

Sprint 1 통과 후 다음 채팅 진입 옵션 (병렬 가능):

| 트랙 | 트리거 | 산출물 의존 |
|---|---|---|
| **Phase C (정제·청킹)** | corpus 정제, 임베딩용 청크 크기 결정 | `data/sprint1/*/chunks.jsonl` |
| **Phase D-1 (LLM Q&A 생성)** | FAQ 시드 + 정적 페이지로 평가셋 시드 생성 | `data/sprint1/day3/chunks.jsonl` (도서관 FAQ) + `data/sprint1/day4/chunks.jsonl` (장학 FAQ) |
| **Phase B Sprint 2** | P1 24항목 보강 (학칙·졸업요건 Stage 2 등) | Sprint 1 어댑터 검증 결과 |

memory에 Sprint 1 결과를 기록할 때 위 `report.md`·`coverage.json`을 첨부하면 다음 채팅에서 바로 이어갈 수 있음.

---

## 부록 A: 파일 위치 요약

```
NLP_TP/
├── crawler/                       # 어댑터·파이프라인 (Sprint 0 + Sprint 1 보강)
│   ├── adapters/
│   │   ├── a_plus.py              # +CONTENT_CONTAINER_CANDIDATES 보강
│   │   └── b_board.py             # +첨부 자동 추출 +페이지네이션 루프
│   ├── pdf_pipeline.py
│   └── hwp_pipeline.py            # 신규 (a·b 양쪽 지원)
├── scripts/                       # Sprint 1 러너 (신규)
│   ├── _common.py                 # DayRunner
│   ├── sprint1_pre_inspect.py     # 사전 정비 inspect
│   ├── sprint1_targets.json       # P0 27항목 URL 카탈로그
│   ├── sprint1_runner.py          # Day1~Day5 통합 러너
│   ├── sprint1_process_attachments.py  # 첨부 후처리 (HWP/PDF)
│   ├── sprint1_verify.py          # Exit 검증
│   ├── run_sprint1.sh             # 마스터 (Linux/macOS)
│   └── run_sprint1.bat            # 마스터 (Windows)
├── data/sprint1/                  # 산출물 (gitignore 대상)
│   ├── day1/chunks.jsonl
│   ├── day1/tables/*.csv
│   ├── day4/hwp/*.hwp(.converted.pdf)
│   └── ...
└── logs/sprint1/
    ├── day*.log
    ├── report.md                  # ← 다음 채팅으로 가져갈 핵심 산출물
    └── coverage.json              # ← 다음 채팅 입력
```

## 부록 B: 결과 확인 빠른 명령

```bash
# 각 Day 첫 청크 1건
for d in day1 day2 day3 day4 day5; do
  echo "=== $d ==="
  head -1 data/sprint1/$d/chunks.jsonl 2>/dev/null | python -m json.tool | head -10
done

# 도메인별 청크 수
cat data/sprint1/*/chunks.jsonl | python -c "
import sys, json
from collections import Counter
c = Counter()
for L in sys.stdin:
    d = json.loads(L)
    for x in d['domains']: c[x] += 1
for k in sorted(c): print(f'  domain {k}: {c[k]} chunks')
"
```
