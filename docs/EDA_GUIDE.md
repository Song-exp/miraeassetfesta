# 📊 EDA & 온톨로지 설계 준비 가이드 (팀 배포용)

> **미래에셋 금융상품 AI Agent — 상품군별 데이터 탐색 및 온톨로지 설계 논의 준비**
> 대상: EDA 담당 전원

---

## 🚀 시작하기 (여기부터)

### 목적지

최종 목표는 "데이터를 파악하는 것"이 아니라 **다 같이 모여 온톨로지를 그리는 워크샵(§5)** 입니다.
지금 하는 EDA는 그 워크샵에 가져올 **재료**를 만드는 작업입니다.

### 읽는 순서

문서가 깁니다. **§0 → §2 → §3 → §4 만 읽으면 작업을 시작할 수 있습니다.**
§5 이후는 워크샵 때, §8(함정 목록)은 작업하면서 참조하세요.

### 5분 셋업

```bash
# 1) 원본 엑셀 8개를 팀 공유 드라이브에서 받아 1.금융상품/ 에 배치 (Git에 없습니다)

# 2) 환경
git pull
python -m venv .venv
.venv\Scripts\Activate.ps1                             # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 3) 데이터 준비 + 프로파일
python scripts/build_db.py
python scripts/profile_table.py <내_테이블>
python scripts/profile_table.py --report <내_테이블>    # 중요 발견 요약

# 4) 탐색 시작 — 템플릿을 복사해서 쓰세요
#    notebooks/eda_template.ipynb → notebooks/<domain>_<이름>.ipynb
```

### 세 가지만 기억해주세요

**1. 컬럼 사전 만들지 마세요.**
결측률·값 목록·분포는 스크립트가 이미 다 뽑습니다(`ontology/enums/*.auto.yaml`).
손으로 옮겨 적으면 느릴 뿐 아니라 **오타가 그대로 가드레일에 들어갑니다.**
여러분이 낼 건 **해석과 판단**입니다.

**2. 질의 20개(§4)가 가장 중요합니다.**
주최 측이 예시 질의를 제공하지 않습니다. 우리가 만드는 80문항이
앞으로 성능을 측정할 **유일한 기준**입니다.
마지막에 몰아 쓰지 말고 탐색하면서 같이 쓰세요 — 도메인 지식이 머리에 있는 지금이 제일 잘 써집니다.

**3. 온톨로지 구조는 워크샵에서 정합니다.**
무엇을 개체로 보고 무엇을 관계로 녹일지는 §5에서 전원이 함께 결정합니다.
개인 단계에서는 **§3의 질문 11개에만 답해 오시면 됩니다.**
*"어떻게 그려야 할지 모르겠다"* 는 상태로 오셔도 됩니다.

> 🔒 **원본 DB는 읽기 전용으로만 여세요.** 스크립트와 노트북 템플릿이 막아줍니다.
> 새 노트북을 만들더라도 템플릿 첫 셀은 복사해 쓰세요 — `to_sql` 한 줄이면 테이블이 날아갑니다.

> ⚠️ **§8에 이미 확인된 함정 9종이 있습니다. 재조사하지 마시고 거기 없는 걸 찾아주세요.**
> 예) 채권 `BD_KND`: `WHERE = '일반회사채'` → **188건** / `TRIM()` 적용 → **13,998건** (74배)
> 예) 국내ETF마스터 1,734건 중 **532건(30.7%)이 ETF가 아니라 ETN**입니다

> 🎯 **schema 엑셀의 `Sheet2_Sample` 을 반드시 여세요.** 주최 측이 제시한 분류 축(`axis_*`)과
> **정답 100건**이 들어 있습니다. 채권 8축 / 국내ETF 7축 / 공모펀드 6축. → §3 첫 절

---

## 0. 작업 지시 요약

### 전체 흐름 — 4단계

```
1단계  프로파일 자동 생성      스크립트   ─ 논의의 재료. 사람이 손대지 않음
   ▼
2단계  개인 탐색 + 질의 작성    각자      ─ 이 문서의 대부분
   ▼
3단계  온톨로지 설계 워크샵     전원      ─ 개체·관계·계층 합의 → ontology.ttl 초안
   ▼
4단계  enums·제약 확정         각자      ─ 워크샵 결론에 따라
```

### 파일 4종 — 무엇을 언제 만드나

**2단계에서 각자 낼 것은 아래 2번·3번, 두 개입니다.**

| # | 파일 | 만드는 시점 | 읽는 주체 | 형식 |
| :-: | :--- | :--- | :--- | :--- |
| 1 | `ontology/enums/<domain>.auto.yaml` | 1단계 — **스크립트가 생성** | 사람·2단계 재료 | 손대지 않음 |
| 2 | `docs/eda/<domain>_notes.md` | **2단계 — 각자** | 사람 (워크샵 참석자) | **자유** |
| 3 | `eval/questions_<domain>.jsonl` | **2단계 — 각자** | 자동 테스트 | **고정** (§4) |
| 4 | `ontology/enums/<domain>.yaml` | **2단계**(결측 판정) → 4단계(온톨로지 매핑) | **런타임 가드레일** | **고정** (§6) |

**기계가 읽는 파일(3·4번)은 형식 고정, 사람이 읽는 파일(2번)은 자유입니다.**
`_notes.md` 는 표를 쓰든 글로 쓰든 §3의 질문에 답만 있으면 됩니다.

> 📌 **4번은 두 번에 나눠 씁니다.**
> - **2단계** — `missing_semantics`(결측 판정)만. 컬럼 단위 판단이라 합의가 필요 없습니다
> - **4단계** — `canonical_*`(개체·관계 매핑). 이건 §5 워크샵에서 정해진 뒤에 씁니다
>
> 워크샵 전에 `canonical_*` 을 각자 쓰면 축 이름과 값이 제각각이라 병합되지 않습니다.
> 나머지 발견은 전부 **`_notes.md`(2번)** 에 적어두었다가 워크샵 후 옮깁니다.

### 작업 시 지켜야 할 단 하나의 원칙

**명세 문서에 적힌 데이터 제약을 믿지 말고, DB에 직접 물어서 확인하세요.**

실례 — 과제 명세에는 위험등급이 **1~5등급**으로 기술돼 있으나 실제 데이터는 다릅니다:

| 테이블 | 6등급 존재 | 비율 |
| :--- | ---: | ---: |
| `domestic_bonds` | **10,408건** | 24.6% |
| `public_funds` | 2,397건 | 2.5% |
| `domestic_etfs` | 21건 | 1.2% |

`1~5` 제약을 온톨로지에 넣으면 **채권 데이터의 1/4이 정상인데도 차단**됩니다.
→ **위험등급 범위는 `0~6` 으로 확정**했고, 관련 문서도 수정했습니다.

> 앞으로도 명세와 데이터가 어긋나면 **데이터를 채택하고, 어긋난 사실을 노트에 기록**한 뒤 T0에 알려주세요.

---

## 1. 담당 분할

컬럼 수 기준으로 부하를 맞춰 **4개 수직 트랙 + 1개 수평 역할**로 나눕니다.

| 트랙 | 테이블 | 건수 | 컬럼 | 담당 |
| :--- | :--- | ---: | ---: | :--- |
| **T1** | `domestic_bonds` (국내채권) | 42,394 | 40 | |
| **T2** | `domestic_etfs` (국내ETF) | 1,734 | 73 | |
| **T3** | `overseas_etfs` (해외ETF) | 5,646 | 49 | |
| **T4** | `public_funds` (공모펀드) | 95,619행 (고유 11,127) | 45 | |
| **T0** | **워크샵 진행 + 교차 관계 취합** | — | — | 개발 리드 |

> **T0가 하는 일:** T1~T4가 보낸 §3 질문 4·5의 답을 모아 테이블 간 불일치를 정리하고,
> 워크샵(§5) 안건을 구성합니다.
> T1~T4는 각자 자기 테이블만 보기 때문에 **테이블을 관통하는 관계는 취합하지 않으면 드러나지 않습니다.**
> → **§3 질문 5·9·11의 답은 워크샵 전에 T0에 보내주세요.**

> 📌 **T2 주의:** `domestic_etfs` 1,734건은 ETF만이 아닙니다. **ETN이 532건(30.7%) 섞여 있습니다.**
> 구분 컬럼은 `pd_grp_no` (`'ETF'` 1,202 / `'ETN'` 532). 상세는 §8-⑤.

---

## 2. 1단계 — 데이터 프로파일 자동 생성

**사람이 손으로 뽑지 않습니다.** 결측률·distinct·값 목록·분포는 판단이 들어가지 않는 기계적 사실이라,
손으로 옮겨 적으면 느릴 뿐 아니라 **오타가 그대로 가드레일 화이트리스트가 됩니다.**

### 실행 준비 (최초 1회)

원본 엑셀 8개 파일(`1.금융상품/`)은 Git에 없습니다. **팀 공유 드라이브에서 받아 프로젝트 루트에 두세요.**

```bash
git pull

# 가상환경 (Windows PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
#   macOS/Linux → python3 -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt   # dev = 노트북용 (§3)
python scripts/build_db.py          # 엑셀 → SQLite (data/financial_products.db 생성)
```

> ⚠️ **이미 가상환경을 만들어 둔 분도 `pip install` 을 다시 실행하세요.**
> 프로파일러가 `pyyaml` 을 새로 씁니다. 안 하면 `ModuleNotFoundError: No module named 'yaml'` 로 죽습니다.
>
> `requirements-dev.txt` 는 노트북용(`jupyterlab`·`ipykernel`)이라 지금 같이 깔아두면 §3에서 바로 씁니다.
> **제출용 Dockerfile 에는 넣지 마세요** — `requirements.txt` 만으로 API 서버가 구동되어야 합니다.

### 실행

```bash
python scripts/profile_table.py                 # 4개 테이블 전체 (약 40초)
python scripts/profile_table.py domestic_etfs   # 담당 테이블만
```

인자 없이 돌리면 전체, 테이블명을 주면 그것만 처리합니다.
전 컬럼 풀스캔이라 공모펀드(95,619행 × 45컬럼)가 30초 정도로 가장 오래 걸립니다.

> 🔒 **원본은 훼손되지 않습니다.** 스크립트는 DB를 **읽기 전용(`mode=ro`)** 으로 열기 때문에,
> 실수로 쓰기 코드가 들어가도 커넥션이 거부합니다 (`attempt to write a readonly database`).
> 원본 엑셀은 열지도 않습니다. 최악의 경우에도 `python scripts/build_db.py` 로 DB가 재생성됩니다.

### 출력

| 파일 | 내용 | Git |
| :--- | :--- | :--- |
| `ontology/enums/<domain>.auto.yaml` | 컬럼 프로파일 + 발견 목록 | **gitignore** |
| `ontology/enums/<domain>.<column>.values.txt` | distinct 200종 초과 컬럼의 값 목록 | **gitignore** (총 10MB+) |

**둘 다 커밋하지 않습니다.** 스크립트로 언제든 재생성되고, 탐지기가 바뀌면 전체가 달라져
diff 노이즈가 큽니다. → **각자 로컬에서 직접 돌리세요.** (40초)

**손으로 편집하지도 마세요.** 실행할 때마다 통째로 덮어씁니다.
사람의 판단은 `<domain>.yaml`(§6)에 씁니다 — 이건 커밋 대상입니다.

### 뽑히는 것 — **사실만** 냅니다

| 항목 | 내용 |
| :--- | :--- |
| `null` / `blank_string` | 각각의 건수 (합치지 않음) |
| `values_present` | 값이 들어 있는 행 수 = `total − null − blank` |
| `judgment_needed` | **결측일 수도 있는 값 목록** — 판정은 사람이 (§3 결측 판정) |
| distinct 값 목록 | 값 + 건수. 200종 초과 시 별도 `.txt` |
| 수치 분포 | min / p01 / p50 / p99 / max / mean / 0의 개수 |
| 한글 컬럼명 | `schema_metadata` 테이블(207행) 조인 |
| **탐지기 결과** | 아래 12종 — 각 발견마다 재현 SQL 포함 |
| **`group_findings`** | 컬럼 그룹별 응축 (§ 아래) |

> 🔑 **`missing_rate`(결측률)를 내지 않습니다.**
> *"무엇을 결측으로 볼 것인가"* 는 사실이 아니라 **판정**입니다.
> `null` 개수는 사실이고, `'해당없음' 95,451건`도 사실이지만,
> **그 둘을 합쳐 "결측 99.9%"라고 하는 건 결정**입니다.
> 그 결정은 §3에서 사람이 내리고 `<domain>.yaml` 에 선언합니다.

### 탑재된 탐지기 12종

| 탐지기 | 잡아내는 것 | 관련 |
| :--- | :--- | :--- |
| `padding` | 앞뒤 공백 패딩 — 정확일치가 조용히 실패 | §8-① |
| `blank_string` | 공백만 든 문자열 (NULL 아닌 결측) | §8-② |
| `judgment_needed` | `not provided`·`해당없음` 류 — **결측 여부 판정 대기** | §8-② |
| `zero_heavy` | non-null의 30% 이상이 `0` — 미입력을 0으로 채웠는지 | |
| `repeated_extreme` | 극단값이 정확히 반복 — 수치형 센티넬(`-100` 등) 의심 | |
| `outlier_high` | 최대값이 p99의 5배 초과 | §8-⑧ |
| `wide_range` | **비율 컬럼**인데 p99가 p50의 10배 초과 — 단위 의심 | §8-⑧ |
| `multivalue` | 한 칸에 콤마로 여러 값 | §8-④ |
| `mixed_type_categorical` | 설명값 사이에 미해독 숫자 코드 | §8-⑥ |
| `empty_column` / `constant_column` | 전 레코드 결측 / 값이 한 종류뿐 | |
| `boolean_variant` | `_yn` 플래그의 표현 방식 (테이블마다 다름) | §8-⑨ |
| `duplicate_rows` / `composite_key_hint` | PK 중복 + **무엇이 행을 가르는지 자동 추정** | §8-⑦ |

> 마지막 항목이 §8-⑦(공모펀드 행 중복)을 자동으로 재현합니다. 실행하면 이렇게 나옵니다:
> ```
> 🔴 [not_unique_key] 'itm_no' 는 유일하지 않음 — 95,619행 / 고유 11,139개 (평균 8.6배 중복)
> 🔴 [composite_key_hint] 'itm_no'='KR5153450333' 인 16개 행에서 값이 달라지는 컬럼은
>    ['prfd_attr_cd'] 뿐 — 실질 복합키는 ('itm_no', 'prfd_attr_cd') 로 추정
> ```

### 결과 읽는 법

`.auto.yaml`은 `meta` / `table_findings` / **`group_findings`** / `columns` 네 블록입니다.

**컬럼 하나:**

```yaml
cu_charge_rt:
  korean_name: 총보수요율
  kind: numeric
  total: 1734
  null: 1517
  blank_string: 0
  values_present: 217            # ← 값이 들어 있는 행 (결측률이 아님)
  distinct_count: 17
  numeric:
    p50: 0.0
    max: 0.64
    n_zero: 150                  # ← 값은 있는데 0
  findings:
  - detector: zero_heavy
    severity: high
    message: non-null 217건 중 150건(69%)이 0 — 실제 0인지 미입력인지 확인 필요. 실질 모수는 67건
```

**판정이 필요한 값이 있으면:**

```yaml
cu_base_index:
  values_present: 5638
  judgment_needed:               # ← 사람이 결측 여부를 정할 값
  - value: Index is not provided by Management Company
    count: 1984
    hint: not_provided           # 문장형 → 결측 가능성 높음
  - value: 해당없음
    count: 95451
    hint: not_applicable         # → 정보일 가능성 높음
```

**중요한 것만 먼저 보려면 — `--report`**

73컬럼짜리 yaml을 처음부터 읽을 필요 없습니다. 재실행 없이 요약만 뽑습니다:

```bash
python scripts/profile_table.py --report                 # 4개 테이블
python scripts/profile_table.py --report domestic_etfs   # 담당 테이블만
```

```
📊 [public_funds] 95,619행 × 45컬럼

  🔴 [테이블] not_unique_key
      'itm_no' 는 유일하지 않음 — 95,619행 / 고유 11,139개 (평균 8.6배 중복)

  ▪ 그룹 _yn  (6개 컬럼)
      ─ boolean_variant: 6/6 전부 해당 → 이 그룹의 성질 (개별 조치 불필요)
      ⚠️ 값 표현이 5가지로 갈림:
         numeric:0.0|0.0     ← hdge_fd_yn, ofsfd_yn
         00080008|N|Y        ← exchdg_yn
         판매완료|판매중         ← sale_yn
         KRZ50226929C|Y      ← thco_sale_yn

  📉 실제 값이 절반 미만인 컬럼 (답변 정책 필요)
       itm_eabrv_nm            172 / 95,619

  ❓ 결측 여부 판정 필요 — <domain>.yaml 의 missing_semantics 에 선언하세요
       cu_base_index         1,984건  [not_provided]  'Index is not provided by Management…'
```

**보는 순서**

1. **`🔴 [테이블]`** — 테이블 전체에 걸린 문제(PK 중복 등). 가장 파급력이 큽니다
2. **`▪ 그룹`** — `전부 해당` 은 그룹의 성질이라 넘기고, **`⚠️` 만 개별 확인**
3. **`📉` 저모수 컬럼** — 답변 정책(`확인할 수 없음` / 모수 명시)이 필요한 곳
4. **`❓` 판정 대기** — §3 🕳️ 절차로 판정하고 `missing_semantics` 에 선언
5. 관심 가는 항목은 `.auto.yaml` 의 `repro_sql` 을 복사해 직접 돌려보세요

> ⚠️ **탐지기 결과는 "사실"이지 "결론"이 아닙니다.**
> `zero_heavy`가 울렸다고 그 컬럼이 잘못된 건 아닙니다 — 진짜 무보수 ETF일 수도 있습니다.
> 판단은 원본 schema 엑셀과 대조해 여러분이 내리고, **탐색 노트에 씁니다.**

### 🔧 탐지기 추가 — 발견을 전원에게 전파하는 방법

**새로운 데이터 함정 패턴을 발견하면, 노트에 적는 것으로 끝내지 말고 탐지기로 만들어 주세요.**
함수 하나를 쓰고 리스트에 등록하면 **4개 테이블 전체에 자동으로 적용**됩니다.
한 사람이 자기 테이블에서 찾은 것이, 아무도 안 찾아본 다른 테이블에서도 그 자리에서 드러납니다.

```python
# scripts/profile_table.py

def detect_my_pattern(ctx):
    n = ctx.scalar('SELECT COUNT(*) FROM {t} WHERE ...')   # {t}=테이블, {c}=컬럼
    if not n:
        return []
    return [Finding("my_pattern", "medium", f"설명 {n:,}건", n, ctx.sql('...'))]

DETECTORS = [..., detect_my_pattern]      # ← 등록
```

`ctx`가 이미 갖고 있는 것: `kind`(numeric/text/empty) · `total` · `n_null` · `n_blank` ·
`n_padded` · `n_distinct` · `values`(값+건수) · `numeric`(분위수) · `korean_name`,
그리고 `is_continuous` / `is_rate_like` 판별자.

> **무엇을 탐지기로 만들고 무엇을 노트에 쓰나 — 기준은 하나입니다.**
> **"이걸 다른 테이블에도 기계적으로 돌릴 수 있나?"**
>
> | 발견한 것 | 어디로 |
> | :--- | :--- |
> | *"한 칸에 콤마로 여러 값이 들어있다"* — **패턴** | ✅ 탐지기 |
> | *"`or_attr_desc='06'`이 5,436건"* — **사실** | ❌ `.auto.yaml`에 자동으로 나옴 |
> | *"'06'은 파생형 코드로 추정된다"* — **해석** | ❌ 탐색 노트로 |
> | *"`AA0`은 사용자가 말하는 `AA`다"* — **해석** | ❌ 탐색 노트로 |
>
> 개별 사실이나 해석을 스크립트에 하드코딩하면 데이터가 코드에 박히는 것입니다.

탐지기는 PR로 보내주세요. 리드가 머지하면 전원이 다시 돌립니다.

### 담당자가 이 단계에서 할 일

- [ ] 원본 엑셀 8개를 공유 드라이브에서 받아 `1.금융상품/` 에 배치
- [ ] 가상환경 생성 + `pip install -r requirements.txt` (**기존 환경도 재실행** — `pyyaml` 추가됨)
- [ ] `python scripts/build_db.py` → `data/financial_products.db` 생성 확인
- [ ] `python scripts/profile_table.py <domain>` → `.auto.yaml` 생성
- [ ] `table_findings` 와 `severity: high` 항목을 먼저 훑기
- [ ] 원본 `1.금융상품/<테이블ID>_*_schema.xlsx` **두 시트를 모두** 열기
  - `Sheet1_Schema` — **컬럼 정의·단위·PK 표기** 대조 (DB에 없는 정보. 단위 틀리면 답변이 100배 틀립니다)
  - `Sheet2_Sample` — 🎯 **`axis_*` 분류 축 + 정답 100건** (§3 참조)

> 📌 **`Sheet1_Schema` 의 `PK/FK` 열에 주최 측이 키를 표기해 뒀습니다.**
> 공모펀드 `(itm_no, prfd_attr_cd, zrin_fd_ivst_risk_gcd)` · 국내ETF `(pd_exg_mkt_cd, pd_itm_no, pd_itm_no_ma)` ·
> 해외ETF `(pd_itm_no)` · **국내채권은 표기 없음**.
> 실측하면 다를 수 있습니다 — 공모펀드는 `(itm_no, prfd_attr_cd)` 2개만으로 완전한 키였습니다.
> **표기를 확인하고, 실제로 유일한지 검증하세요.**

프로파일은 **결론이 아니라 재료**입니다. 여기서부터 진짜 작업이 시작됩니다.

---

## 3. 2단계 — 개인 탐색: 답해야 할 질문

**산출물: `docs/eda/<domain>_notes.md` — 형식 자유.**
표를 쓰든 글로 쓰든 상관없습니다. 아래 질문에 답이 있으면 됩니다.

컬럼 사전은 만들지 마세요 — `.auto.yaml`에 이미 있습니다. **여기서 원하는 건 판단과 해석입니다.**

---

### 🧪 탐색은 노트북에서 — 템플릿 제공

SQL 돌리고 결과 보고 다시 묻는 반복이 아래 질문 11개를 푸는 작업 그 자체라, **주피터 노트북이 가장 잘 맞습니다.**
`notebooks/eda_template.ipynb` 를 준비해 뒀습니다.

```bash
pip install -r requirements-dev.txt   # 🚀 시작하기에서 이미 깔았다면 생략
jupyter lab                           # 또는 VS Code에서 .ipynb 열기
```

> **커널을 반드시 `.venv` 로 잡으세요.** 시스템 파이썬이면 `pandas`·`pyyaml`이 없습니다.
> VS Code는 우측 상단 커널 선택에서 `.venv` 를, JupyterLab은 위 명령을 venv 활성화 상태에서 실행하면 됩니다.

**템플릿을 복사해서 쓰세요** — `notebooks/<domain>_<이름>.ipynb`. 원본 템플릿은 그대로 둡니다.

#### 🔒 노트북에서는 원본 DB가 실제로 깨질 수 있습니다

`profile_table.py` 는 읽기 전용으로 열지만 **노트북에서 직접 쓰는 셀은 그 보호를 안 받습니다.**
게다가 노트북은 셀을 순서 없이 재실행하는 게 자연스러워서 스크립트보다 위험합니다.

```python
df.to_sql('domestic_etfs', conn, if_exists='replace')   # ← 오타 하나로 테이블 증발
```

템플릿 첫 셀이 이걸 막습니다. **다른 노트북을 새로 만들더라도 이건 그대로 복사해 쓰세요:**

```python
conn = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True)   # 쓰기 시도 → 예외
```

템플릿은 여기서 한 발 더 나가, **쓰기가 실제로 막혔는지 확인하고 안 막혔으면 멈춥니다.**

#### 템플릿에 들어 있는 것

| 절 | 내용 |
| :--- | :--- |
| 안전 셋업 | 읽기 전용 커넥션 + 쓰기 차단 검증 + `DOMAIN` 변수 하나만 바꾸면 됨 |
| 헬퍼 | `q()` `vals()` `miss()` `peek()` `cross()` `kor()` — **전부 `TRIM()` 기본 적용** |
| 1단계 요약 | `.auto.yaml` 을 읽어 `table_findings` · high · 저모수 컬럼 출력 |
| §3 질문 11개 | 마크다운 셀로 박혀 있고 그 아래 출발점 코드 — 답을 채워 나가는 구조 |
| §4 질의 작성 | `QUESTIONS` 리스트 → **전량 `gold_sql` 실행 검증** → `jsonl` 자동 생성 |

`cross()` 가 §3 질문 5(다른 테이블과 표기가 같은가) 전용입니다 — 두 테이블의 값 집합을
**겹침 / 우리만 / 상대만** 으로 갈라 보여줍니다.

#### ⚠️ 노트북은 산출물이 아닙니다

> **노트북 = 작업장 / `_notes.md` + `.jsonl` = 산출물**

개인 노트북은 `.gitignore` 되어 있습니다 (`notebooks/eda_template.ipynb` 만 커밋됨).
`.ipynb` 는 git diff 가 안 읽혀 리뷰가 안 되고, 탐색 과정이 전부 남아 결론이 묻힙니다.

**결론은 반드시 `_notes.md` 로 옮겨 적으세요. 노트북에만 있으면 없는 것과 같습니다.**

---

### 📦 컬럼을 하나씩 보지 말고 **그룹으로** 보세요

207컬럼을 하나씩 훑으면 판단할 게 200건이 됩니다. **컬럼명 접미사로 묶으면 20건 안팎**으로 줍니다.
프로파일러가 `group_findings` 로 자동 응축해 주고, `--report` 가 그룹 중심으로 출력합니다.

그룹으로 보면 이 구분이 드러납니다:

| 패턴 | 해석 | 대응 |
| :--- | :--- | :--- |
| **그룹 전체가 걸림** | 그 그룹의 **성질** | 무시하거나 규칙 하나로 처리 |
| **그룹 일부만 걸림** | **진짜 이상치** | 개별 확인 |
| **테이블 단위로 갈림** | **소스 시스템 차이** | 테이블별 정규화 규칙 |

실제 사례:

```
▪ 그룹 _yn (6개)
    ─ boolean_variant: 6/6 전부 → 그룹의 성질 (개별 조치 불필요)
    ⚠️ 값 표현이 5가지로 갈림:
       numeric:0.0|0.0    ← hdge_fd_yn, ofsfd_yn
       00080008|N|Y       ← exchdg_yn        ← 오염
       판매완료|판매중        ← sale_yn          ← 한글
       KRZ50226929C|Y     ← thco_sale_yn     ← 오염
```

컬럼별 목록에 흩어져 있을 땐 안 보이던 **오염 2건이 한 화면에서 잡힙니다.**

그리고 **패딩은 컬럼 성격이 아니라 테이블 성격**이었습니다:

| 테이블 | 패딩 컬럼 | 비율 |
| :--- | ---: | :--- |
| `domestic_bonds` | 6개 | **95~98%** ← 고정폭 레거시 |
| `domestic_etfs` | 4개 | **89~100%** |
| `overseas_etfs` | **0개** | 깨끗 |
| `public_funds` | 7개 | 0~2% (산발) |

→ 정규화 규칙을 **컬럼별이 아니라 테이블별**로 세우면 됩니다.

---

### 🕳️ 결측 판정 — 채우지 말고 **분류**하세요

> 🔴 **이 프로젝트에서는 결측을 채우면(impute) 안 됩니다.**
> 일반 EDA는 평균·중앙값 대치를 하지만, 여기선 **환각 방지가 최우선**입니다.
> 없는 값을 만들어내는 게 곧 환각입니다.
> **전처리 = 채우기가 아니라 "유형을 판정하고 라벨링하기"** 입니다.

#### 결측 4유형

| 유형 | 뜻 | 판정법 | 런타임 응답 |
| :--- | :--- | :--- | :--- |
| **① 해당없음**<br>`not_applicable` | 그 대상엔 원래 없는 속성 | **다른 컬럼과 완벽 대응**하는지 확인 | "그 상품에는 해당하지 않습니다" |
| **② 미제공**<br>`missing` | 제공자가 안 줌 | 명세에 명시 / 문장형 센티넬 | "데이터 미제공" |
| **③ 진짜 결측** | 있어야 하는데 없음 | ①②가 아닌 `null` | "확인할 수 없음" |
| **④ 위장 결측** | `null` 아닌 형태 | 공백문자열 · 센티넬 · `0` 다수 | ②③으로 재분류 |

**①과 ②를 가르는 게 핵심입니다.** 실증 사례:

```sql
-- ① 해당없음 — 채권 매수수익률
SELECT
  SUM(CASE WHEN BUY_YIELD IS NOT NULL AND BUYABLE_QUANTITY IS NOT NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN BUY_YIELD IS     NULL AND BUYABLE_QUANTITY IS     NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN (BUY_YIELD IS NULL) <> (BUYABLE_QUANTITY IS NULL) THEN 1 ELSE 0 END)
FROM domestic_bonds;
-- ▶ 881 / 41,513 / 0   ← 엇갈림 0건 = 완벽 대응
```

**결측률 97.9%가 아니라 "매수 가능한 채권이 881개뿐"** 입니다.
과제 명세에도 *"매수/세후 수익률은 **매수가능 종목 일부만** 수록"* 이라고 적혀 있습니다.
→ 이건 데이터 품질 문제가 **아닙니다.**

```sql
-- ① 해당없음 — 펀드 사모구분
SELECT trim(prvo_fd_desc), trim(prvo_pbff_desc), COUNT(*)
FROM public_funds GROUP BY 1,2;
-- ▶ ('해당없음','공모') 95,451 / ('일반사모(2015년전)','사모') 102   ← 1:1 대응
```

`'해당없음'` 은 **"공모라서 사모 세부구분이 없다"는 정보**이지 결측이 아닙니다.

```
-- ② 미제공 — 해외ETF 기초지수
"Index is not provided by Management Company"  1,984건
   → 지수는 있는데 운용사가 안 준 것. 결측으로 처리
```

#### 명세가 알려주는 결측 사유

📄 과제 PDF의 데이터 명세표에 **결측 사유가 일부 명시**되어 있습니다:

| 테이블 | 명세 기술 | 해석 |
| :--- | :--- | :--- |
| 국내채권 | *"매수/세후 수익률은 **매수가능 종목 일부만** 수록"* | ① 해당없음 |
| 국내ETF | *"기초지수·총보수는 **일부 종목만** 수록"* | ② 미제공 |
| 공모펀드 | *"**보수 정보 미포함**"* | ② 미제공 (컬럼 자체 없음) |

> ⚠️ `*_schema.xlsx` 에는 **nullable 표기가 없습니다.** 위 3건 외에는 우리가 판정해야 합니다.

#### 판정을 선언하는 법

**노트북 템플릿의 「🕳️ 결측 판정」 절이 이 작업을 순서대로 안내합니다.**
결측 컬럼 나열 → 원인 교차 확인(`why_missing`, `co_missing`) → 판정 기록 → yaml 내보내기.

`ontology/enums/<domain>.yaml` 에 씁니다. **이 파일은 2단계에서 만들기 시작합니다**
(결측 판정은 컬럼 단위라 워크샵 합의가 필요 없습니다).

> 🔴 **판정을 노트북에만 적지 마세요.** 노트북은 `.gitignore` 대상이라 전달되지 않습니다.
> 반드시 yaml 로 내보내야 런타임과 팀원이 봅니다. (§6 참조)

```yaml
domain: public_funds
columns:
  prvo_fd_desc:
    missing_semantics:
      # prvo_pbff_desc='공모' 와 1:1 대응 → 정상 정보
      "해당없음": not_applicable
  cu_base_index:
    missing_semantics:
      "Index is not provided by Management Company": missing
```

선언 후 프로파일러를 다시 돌리면 반영됩니다:

```bash
python scripts/profile_table.py public_funds
# ▶ (missing_semantics 2컬럼 반영)
```

> ✅ 이 파일은 **커밋 대상**입니다 (`.auto.yaml` 은 gitignore).

---

### 🎯 먼저 볼 것 — schema 엑셀의 `axis_*` 정답 시트

🚨 **`1.금융상품/<테이블ID>_*_schema.xlsx` 의 `Sheet2_Sample` 시트에,
DB에는 없는 `axis_*` 컬럼이 샘플 100건의 정답값과 함께 들어 있습니다.**

주최 측이 **기대하는 분류 축**을 제시해 둔 것입니다. 4개 파일 중 3개에 있습니다.

| 테이블 | 축 | 목록 |
| :--- | :-: | :--- |
| `domestic_bonds` | **8** | `issuerType` `maturityClass` `couponType` `creditRating` `collateralType` `currency` `issuanceMarket` `issuerCategory` |
| `domestic_etfs` | **7** | `assetType` `region` `strategy` `replicationMethod` `leverageType` `underlyingScope` `distributionType` |
| `public_funds` | **6** | `fundType` `redemptionType` `issuanceType` `listingType` `classDifferentiation` `investorEligibility` |
| `overseas_etfs` | — | 없음 |

#### 이걸 어떻게 쓰나 — 정답이 붙은 검증셋입니다

`axis_*` 값은 **DB에 없으므로 기존 컬럼에서 유도해야 합니다.**
그런데 샘플 100건에 정답이 있으니, **유도 규칙을 세우고 그 자리에서 채점**할 수 있습니다.

```python
# 노트북에서: 샘플 시트 ↔ DB 를 itm_no(또는 pd_no/pd_itm_no)로 조인하고 교차표
m = sample.merge(db, on='<식별자>')
pd.crosstab(m['axis_fundType'], m['or_attr_desc'])
```

공모펀드 실측 결과 (샘플 96건 매칭):

| 축 | 유도 규칙 | 결과 |
| :--- | :--- | :--- |
| `axis_fundType` | `or_attr_desc` 매핑 | ✅ **96/96 완전 일치** |
| `axis_investorEligibility` | `prvo_pbff_desc` (공모/사모) | ✅ **96/96** |
| `axis_listingType` | `itm_nm LIKE '%상장지수%'` | ✅ **96/96** |
| `axis_classDifferentiation` | 종목명에 `종류`/`클래스` | ❌ **안 맞음** — 다른 규칙 필요 |
| `axis_issuanceType` | `fd_set_pcd` | ⚠️ 부분만 |

> **정답이 없었다면 뒤 두 개가 틀렸다는 것도 몰랐을 겁니다.**
> 그럴듯한 규칙을 세우고 넘어가지 말고, **반드시 샘플로 채점하세요.**

#### 담당자가 할 일

- [ ] 담당 테이블의 `Sheet2_Sample` 을 열어 `axis_*` 컬럼과 값 종류를 파악
- [ ] 각 축을 **DB의 어떤 컬럼에서 유도할 수 있는지** 규칙을 세우고 샘플로 채점
- [ ] 규칙과 **정확도(N/100)** 를 `_notes.md` 에 기록 — 안 맞는 축도 그대로 남기기
- [ ] 못 맞춘 축은 §5 워크샵에 가져오기

> ⚠️ **이 축을 그대로 쓸지는 워크샵에서 정합니다.** 주최 측 제시안이지 확정안이 아닙니다.
> 다만 평가자가 기대하는 모델이 드러난 것이므로, **다르게 갈 거라면 근거가 필요합니다.**
> 그리고 이건 상품군 **내부** 축입니다 — 상품군을 **관통하는** 축(운용사·지역 등)은
> 여전히 §5-A와 아래 질문 4·5로 따로 찾아야 합니다.

---

### 🔹 개체 (Entity)

1. 내 상품군에서 **"상품 하나"를 식별하는 것**은 무엇인가?
   > 자명해 보여도 확인하세요. 공모펀드는 `std_itm_no`가 PK가 아니었습니다 —
   > 같은 펀드가 속성코드별로 최대 16행입니다 (§8-⑦). 이런 게 논의에서 나와야 합니다.
2. 내 테이블에 **상품이 아닌 개체**가 섞여 있는가?
   > 국내ETF마스터에는 ETN이 30.7% 들어 있습니다. 같은 개체로 볼 것인가, 나눌 것인가?

### 🔹 관계 (Relation)

3. 내 상품군의 상품은 **무엇과 연결**되는가?
   > 후보: 운용사 · 발행사 · 기초지수 · 벤치마크 · 상장시장 · 기초자산 · 통화 · 구성종목 …
   > 우리 테이블에 실제로 그 연결이 **어떤 컬럼으로** 들어 있는지 함께 적어주세요.
4. 그 연결 대상 중 **다른 상품군에도 등장할 것**은 무엇인가?
   > ★ 워크샵의 핵심 재료입니다. 여기서 공통 축이 *발견*됩니다.
   > 예: 채권 발행사와 ETF 운용사가 같은 금융그룹일 수 있습니다.
5. 우리 테이블의 그 값이 **다른 테이블과 같은 표기를 쓰고 있을까?**
   > 아니라면 어떻게 다른지. (이미 확인된 불일치는 §5에 정리돼 있습니다 — 거기 없는 것을 찾아주세요.)

### 🔹 분류 (Classification)

6. 내 상품군을 **분류하는 방식이 몇 가지**이고, **무엇이 1차 분류**인가?
   > 자산군? 운용전략? 투자지역? 위험등급? 여러 축이 있다면 서로 직교하는지 겹치는지.
   > **주최 측 `axis_*`(위 🎯)를 출발점으로 삼되, 데이터에만 있는 축도 함께 적어주세요.**
   > 예: 공모펀드 `prfd_attr_cd` 안에 국가 태그(`CHN` 646종목 등)가 숨어 있는데
   > 이건 `axis_*` 에도 `fd_ivst_rgn_desc` 에도 없습니다.
7. 그 분류에 **계층**이 있는가?
   > 예: 일본 ⊂ 아시아 ⊂ 글로벌. 계층이 있으면 온톨로지에서 `rdfs:subClassOf`가 실제로 값어치를 합니다.

### 🔹 고유 개념 & 한계

8. 내 상품군에만 있고 **다른 상품군엔 없는 개념**은?
   > 채권: 만기·듀레이션·신용등급 / ETF: 괴리율·추적오차·합성 vs 실물 / 펀드: 클래스 체계·재간접
   > → 이건 온톨로지에서 공통 상위 클래스가 아니라 **하위 클래스 고유 속성**이 됩니다.
9. 사용자가 물을 법한데 **지금 데이터로 답할 수 없는 것**은?
   > 결측률이 높아서든, 컬럼이 아예 없어서든. 이게 그대로 `확인할 수 없음` 응답 정책이 됩니다.
10. 비전공자 팀원이 이 상품군 질의를 이해하려면 **최소한 알아야 할 도메인 지식**은?
    > 워크샵에서 다른 트랙 담당자에게 설명한다고 생각하고 적어주세요.

### 🔹 함정

11. §8에 없는 **새로운 데이터 함정**을 발견했다면 — 재현 SQL과 영향 건수를 함께.

> 💡 **질문 5·9·11의 답은 워크샵 전에 T0에 미리 공유해 주세요.** 안건을 짜는 데 씁니다.

---

## 4. 2단계 — 예상 질의 작성 (형식 고정)

**담당 상품군에 대해 예상 질의 20개를 작성합니다.**

> 🔴 **확정 사항: 주최 측은 예시 질의셋을 제공하지 않습니다.**
> 평가 30문항(상10·중10·하10)이 무엇을 물을지 우리는 **끝까지 알 수 없습니다.**
> 따라서 **4명 × 20문항 = 80문항 자체 평가셋이 이 프로젝트의 유일한 성능 측정 기준**이 됩니다.

**그리고 이 질의들이 온톨로지 설계의 입력입니다.**

*"무엇을 네트워크로 녹일까"* 의 답은 *"어떤 질의에 답해야 하는가"* 에서 나옵니다.
*"삼성전자를 5% 이상 담은 ETF를 운용하는 운용사의 채권형 펀드"* 라는 질의를 써 봐야
`상품 → 운용사 → 상품` 경로와 `상품 → 구성종목` 관계가 필요하다는 게 드러납니다.
**질의 없이 온톨로지를 그리면 쓰지도 않을 관계를 모델링하고 정작 필요한 건 빠집니다.**

그래서 이 작업은 §3 탐색과 **동시에** 진행하고, 워크샵 전에 끝내야 합니다.

**작성 시 지킬 것**

1. **실제 평가 구성을 모사합니다.** 난이도 배분: **하 7 / 중 7 / 상 6**.
2. **평가자의 말투로 씁니다.** ❌ `wu_inv_ast_type이 채권인 ETF` → ✅ `채권형 ETF`.
3. **`gold_sql`을 반드시 직접 실행하고 결과를 눈으로 확인**합니다. 실행 안 해본 정답은 정답이 아닙니다.
4. **2인 크로스체크 필수.** 작성자 외 1명이 `gold_sql`을 재실행해 승인합니다 (`note`에 이름).
   유일한 기준이 틀려 있으면 이후 모든 개선 판단이 함께 틀립니다.
5. 우리 시스템이 **맞히기 쉬운 질의만 쓰지 마세요.** 어렵게 낼수록 이득입니다.

> 💡 **손으로 JSON 을 쓰지 마세요.** `notebooks/eda_template.ipynb` 마지막 절에서
> `QUESTIONS` 리스트만 채우면 **전 문항 `gold_sql` 실행 검증 → `jsonl` 생성**이 자동으로 됩니다.
> 문법 오류·0건 반환·난이도 배분 미달이 그 자리에서 드러납니다 (§3의 노트북 안내 참조).

한 줄에 JSON 객체 하나:

```json
{"qid":"ETF-D-001","difficulty":"중","qtype":"연산·순위","expected_behavior":"answer","question":"국내 상장 ETF 중 최근 1년 수익률이 가장 높은 채권형 ETF 3개를 알려줘.","gold_sql":"SELECT TRIM(pd_nm), du_er_1y FROM domestic_etfs WHERE pd_grp_no='ETF' AND TRIM(wu_inv_ast_type)='채권' AND du_er_1y IS NOT NULL ORDER BY du_er_1y DESC LIMIT 3","must_include":["ETF명 3개","1년 수익률 수치"],"must_not_include":["수익률 전망","매수 추천"],"source_columns":["pd_grp_no","wu_inv_ast_type","du_er_1y"],"note":"pd_grp_no 필터 없으면 ETN이 섞임. du_er_1y 결측 20.6%"}
{"qid":"ETF-D-014","difficulty":"상","qtype":"결측·데이터미제공","expected_behavior":"unanswerable","question":"KODEX 200의 기초지수 구성종목 비중을 알려줘.","gold_sql":null,"must_include":["확인할 수 없음","구성종목 미수록"],"must_not_include":["삼성전자","SK하이닉스"],"source_columns":[],"note":"마스터에 Holdings 미수록. 절대 지어내면 안 되는 대표 문항."}
{"qid":"ETF-D-018","difficulty":"상","qtype":"네거티브(미존재)","expected_behavior":"unanswerable","question":"KODEX AI 로봇 ETF의 총보수가 얼마야?","gold_sql":null,"must_include":["확인할 수 없음","해당 종목 없음"],"must_not_include":["0.4%","총보수는"],"source_columns":[],"note":"2026-07-11 기준 미존재 상품. 멘토 경고 사항 직결."}
{"qid":"ETF-D-020","difficulty":"중","qtype":"역질문필요","expected_behavior":"clarify","question":"안전한 ETF 하나 추천해줘.","gold_sql":null,"must_include":["위험등급","투자 지역","확인이 필요"],"must_not_include":["추천드립니다","가장 안전한"],"source_columns":[],"note":"조건 부족 → 역질문 분기. 과제 명세의 '조건부 안내' 요구사항."}
```

**필드 정의**

| 필드 | 값 | 설명 |
| :--- | :--- | :--- |
| `qid` | `<도메인약칭>-<3자리>` | `BOND` / `ETF-D` / `ETF-O` / `FUND` |
| `difficulty` | `하` / `중` / `상` | **하 7 / 중 7 / 상 6** 으로 배분 |
| `qtype` | 아래 8종 | 유형 커버리지 확보용 |
| `expected_behavior` | `answer` / `unanswerable` / `clarify` | **가드레일 3분기와 1:1 대응** |
| `question` | 자연어 | 실제 평가자가 쓸 법한 말투로 |
| `gold_sql` | SQL 또는 `null` | 정답 도출 쿼리. `unanswerable`/`clarify`는 `null` |
| `must_include` | 문자열 배열 | 답변에 **반드시** 나와야 할 요소 |
| `must_not_include` | 문자열 배열 | 나오면 **감점**인 요소 (환각·단정적 추천) |
| `source_columns` | 배열 | 근거 컬럼 |
| `note` | 문자열 | 주의사항 (결측 모수 등) + **크로스체크 승인자 이름** |

**`qtype` 8종 — 20문항 배분**

| qtype | 권장 문항수 | 설명 |
| :--- | :---: | :--- |
| `조건검색` | 3 | 자산군·지역·위험등급·보수 조건 필터 |
| `정보조회` | 3 | 특정 종목의 세부 속성 |
| `비교` | 3 | 2~3개 상품 간 보수·수익률·규모 비교 |
| `연산·순위` | 3 | 정렬·Top-N·집계·평균 |
| `교차상품군` | 2 | 다른 상품군을 넘나드는 질의 ← **온톨로지 설계의 핵심 입력** |
| `네거티브(미존재)` | 3 | 없는 상품·없는 등급 → `unanswerable` |
| `결측·데이터미제공` | 2 | 존재하지만 값이 없음 → `unanswerable` |
| `역질문필요` | 1 | 조건 부족 → `clarify` |

> **네거티브 + 결측 + 역질문 6문항(30%)은 줄이지 마세요.**
> 환각은 "즉시 대형 감점"이라, 맞히는 것보다 **틀리지 않는 것**의 기댓값이 큽니다.

> 💡 **`교차상품군` 2문항은 지금은 답이 안 나올 겁니다.** 그게 정상입니다 —
> 그 질의가 워크샵에서 "이 관계를 온톨로지에 넣어야 한다"의 근거가 됩니다.

---

## 5. 3단계 — 온톨로지 설계 워크샵 (전원)

각자 가져온 것을 놓고 **개체·관계·계층을 합의**합니다.

### 산출물: `ontology.ttl` 초안

**그날 클래스와 관계를 실제로 파일에 적고 끝냅니다.** 완성이 아니라 초안이면 됩니다.
화이트보드에만 남기지 않습니다.

### 안건

1. **주최 측 `axis_*` 축(§3 🎯)을 채택할 것인가** — 채택 / 수정 / 자체 설계.
   각 트랙이 가져온 **유도 규칙과 정확도(N/100)** 를 보고 판단합니다.
   다르게 갈 거라면 그 근거가 곧 기술제안서의 "온톨로지 설계 의도"가 됩니다.
2. **최상위 클래스를 어떻게 나눌 것인가** — 상품군별? 자산군별? 둘 다?
3. **각 트랙의 개체 식별자** — §3 질문 1의 답을 맞춰봅니다
4. **교차 관계 확정** — §3 질문 4의 답을 모아 붙입니다.
   `axis_*` 는 상품군 **내부** 축이라, 상품군을 **관통하는** 축은 여기서 따로 정합니다
5. **불일치 해소 방침** — 아래 §5-A의 발견들을 어떻게 정규화할지
6. **계층 설계** — §3 질문 7의 답 (지역·자산군 등)
7. **제약(Constraint) 확정** — `DisjointWith` / 값 범위 / `inverseOf`
8. **`교차상품군` 질의 검토** — 각자 쓴 질의가 이 온톨로지로 답이 나오는지 역검증

---

### §5-A. 이미 발견된 교차 불일치 — 논의 재료

> 사전 조사에서 확인된 **불일치 목록**입니다. 위 안건 5번(불일치 해소 방침)의 재료로 씁니다.
> 정규화 방식은 워크샵에서 정합니다.
> **여기 없는 불일치를 찾아 가져오는 것**이 §3 질문 5의 목적입니다.

#### 운용사 표기 — 가장 심각

| 테이블 | 컬럼 | 현재 상태 |
| :--- | :--- | :--- |
| `domestic_etfs` | `cu_fund_mgmt_co` | 한글 97종. **약칭**(`삼성` 224, `미래에셋` 193, `KB` 147) + **정식명 혼재**(`메리츠증권 주식회사` 92) + **상품 전체명 오염 약 60건** + `'.'` 1건 |
| `overseas_etfs` | `cu_fund_mgmt_co` | 영문 372종 (`ARK Investment Management LLC`) + NULL |
| `public_funds` | `or_co_xtn_itt_cd` | ⚠️ **숫자 코드 67종만 (`40010.0`). 운용사 이름이 아예 없음** |
| `domestic_bonds` | `PD_PBCM` | 발행사 — 운용사와 같은 개체로 볼지가 **논의 대상** |

> 🔴 *"미래에셋자산운용이 운용하는 ETF와 펀드를 비교해줘"* 는 현재 상태로 답이 나오지 않습니다.
> 국내ETF에서 `cu_fund_mgmt_co = '미래에셋자산운용'` 은 **0건**입니다 (실제 저장값은 `'미래에셋'` 193건).
> 공모펀드는 이름 컬럼이 아예 없어 전체가 조회 불가입니다.
> 그런데 상품군 교차 질의는 과제 명세에 배점 항목으로 명시돼 있습니다.
> → **펀드 운용사 코드 67개 → 이름 매핑**을 누가 어떻게 만들지가 워크샵 결정 사항입니다.
> (금투협 공시 등 2026-07-11 이전 공개 자료로 매핑 가능. 외부 수집 시 §9 규칙 준수)

#### 자산군 표기 — 언어 불일치

| 테이블 | 컬럼 | 값 |
| :--- | :--- | :--- |
| `domestic_etfs` | `wu_inv_ast_type` | 채권 / 주식 / 원자재 / 혼합자산 / 통화 / 단기자금 / 부동산 / 기타 (8) |
| `overseas_etfs` | `wu_inv_ast_type` | Equity / Bond / Mixed Assets / Alternatives / Commodity / Money Market (6) |
| `public_funds` | `or_attr_desc` | 주식형 / 재간접 / 채권혼합 / 채권형 / **`06`(5,436건)** / 주식혼합 / MMF / 혼합자산 / 특별자산 / 임대형 / 대출형 (11) |
| `domestic_bonds` | `STD_PD_MCLS_NM` | 회사채 / 특수채 / 국공채 / 개인투자용국채 / 외화채권-회사채 / 외화채권-금융채 (6) |

> 값 집합의 **입도와 성격이 서로 다릅니다.** 펀드의 `재간접`·`임대형`은 자산군이라기보다 운용구조이고,
> 채권의 분류는 발행 주체 기준입니다. **하나의 축으로 합칠 수 있는지 자체가 논의 대상입니다.**
> `or_attr_desc = '06'` 5,436건은 디코딩 안 된 코드입니다 (상품명이 전부 파생형 계열 → T4가 원본 schema로 확정).

#### 투자지역 표기 — 언어 + 입도 불일치

| 테이블 | 컬럼 | 값 |
| :--- | :--- | :--- |
| `domestic_etfs` | `wu_inv_rgn` | 미국 / 국내 / 중국 / 글로벌 / 아시아 / 일본 / 베트남 / 남미·북미 / 인도 / 이머징·브릭스 / 유럽 (11) |
| `overseas_etfs` | `wu_inv_rgn` | `United States of America` / `Global Emerging Markets` / `Asia Pacific ex Japan` / `Greece` / `Qatar` … |
| `public_funds` | `fd_ivst_rgn_desc` | 국내 / 글로벌 / 아시아 / 남미·북미 / 이머징·브릭스 / 유럽 / 중동·아프리카 (7) + NULL |

> 국내ETF는 `일본`·`인도`·`베트남`을 분리하는데 펀드는 전부 `아시아`로 묶습니다.
> 해외ETF는 `Greece`·`Qatar`까지 내려갑니다. → **계층 설계가 필요한 대표 사례** (§3 질문 7).

#### 위험등급 — 동일 개념, 3가지 표현

| 테이블 | 컬럼 | 표현 |
| :--- | :--- | :--- |
| `domestic_bonds` | `PD_RISK_GCD` | INTEGER `0`~`6` (0등급 58건) |
| `domestic_etfs` | `pd_risk_cd` | 문자열 `PD_RISK_GCD_11` ~ `_16` (**뒤 2자리 − 10 = 등급**) |
| `public_funds` | `zrin_fd_ivst_risk_gcd` | REAL `1.0`~`6.0` + **NULL 18,416건 (19.3%)** |

라벨(`zrin_fd_ivst_risk_grd_nm`) 표기도 흔들립니다: `'높은 위험'` vs `'높은위험'`, `'보통 위험'` vs `'보통위험'`.

> ✅ **확정: 범위는 1~6 (+ 미분류 0/NULL).** 온톨로지 제약을 1~5로 쓰면 안 됩니다.

#### 통화 — 3가지 표현

| 테이블 | 컬럼 | 값 |
| :--- | :--- | :--- |
| `domestic_etfs` | `pd_curr_cd` | `CURR_CD_KRW` / `CURR_CD_000` (접두사 형식) |
| `public_funds` | `curr_cd` | `KRW` / `USD` |
| `domestic_bonds` | `CURR_CD` | `KRW` / `USD` / `JPY` / `EUR` / `000` |
| `overseas_etfs` | `pd_trd_ccy` | `USD` (단일) |

#### 기초지수·벤치마크 — 센티넬 결측 주의

| 테이블 | 컬럼 | 실태 |
| :--- | :--- | :--- |
| `domestic_etfs` | `cu_base_index` | distinct 20. **실제 값 보유 58건 / 1,734건 (3.3%)** — 나머지는 공백문자열 1,551 + NULL 125 |
| `overseas_etfs` | `cu_base_index` | distinct 1,733. 그러나 **`Index is not provided by Management Company` 1,984건 + `Index is not available on Lipper Database` 721건** → 실제 지수명 보유는 **2,933 / 5,646 (51.9%)** |
| `public_funds` | `bmrk_nm` | distinct 391, 결측 0%. **복합식 표기**: `MSCI ACWI CR 50% + 종합채권01Y 50%` → 파싱 필요 |

> 지수를 **독립 개체로 볼 것인가 문자열 속성으로 둘 것인가** 도 논의 대상입니다.
> 독립 개체로 두면 "같은 지수를 추종하는 국내/해외 ETF 비교" 같은 질의가 가능해집니다.

---

## 6. 4단계 — enums·제약 확정 (워크샵 이후)

워크샵에서 개체·관계·계층이 정해진 **뒤에** 각 트랙이 마무리합니다.
여기서 나오는 것이 런타임 가드레일이 직접 읽는 파일입니다.

`ontology/enums/<domain>.yaml` — `.auto.yaml` 위에 **판단이 들어가는 필드만** 채웁니다.

**이 파일은 문서가 아니라 에이전트가 실행 중에 로드하는 설정입니다.**

### 🔴 규칙: 데이터 설정은 노트북이 아니라 이 파일에 씁니다

노트북은 `.gitignore` 대상입니다. **판정이나 규칙을 노트북에만 적으면 런타임에도 팀원에게도 전달되지 않습니다.**

```
scripts/profile_table.py       판정 "기준" (무엇을 후보로 볼지) — 코드
        ↓ 후보 제시
ontology/enums/<domain>.yaml   판정 "결과" + 규칙        ★ 단일 진실 원천
        ↓ 로드
notebooks/*.ipynb              탐색 — 정의하지 않고 읽어서 씀
```

| ❌ 하지 말 것 | ✅ 할 것 |
| :--- | :--- |
| 노트북에 `RULES = {...}` 하드코딩 | yaml 에 `query_rules` 로 기록하고 노트북은 로드 |
| 노트북에서 결측 판정 기준 재정의 | `from profile_table import NOT_PROVIDED_PATTERNS, …` |
| 정제된 DataFrame 을 만들어 탐색 | 원본에 규칙을 매번 적용 (SQL 조각으로) |
| yaml 블록을 **통째로 대입** | **기존 값을 먼저 싣고 덧씌우기** (아래) |

> 🔴 **왕복(round-trip) 주의 — 실제로 규칙이 사라질 뻔했습니다.**
> yaml 에 다른 경로로 규칙을 추가해 두고 노트북을 다시 실행하면,
> 노트북이 자기가 가진 것으로 **통째로 덮어써서 추가분이 유실**됩니다.
>
> ```python
> # ❌ 유실
> QUERY_RULES = {"종목단위": "...", "공모만": "..."}
>
> # ✅ 병합
> QUERY_RULES = {
>     **DECL.get("query_rules", {}),   # 기존 것을 먼저
>     "종목단위": "...",
> }
> ```
>
> 템플릿의 내보내기 셀에는 **유실 검증 assert** 가 들어 있습니다.
> yaml 을 손으로 고쳤다면 노트북 재실행 전에 그 내용이 `QUERY_RULES` 에 반영됐는지 확인하세요.

> **정제본을 만들면 `gold_sql` 이 런타임과 어긋납니다.**
> 노트북에서 검증한 쿼리가 원본에서 다른 결과를 내면 평가셋 전체가 무의미해집니다.

### 이 파일이 담는 것 — 3블록

```yaml
domain: public_funds

normalization:                    # ① 정규화 규칙
  trim_columns: [itm_nm, prfd_attr_cd, ...]

query_rules:                      # ② 질의 필수 조건 — gold_sql 에도 그대로
  종목단위: "GROUP BY itm_no"
  공모만:  "prvo_pbff_desc = '공모'"
  ETF제외: "itm_nm NOT LIKE '%상장지수%'"

columns:                          # ③ 컬럼별 판정
  exchdg_yn:
    missing_reason: not_applicable
    note: 국내 87.7% 결측 vs 해외 0.8% — 국내 투자엔 환헤지 개념이 없음
    answer_policy: 국내 펀드의 환헤지 문의 → '해당사항 없음'
```

각 필드가 쓰이는 곳:

| 필드 | 내용 | 런타임 소비처 |
| :--- | :--- | :--- |
| `missing_reason` | 컬럼 전체의 결측 성격 (`missing` / `not_applicable`) | 응답 분기 |
| `missing_semantics` | **특정 값**이 결측인지 정보인지 | 결측 계산 · 프로파일러가 읽음 |
| `normalization.trim_columns` | `TRIM` 이 필요한 컬럼 | SQL 생성 |
| `query_rules` | 필수 필터·`GROUP BY` | SQL 생성 · **`gold_sql`** |
| `trap` | 이 컬럼의 함정 (패딩·센티넬·오염값) | SQL 생성 — `TRIM()` 적용, ETN 필터 등 |
| `answer_policy` | 모수 기반 답변 정책<br>예: *"총보수는 1,734건 중 67건만 유효값. 모수 명시 필수"* | 답변 조립 — 모수 문구 삽입 |
| `canonical_*` | 워크샵에서 정한 개체·관계에 이 컬럼이 어떻게 매핑되는지 | 질의어 그라운딩 — "미래에셋자산운용" → 축 값 |
| `unit` | 원본 schema에서 확인한 단위 (% 인지 소수인지, 누적인지 연환산인지) | 숫자 포맷·환산 |
| 오염값 제외 | `'.'` 같은 값을 허용값에서 빼는 판단<br>**삭제하지 말고 `trap`에 기록** | 존재 검증 화이트리스트 |

> **`.auto.yaml`의 기계적 사실(결측률·distinct·분포)은 여기에 복사하지 않습니다.**
> 그건 스크립트가 매번 다시 뽑습니다. 여기에 박아두면 DB가 갱신될 때 조용히 낡습니다.
> 이 파일에는 **사람의 판단만** 넣으세요.

---

## 7. 완료 정의(DoD) & 머지 규칙

### 2단계 완료 조건

- [ ] `docs/eda/<domain>_notes.md` 에 §3의 11개 질문에 대한 답이 있다
- [ ] **결측 판정**을 `ontology/enums/<domain>.yaml` 에 선언했다 (§3 🕳️)
      — `judgment_needed` 가 비워질 때까지. 판정마다 **근거 수치**를 `note` 에 남길 것
- [ ] **정규화 규칙·질의 규칙**을 같은 파일의 `normalization` / `query_rules` 에 기록했다 (§6)
      — 노트북에만 두지 말 것. `gold_sql` 이 이 규칙을 따라야 합니다
- [ ] **`axis_*` 축별 유도 규칙과 정확도(N/100)** 를 기록했다 (§3 🎯) — 못 맞춘 축 포함
- [ ] §3 질문 5·9·11의 답을 T0에 공유했다 (워크샵 안건용)
- [ ] `eval/questions_<domain>.jsonl` 20문항 작성 완료
- [ ] 질의 20개 각각에 대해 `gold_sql`을 **직접 실행해 결과를 눈으로 확인**했다
- [ ] 질의 20개가 **하 7 / 중 7 / 상 6** 으로 배분되어 있다
- [ ] `expected_behavior`가 `unanswerable`/`clarify`인 문항이 **6개 이상**이다
- [ ] 질의 20개에 대해 **2인 크로스체크 승인**이 끝났다 (`note`에 승인자 이름)

### 4단계 완료 조건

- [ ] `ontology/enums/<domain>.yaml` 에 워크샵 결정이 반영되어 있다
- [ ] `trap` / `answer_policy` 가 필요한 컬럼에 기록되어 있다
- [ ] 오염값 제외 판단이 근거와 함께 남아 있다

### 머지 규칙

- 브랜치: `eda/<domain>` → PR → 리드 리뷰 후 `main`
- `.gitignore`에 의해 아래는 커밋되지 않습니다. **강제로 올리려 하지 마세요.**
  - 원본 데이터: `*.xlsx` / `*.db` / `*.csv` / `1.금융상품/`
  - 재생성 가능한 산출물: `ontology/enums/*.auto.yaml` / `*.values.txt`
  - 개인 노트북: `notebooks/*.ipynb` (`eda_template.ipynb` 만 예외)
- 산출물은 모두 텍스트이므로 정상 커밋됩니다.

---

## 8. ⚠️ 이미 확인된 함정 (전원 필독 — 중복 조사 금지)

리드가 사전 조사에서 확인한 항목입니다. **재조사하지 말고, 여기 없는 것을 찾으세요.**
(이 목록이 전부가 아닙니다 — 4개 테이블 207컬럼 중 일부만 본 결과입니다.)

### ① 고정폭 패딩 — 정확일치 검색이 조용히 실패합니다 🔴 최우선

```sql
SELECT COUNT(*) FROM domestic_bonds WHERE BD_KND = '일반회사채';        -- ▶ 188건
SELECT COUNT(*) FROM domestic_bonds WHERE TRIM(BD_KND) = '일반회사채';  -- ▶ 13,998건
```

**74배 차이입니다.** 게다가 패딩이 **혼재**되어 있어 (42,394건 중 40,942건만 패딩) 더 위험합니다.

패딩이 확인된 컬럼:

| 테이블 | 컬럼 | 패딩 건수 |
| :--- | :--- | ---: |
| `domestic_bonds` | `PD_ENG_NM` | 41,737 |
| `domestic_bonds` | `PD_ABRV_NM` | 41,732 |
| `domestic_bonds` | `PD_ABRV_ENG_NM` | 41,712 |
| `domestic_bonds` | `BD_KND` | 40,942 |
| `domestic_bonds` | `PD_PBCM` | 40,243 |
| `domestic_bonds` | **`PD_NM` (종목명)** | **1,396** |
| `domestic_etfs` | `pd_exg_mkt_nm` | 1,733 |
| `domestic_etfs` | `pd_mkt_nm` | 1,732 |
| `domestic_etfs` | `cu_base_index` | 1,551 |
| `domestic_etfs` | `pd_dvid_cycl` | 1,551 |

> 🔴 **`PD_NM`(종목명)에도 패딩 1,396건**입니다. 종목명 정확일치 조회가 실패하면 시스템은
> "그런 상품 없음"이라고 **잘못된 `확인할 수 없음`** 을 반환합니다. 환각만큼이나 위험한 오답입니다.
>
> → 모든 문자열 비교는 `TRIM()`을 거칩니다. 정규화 규칙(대소문자·전각·공백)은 워크샵 안건입니다.

### ② 위장 결측 — `IS NULL`로는 안 잡힙니다

결측은 3가지 형태로 존재합니다:

| 형태 | 실례 | 판정 |
| :--- | :--- | :--- |
| 진짜 `NULL` | `domestic_etfs.cu_base_index` 125건 | 결측 |
| **공백 문자열** | `domestic_etfs.cu_base_index` 1,551건 (`'                '`) | 결측 |
| **문장형 센티넬** | `overseas_etfs.cu_base_index` 의 `Index is not provided by Management Company` 1,984건 | ⚠️ **판정 필요** |
| **`해당없음`** | `public_funds.prvo_fd_desc` 95,451건 | ⚠️ **판정 필요 — 대개 정보** |

`IS NULL`만 세면 해외ETF 기초지수 결측이 **0.1%** 로 보이지만 실제 값은 **51.9%** 뿐입니다.
반대로 `해당없음`을 결측으로 세면 `prvo_fd_desc` 가 **99.9% 결측**으로 부풀려집니다 —
실제로는 `prvo_pbff_desc='공모'` 와 1:1 대응하는 **정상 값**입니다.

> 🔑 **뒤 두 형태는 기계가 판정하지 않습니다.** `judgment_needed` 로 표시만 하고,
> 사람이 §3 🕳️ 절차에 따라 `missing_semantics` 에 선언합니다.
> **새 센티넬 문자열을 발견하면 노트에 기록**하세요.

### ③ 주요 컬럼 결측률 (조사 완료 — 재조사 불필요)

| 테이블 | 컬럼 | 결측률 | 답변 가능 모수 |
| :--- | :--- | ---: | ---: |
| `domestic_bonds` | `BUY_YIELD` (매수수익률) | **97.9%** | 881 / 42,394 |
| `domestic_bonds` | `AFTER_TAX_YIELD` (세후수익률) | **97.9%** | 881 / 42,394 |
| `domestic_bonds` | `PD_EVCO_CRD_GRD` (신용등급) | 41.1% | 24,966 |
| `domestic_bonds` | `DUR` (듀레이션) | 31.6% | 29,018 |
| `domestic_etfs` | `cu_base_index` (기초지수) | **96.7%** | 58 / 1,734 |
| `domestic_etfs` | `cu_charge_rt` (총보수) | **87.5%** | 217 / 1,734 → ⚠️ **그중 150건이 `0`. 실질 67건** |
| `domestic_etfs` | `du_er_1y` (1년수익률) | 20.6% | 1,377 |
| `domestic_etfs` | `du_last_aum` (AUM) | 16.2% | 1,453 |
| `domestic_etfs` | `pd_sect_nm` (섹터) | **100%** | 0 |
| `overseas_etfs` | `cu_charge_rt` (총보수) | **0.0%** | 5,646 |
| `overseas_etfs` | `cu_base_index` (센티넬 포함) | 48.1% | 2,933 |
| `public_funds` | `fd_yr1_ern_r` (1년수익률) | 32.6% | 64,426 |
| `public_funds` | `zrin_fd_ivst_risk_gcd` (위험등급) | 19.3% | 77,203 |
| `public_funds` | 보수 정보 | **컬럼 자체 없음** | — |

> 💡 **국내ETF 총보수 87.5% 결측 vs 해외ETF 0% 결측.**
> "보수가 낮은 ETF 알려줘" 라는 같은 질문이 국내/해외에서 신뢰도가 완전히 다릅니다.
> 이 비대칭이 답변 정책에 반영되어야 합니다.
>
> 🔴 **게다가 국내ETF 총보수는 결측률보다 더 나쁩니다.** non-null 217건 중 **150건이 `0`** 이라,
> 실제 보수값을 가진 건 **67건 (3.9%)** 입니다. `0`이 진짜 무보수인지 미입력인지는
> T2가 원본 schema로 확인해야 합니다. *"총보수가 가장 낮은 ETF"* 를 물으면
> **0%짜리 150개가 공동 1위로 나옵니다.** — 프로파일러 `zero_heavy` 탐지기가 잡아낸 항목입니다.

### ④ 신용등급 표기 함정 (`domestic_bonds`)

두 컬럼이 **서로 다른 체계**입니다.

**`CRD_GRD`** (정규화된 단일 등급):
```
AAA, AA+, AA0, AA-, A+, A0, A-, BBB+, BBB0, BBB-, BB+, BB0, BB-, B+, B0, B-, CCC, CC0, C0, C
```
> 🔴 **`AA0`, `A0`, `BBB0` 처럼 `0`이 붙습니다.** 사용자는 "AA등급 채권"이라고 묻지 `AA0`이라고 묻지 않습니다.
> 매핑 없이 `WHERE CRD_GRD = 'AA'` 하면 0건 → **잘못된 `확인할 수 없음`**.

**`PD_EVCO_CRD_GRD`** (복수 평가사 등급, 콤마 결합 문자열):
```
'A+, AA-, AA-'   'AA+, AA+, AAA'   'A-, CCC, CCC'   'A, BBB+'
```
> 파싱 없이는 등급 필터링 불가. **신용등급을 독립 개체로 볼지, 평가사별 평가를 어떻게 다룰지**는
> T1이 검토해 워크샵에 가져오세요.

**네거티브 테스트:** `AAAA` 는 실제로 존재하지 않습니다 → 위 목록이 그대로 화이트리스트가 됩니다.

### ⑤ ETN 혼입 🔴 — "ETF마스터"에 ETF가 아닌 것이 들어 있습니다

**국내ETF마스터 — 30.7%가 ETN입니다.**

```sql
SELECT pd_grp_no, COUNT(*) FROM domestic_etfs GROUP BY 1;
-- ▶ 'ETF': 1,202 / 'ETN': 532
```

**해외ETF마스터 — 59건이 ETN입니다.**

```sql
SELECT cu_etn_yn, COUNT(*) FROM overseas_etfs GROUP BY 1;
-- ▶ NULL: 5,587 / 'Y': 59
```
또한 `cu_inverse_short_yn = 'Y'` 인 인버스/숏 상품이 171건.

**실제로 오답이 나오는 것을 확인했습니다.**

*"1년 수익률이 가장 높은 채권형 ETF 3개"* 를 자산군 필터만으로 조회하면
Top 3가 **전부 메리츠 인버스 국채 ETN**으로 나옵니다.

```sql
-- ❌ 흔히 쓰는 방식 (ETN이 섞여 나옴)
SELECT pd_nm, du_er_1y FROM domestic_etfs
WHERE wu_inv_ast_type LIKE '%채권%' ORDER BY du_er_1y DESC LIMIT 3;
--   → 261건 중 79건(30%)이 ETN

-- ✅ 수정
SELECT pd_nm, du_er_1y FROM domestic_etfs
WHERE pd_grp_no = 'ETF' AND TRIM(wu_inv_ast_type) = '채권'
  AND du_er_1y IS NOT NULL ORDER BY du_er_1y DESC LIMIT 3;
```

> 온톨로지의 `ETF owl:disjointWith ETN` 제약이 장식이 아니라 **실제 필터**로 작동해야 하는 지점입니다.
> **ETF와 ETN을 별도 클래스로 둘지, 공통 상위 클래스 아래 둘지**가 워크샵 안건입니다 (§3 질문 2).
>
> 반대로 *"ETN도 알려줘"* 라는 질의에는 답할 수 있어야 하므로, ETN을 **삭제하지 말고 구분만** 하세요.

### ⑥ 개별 오염 레코드 (확인된 것)

| 테이블 | 내용 | 건수 |
| :--- | :--- | ---: |
| `public_funds` | `zrin_fd_ivst_risk_gcd = 20054.0`, 라벨 `'06'` — 위험등급 칸에 기관 코드가 들어감 (컬럼 밀림) | 1 |
| `public_funds` | `thco_sale_yn` 에 `Y`/`N` 아닌 종목코드 문자열(`KRZ50226929C`) | 1 |
| `domestic_etfs` | `cu_fund_mgmt_co` 에 상품 전체명이 들어감 (`미래에셋TIGER200IT증권상장지수투자신탁(주식)` 등) | 약 60 |
| `domestic_etfs` | `cu_fund_mgmt_co = '.'` | 1 |

> 건수는 적지만, 이런 값이 `DISTINCT`로 뽑혀 **온톨로지 화이트리스트에 그대로 들어가면**
> "`'.'` 라는 운용사가 존재한다"고 시스템이 믿게 됩니다.
> 4단계에서 걸러내되 **삭제하지 말고 기록**하세요 (평가 질의가 이 종목을 물을 수도 있습니다).

### ⑦ 공모펀드 행 중복 🔴 — "95,619건"은 펀드 개수가 아닙니다

```sql
SELECT COUNT(*), COUNT(DISTINCT std_itm_no) FROM public_funds;
-- ▶ 95,619 행 / 11,127 개  (평균 8.6배, 최대 16행)
```

`std_itm_no`는 **PK가 아닙니다.** 같은 펀드가 **속성코드(`prfd_attr_cd`)별로 여러 행**으로 분리되어 있고,
이름·수익률·AUM 등 나머지 컬럼 값은 전부 동일합니다. 실질 복합키는 **`(std_itm_no, prfd_attr_cd)`** 입니다.

**실제로 오답이 나오는 것을 확인했습니다.**

```sql
-- ❌ 상위 5개가 전부 같은 펀드 1개로 채워짐
SELECT itm_nm, fd_yr1_ern_r FROM public_funds
WHERE zrin_fd_ivst_risk_gcd = 1 ORDER BY fd_yr1_ern_r DESC LIMIT 5;

-- ✅ GROUP BY 필수
SELECT TRIM(itm_nm), MAX(fd_yr1_ern_r) AS er FROM public_funds
WHERE zrin_fd_ivst_risk_gcd = 1 AND fd_yr1_ern_r IS NOT NULL
GROUP BY std_itm_no ORDER BY er DESC LIMIT 5;
```

> 영향 범위가 넓습니다 — **Top-N 질의는 중복 출력**, **집계 질의("펀드가 몇 개야?")는 8.6배 과대 답변**이 나갑니다.
> **T4는 `prfd_attr_cd` 228종이 무엇인지 원본 schema로 확인해 워크샵에 가져오세요.**
> 같은 펀드를 왜 나누는지가 정해져야 "펀드 하나"의 정의(§3 질문 1)가 정해집니다.
>
> 참고: 나머지 3개 테이블은 PK 중복이 없습니다 (`domestic_bonds.PD_NO`, `domestic_etfs.pd_itm_no`,
> `overseas_etfs.pd_itm_no` 전부 행 수 = distinct 수).

### ⑧ 수익률 이상치 — Top-N 질의에서 1위로 올라옵니다

| 컬럼 | 최대값 | 비고 |
| :--- | ---: | :--- |
| `domestic_etfs.du_er_1y` | **2,738.95%** | 미래에셋 TIGER 200IT레버리지 |
| `public_funds.fd_yr1_ern_r` | **975.1%** | 200% 초과가 3,537행 |
| `public_funds.fd_yr1_ern_r` | **−92.6%** (최소) | |

레버리지 상품이라도 비현실적인 값이라 **단위 정의 오류 또는 데이터 오류 가능성**이 있습니다.
"수익률 가장 높은 상품" 질의에서 그대로 1위로 나가면 답변 신뢰도가 무너집니다.

> **담당자 액션:** 원본 `*_schema.xlsx`의 단위 정의(% 인지 소수인지, 누적인지 연환산인지)와 대조하고,
> 이상치 처리 방침(그대로 노출 / 상한 필터 / 단서 부기)을 노트에 적어 오세요.
> 임의로 삭제하지는 마세요 — 평가 질의가 이 종목을 물을 수도 있습니다.

### ⑨ Boolean 표현이 4가지입니다

| 컬럼 | 표현 |
| :--- | :--- |
| `public_funds.sale_yn` | `'판매중'` / `'판매완료'` (한글) |
| `public_funds.thco_sale_yn` | `'Y'` (+ 오염 1건) |
| `domestic_etfs.pd_tr_yn` | `0.0` / `1.0` (REAL) |
| `overseas_etfs.pd_sale_yn` | `1.0` (REAL, 단일값) |

> **판매/거래 여부는 "모수 필터"입니다.** *"지금 살 수 있는 상품 중에서"* 라는 질의에 직결됩니다.

---

## 9. 외부 데이터 수집 규칙 (해당 담당자만)

ETF 구성종목(Holdings) 등 마스터에 없는 정보를 외부에서 보완할 때:

1. **2026-07-11 이전 스냅샷만** 사용합니다. 이후 데이터 사용 시 감점입니다.
2. **주최 측 제공 데이터가 항상 우선합니다.** 외부 수집값과 상충하면 마스터 데이터를 채택하고, 상충 사실을 기록합니다.
3. 수집한 데이터는 **출처 URL + 조회 시점 + 데이터 기준일**을 함께 저장합니다 (`data/external/` + `SOURCES.md`).
4. 마스터 데이터와 **같은 테이블에 섞지 않습니다.** 별도 테이블로 두고, 답변 시 출처를 구분해 표기합니다.

---

## 10. 질문 & 에스컬레이션

- 작업 방식에 대한 질문 → 개발 리드
- 컬럼 의미가 불명확 → `1.금융상품/*_schema.xlsx` 원본 확인 → 그래도 불명확하면
  **노트에 "의미 불명"으로 기록하고 넘어가기** (막히지 마세요. 워크샵에서 같이 봅니다)
- 분량이 감당이 안 될 것 같으면 → 리드에게 알리세요. 범위를 조정합니다. (혼자 끌지 마세요)
- **온톨로지를 어떻게 그려야 할지 모르겠으면** → 그게 정상입니다. §3의 질문에만 답해 오세요.
  모양은 워크샵에서 같이 만듭니다.

---

## 부록: 참고 문서

| 문서 | 내용 |
| :--- | :--- |
| `PROJECT.md` | 과제 개요·배점·API 명세 |
| `.agents/rules/miraeasset-rules.md` | 핵심 개발 규칙 (확정 규칙 — 이 문서보다 우선) |
| `docs/sqlite_db_architecture.md` | DB 구축 구조·인덱스 설계·컬럼별 함정 |
| `docs/domain/<domain>.md` | **상품군별 도메인 가이드** — 배경지식 + 데이터 구조 (작성된 것부터) |
| `docs/agent_architecture_notes.md` | Agent 그래프 구조 참고 노트 — 산출물이 런타임에서 어떻게 쓰이는지 |
| `scripts/build_db.py` | 엑셀 → SQLite 변환 스크립트 |
| `scripts/profile_table.py` | 컬럼 프로파일 자동 생성 (1단계) |
| `notebooks/eda_template.ipynb` | 탐색 노트북 템플릿 (2단계) — 복사해서 사용 |
| `requirements-dev.txt` | 노트북용 의존성 (제출 Dockerfile 에는 넣지 않음) |
