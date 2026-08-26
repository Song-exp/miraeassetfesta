# 🔁 검토지시서 재검증 결과 — 2차 데이터(2026-08-22) 기준 · 2026-08-25

> 대상: `review_request_2026-08-20.md` 상단 상태표의 🔄 **재검증** 10항목 (B1·B2·B3·B5·B8·E2·E4·E5·E7·F2).
> 방법: `data/financial_products.db`(2차, 읽기 전용) 직접 조회. 1차 수치는 원 지시서 기재값. yaml 은 수정하지 않았고 "정정 필요" 로만 표시.
> 총평: **채권 5건 중 4건은 전용 컬럼이 생겨 이름 정규식 자체가 폐기 대상**(B1·B3·B5·B8), 영구채(B2)만 이름 판정이 남는다.

| # | 항목 | 판정 | 한 줄 |
| :-: | :-- | :-: | :-- |
| B1 | 사모 판정 | **정정** | `bd_ofr_tcd='사모'` 2,007 (1차 이름 15,261). 이름 정규식은 recall 98.7%·precision 100% 였으나 컬럼으로 대체 |
| B2 | 영구채 450 | **정정·종결** | 450 재현 불가 종결. `신종\|영구` 237 채택 권고 (차집합 41건 전부 조건부자본증권=영구). dur=0 역전 문제 소멸 |
| B3 | FRN 정규식 | **정정** | `bd_inrt_tcd` 변동 830 + 고정+변동 148. 이름 '변' 431 = recall 44% → 정규식 폐기, 컬럼 사용 |
| B5 | 듀레이션 0 | **종결** | dur=0 & 잔존>0 이 **4건**(1차 500). 판정 대상 데이터 소멸. 규칙은 `dur > 0` 단순 필터로 |
| B8 | 유동화 범위 | **정정** | 코드 기준 2,924 + 코드 밖 112(신보/기보 SPC 95·Conduit 16) → 확장 규칙 3,036 |
| E2 | 수익률 센티넬 | **유지** | 1d 1·1m 16·3m 45·6m 66·ytd 69·1y 110. 1y=-100 전건 종가 0 동반. 매개변수형 규칙 ✅ |
| E4 | 정정 3건 | **유지(건수 갱신)** | 섹터 4=금현물 1·9=단일종목 2 ✅ · VOO/SPY/IVV=AMX ✅ · 상장일 0 은 8→**11**건 |
| E5 | 해외 한글명 13종 | **유지 11·정정 2** | `du_opr` 시가 등 11종 값 부합. `pd_lst_price`(전부 0)·`du_base_dt_match_yn`(전부 N)은 "정보 없음" 표기 필요 |
| E7 | 축 유도 실험 | **재현 불가·판정 강화** | 주최 정답은 1차 샘플(100건)에만 존재, 91건 조인. 2차 `ref_ast_type` 도 주최 정답과 69% 만 일치 → "규칙 유도 불가" 판정 유지. 인버스 10/10 이 양수 배수 = 부호 소실 확증 |
| F2 | 당사판매여부 | **정정(수치)** | `=''` 0 ✅ · NULL 13,079 (행=종목). 판매중 NULL 2,412 = **사모 1,993 + 공모 419** → 1차 "판매중 11종목" 서술 무효 |

---

## B1. 사모 채권 판정 — 전용 컬럼 `bd_ofr_tcd` 로 대체

**원 질문**: 이름 '사모' 15,261건(36%)이 맞나, 추천 모수에서 제외할 것인가.

```sql
SELECT bd_ofr_tcd, COUNT(*) FROM domestic_bonds GROUP BY 1;                       -- 공모 19,875 · 사모 2,007
SELECT bd_ofr_tcd, pd_nm LIKE '%사모%', COUNT(*) FROM domestic_bonds GROUP BY 1,2; -- 사모∧이름 1,981 · 사모∧이름없음 26 · 공모∧이름 0
SELECT COUNT(*) FROM domestic_bonds WHERE bd_ofr_tcd='사모' AND buy_yield IS NOT NULL;   -- 0
```
- 이름 정규식 성능(2차 기준): precision 1,981/1,981 = **100%**, recall 1,981/2,007 = **98.7%**. 누락 26건은 `하나모터제일차2-1`, `LG전자 89-2` 류 — 이름에 표기 없음.
- 사모 2,007건은 **전부 장외·퇴직연금 편입 N·판매행(buy_yield) 0건** → 추천 모수(판매행 634)에서 제외 비용 **0**. 1차 "36% 제외" 우려는 2차 행 구성(장외 17,645→4,136) 변화로 소멸.
- **판정**: `is_private` 이름 플래그 → `bd_ofr_tcd = '사모'` 로 교체. `사모제외` 규칙은 "개인 추천 질의 시 사모 제외" 로 별도 두되, 현 데이터에서는 판매행과 겹치지 않음을 note.
- **yaml 영향(정정 필요)**: `domestic_bonds.yaml` `name_encoding.is_private`(컬럼 대체 표기는 됐는지 확인), `query_rules.특수구조제외` 의 "별도 결정 필요" 문구 → "사모는 발행방식 축(`bd_ofr_tcd`), 구조옵션과 분리" 로 확정.

## B2. 영구채 판정 건수 — 450 종결, `신종|영구` 237 채택

**원 질문**: 등재 450 이 어떤 패턴으로도 재현 안 됨. 어느 집합이 영구채인가.

```python
A = 신종|영구          → 237   (1차 473)
B = 신종자본|[(/]신종[)/] → 196   (1차 467)
C = 신종자본           → 126   (1차 296)
A - B (41건) = 'DGB금융지주 조건부자본증권(상)5(신종-영구-5콜)(조건상각/콜/후)' 류 — 전부 은행지주 조건부자본증권
```
- 차집합 A−B 41건은 **`(신종-영구-5콜)` 표기의 조건부자본증권(AT1)** = 영구채가 맞다 → **A 패턴 채택**(B·C 는 과소).
- 영구 후보 266행(중복 종목 포함)의 `mat_dt` 분포: 2054(45)·2055(40)·2056(25)… — 스키마 코멘트 *"상환일자(영구채는 1차 콜행사개시일)"* 과 정합(발행+5년 콜).
- **dur=0 은 2건뿐** (1차 500) → "영구채 듀레이션 0 → 금리위험 역전" 방어 규칙의 전제가 사라짐(§B5).
- **판정**: count 450 은 재현 불가로 **종결**. `is_perpetual` pattern `신종|영구`, count **237** 로 정정. 원 산출자 확인 불필요.
- **yaml 영향(정정 필요)**: `name_encoding.is_perpetual` pattern·count, `query_rules.듀레이션정상` 의 영구채 예외 서술 축소.

## B3. 변동금리채 정규식 — 폐기, `bd_inrt_tcd` 사용

**원 질문**: pattern 필드가 산문. 표기 4종 정규식으로 643 재현 + '천변' 제외.

```sql
SELECT bd_inrt_tcd, COUNT(*) FROM domestic_bonds GROUP BY 1;   -- 고정 20,904 · 변동 830 · 고정+변동 148
```
| 이름 표기 | 2차 건수 | 그중 bd_inrt_tcd 변동/혼합 |
| :-- | --: | :-- |
| `(변)` | 268 | 249 변동 + 19 혼합 |
| `변동` | 43 | 43 변동 |
| `/변` | 50 | 32 변동 + 18 혼합 |
| `FRN` | 0 | — |
| `변` 전체 | 431 | 393 변동 + 37 혼합 + **1 고정(대전천변고속도로5)** |

- 이름 정규식 `변(?!.*천변)` 의 성능: precision 430/431 = **99.8%**, **recall 430/978 = 44%**. 누락 548건은 `뉴스텔라제십팔차2-1(사모)`, `케이비캐피탈564-5`, `롯데카드 540-3` 류 — 사모·카드/캐피탈 ABS 의 변동금리가 이름에 없음.
- **판정**: 정규식 확정 대신 **폐기** — `bd_inrt_tcd IN ('변동금리','고정+변동금리')` 가 유일한 판정 기준. `천변` 오탐 문제도 자동 해소.
- 1차 "FRN 643 = SRFC_IRT 는 스냅샷 금리" 해석(§D.8)은 유효 — 대상 집합만 830+148 로 교체. `srfc_irt` 정렬 시 FRN 분리 규칙 유지.
- **yaml 영향(정정 필요)**: `name_encoding.is_frn` pattern → 컬럼 대체 명시(에이전트 재작성분에 "전용 컬럼으로 대체 표기" 가 들어갔는지 확인), `query_rules.이자유형분리` 근거 수치.

## B5. 듀레이션 0 = 영구채 산출불능 — 데이터 소멸, 종결

```sql
SELECT COUNT(*) FROM domestic_bonds WHERE dur=0 AND remaining_days>0;   -- 4  (1차 500)
SELECT COUNT(*) FROM domestic_bonds WHERE dur=0;                        -- 52 (48건은 잔존일수 ≤ 0)
SELECT COUNT(*) FROM domestic_bonds WHERE dur IS NULL;                  -- 16
```
- 4건 중 영구류 패턴 2건(50%), 나머지 2건은 `디비닉스제사십육차1-2(사모/콜)`·`엔투텍17CB(사모/전환/풋)` — 이표채 사모.
- **판정**: "영구채 산출불능" 판정을 검증할 모집단이 사라짐 → **종결**. 규칙은 `dur > 0 AND dur IS NOT NULL` 단순 배제(0값 52 + NULL 16 = 68건)로 충분. 비율 병기 불필요.
- **yaml 영향**: `columns.dur.answer_policy` 의 "500건 영구채" 서술 삭제(정정 필요), `normalization.zero_as_missing` 에 dur 유지.

## B8. 유동화 채권 식별 범위 — 확장 규칙으로 정정

```sql
SELECT TRIM(bd_knd), COUNT(*) FROM domestic_bonds WHERE bd_knd LIKE '%유동화%' OR bd_knd LIKE '%MBS%' GROUP BY 1;
-- MBS 1,396 · 유동화회사채 1,528 · 유동화수익증권 1        → 현행 규칙 base = 2,924 (1차 4,957)
-- 규칙 밖 + 이름/발행사에 '유동화': 112 = bd_knd 공백 95 · Conduit회사채 16 · 유동화수익증권 1
```
- 규칙 밖 112건 표본: `신보2025제15차유동화전문1-2(사)`(bd_knd 공백) · `카드오토제육차유동화전문1-18(콜)`(Conduit회사채, 발행사 '카드오토제육차유동화전문') — **전부 SPC 발행**(신보·기보 P-CBO 유동화전문회사, 카드 ABS 컨듀잇).
- **판정**: 규칙 확장 — `TRIM(bd_knd) IN ('MBS','유동화회사채','유동화수익증권','Conduit회사채') OR pd_nm LIKE '%유동화%' OR pd_pbcm LIKE '%유동화%'` → **3,036건**. 1차 4,957 과의 차이는 만기 경과분 정리.
- **yaml 영향(정정 필요)**: `query_rules.유동화위험금지` 조건식·건수. `collateral_type_map.csv`(외부 코드북)의 bd_knd 32종 재대조는 별도.

## E2. 수익률 센티넬(-100) 매개변수형 규칙 — 유지

```sql
-- 2차: du_er_1d 1 · 1m 16 · 3m 45 · 6m 66 · ytd 69 · 1y 110   (ETF만: 1·2·11·16·16·35)   (1차 20·37·53·44·98)
SELECT COUNT(*) FROM domestic_etfs WHERE du_er_1y=-100 AND du_clpr<>0;   -- 0  (전건 종가 0 동반 = 거래중단/상폐)
SELECT COUNT(*) FROM domestic_etfs WHERE du_clpr=0;                        -- 192
```
- 센티넬이 전 기간에 존재함이 2차에서도 재현. 1일수익률에도 1건 등장(1차엔 없었음).
- 규칙 문안(`<질의 대상 기간 컬럼> > -100 AND … IS NOT NULL`)은 에이전트 재작성분에 반영 확인 ✅. **형식 의견**: 플래너 프롬프트 주입 시 `{period_col}` 플레이스홀더로 표기하고 `planner_context()` 가 그대로 싣는다 — SQL 생성기가 정렬 컬럼과 같은 컬럼을 치환하도록 프롬프트 지시문에 명시할 것.
- **yaml 영향**: 없음(수치만 2차로 갱신돼 있는지 확인).

## E4. 정정·신설 3건 — 유지, 건수 갱신

| 항목 | 2차 실측 | 판정 |
| :-- | :-- | :-- |
| ① 섹터코드 4·9 | 4 = `미래에셋 KRX금현물 Auto-KO-C 2810-01 ETN` 1건 · 9 = `레버리지 삼성전자/SK하이닉스 단일종목 ETN` 2건 | ✅ 동일 |
| ② AMX = NYSE Arca | VOO·SPY·IVV 전부 AMX | ✅ |
| ③ 해외 상장일 0 | `pd_lstg_dt = 0` **11건** (TAWN·BBLS·JPNU·HWO·ONX …) | 건수 8→11 (재작성분 반영 확인) |
- 참고: 2차 `pd_sect_cd` 분포 — ETF 2:1,160·8:16·NULL 59 / ETN 3:419·4:1·9:2·NULL 123. `pd_sect_nm` 은 삭제됐으므로 코드 해석은 `etf_sector.csv` 만이 근거.

## E5. 해외 컬럼 한글명 13종 — 11 부합, 2 정정

| 컬럼 | 명명 | 2차 값 검증 | 판정 |
| :-- | :-- | :-- | :-: |
| `du_opr` | 시가 | `lpr ≤ opr ≤ hpr` 6,022/6,023 | ✅ |
| `du_bpr` | 기준가 | bpr/clpr 평균 0.994 (0.68~2.05) — 전일 종가 성격 | ✅ (note: "전일 기준가" 추정) |
| `du_val_1d` · `du_vol_1d` | 일거래대금·일거래량 | val/vol/clpr = 1.000 | ✅ |
| `cu_index_repl_mthd` | 지수복제방법 | Optimized 1,826 · Swap 297 · Full 278 · Other 6 | ✅ |
| `cu_index_tracking_yn` | 지수추종여부 | 유효값 전부 Y (2,407) | ✅ 이름은 맞으나 판별 정보 없음 |
| `pd_trd_ccy` | 거래통화 | 전부 USD | ✅ |
| `du_clpr_src` | 종가출처 | 전부 `pd65n101.tday_clpr` (내부 테이블명) | ✅ — 답변 노출 금지 |
| `pd_lipper_id` · `pd_us_cik` | Lipper식별자 · SEC CIK | 8자리·7자리 숫자, CIK 는 운용사 단위 | ✅ |
| `cu_etn_yn` | ETN여부 | Y 65 = `pd_grp_no='ETN'` 65 와 1:1 | ✅ |
| `cu_inverse_short_yn` | 인버스/숏여부 | Y 183 (부호 정상 `cu_lev_fector<0` 128 과 병행) | ✅ |
| `wu_core_yn` | 핵심ETF여부 | 유효값 N 106 뿐 | ✅ 이름 맞음·정보 없음(사용 금지 유지) |
| `du_base_dt_match_yn` | 기준일일치여부 | **전부 N** (6,023) | 🔧 "값이 전부 N — 판별 정보 없음" 명시 필요 |
| `pd_lst_price` | 상품액면가 | **전부 0** (6,022) + 1건 | 🔧 "미수록(0)" 명시, 답변 사용 금지 |
- **yaml 영향(정정 필요)**: `overseas_etfs.yaml` `column_korean_names` 의 두 항목에 정보없음 주석, `constant_columns` 에 `du_base_dt_match_yn`·`pd_lst_price` 포함 여부 확인.

## E7. 축 유도 실험(assetType·underlyingScope) — 재현 불가, 판정 강화

**전제 변화**: 주최 axis 정답은 **1차 스키마 엑셀 `Sheet2_Sample`(100건)에만** 있고 2차 스키마 파일엔 샘플 시트가 없다. 1차 샘플 100건 중 2차 DB 에 남은 종목 **91건**으로만 대조 가능(87→83% 실험의 정확 재현은 불가).

```
[assetType] 주최 정답 vs 2차 ref_ast_type (91건)      일치 63/91 = 69%
   Bond→Bond 10, Commodity 4, Equity 37, MixedAsset 8, MoneyMarket 4
   불일치: Currency 5 → Alternatives 4 · RealEstate 4 → Equity 4 · Equity 14 → Alternatives 10/Bond 4 · Bond 6 → 기타
[assetType] 주최 정답 vs wu_inv_ast_type               일치 71/91 = 78%
```
- 주최 정답 "국고채=Equity"(유형 A)는 2차 `ref_ast_type` 에서도 **Bond** 로 나온다 → 주최 정답 쪽이 데이터와 어긋난다는 판정이 **더 강해짐**. 단순 매핑으로는 92% 도 재현 안 됨(1차 실험은 규칙 보정 포함). **"규칙 유도 불가·주최 회신 대기" 판정 유지**.
- `[underlyingScope]` SingleStock 5건 중 `pd_sect_cd=8` 은 **1건**(레버리지 단일종목), 4건은 코드 2(삼성전자채권혼합·테슬라밸류체인) → 코드 8 을 SingleStock 으로 쓰면 recall 20%. 반대로 코드 8 은 SectorTheme 에도 3건 → **"섹터코드 8 사용 금지" 판정 유지**.
- `[leverageType]` 주최 Inverse1X 5건 → `cu_lev_fector` **1.0**, Inverse2X 5건 → **2.0**. 인버스 10/10 이 양수 = **부호 소실 확증**(이름 판정 규칙 필요성 재확인).
- `[distributionType]` 주최 Distributing 99/100 인데 `pd_dvid_cycl` NULL 22 · TR 1건만 — 이 축은 정보량이 거의 없음(참고).
- **yaml 영향**: `axis_derivation.pending_workshop` 각 항목에 "2차 재현: 샘플 91건, ref_ast_type 일치 69%, 판정 유지" 한 줄(정정 필요). 1차 정확도 수치(100/100 등)는 2차 미재현으로 표기.

## F2. 당사판매여부 빈칸 = NULL — 정정(수치·해석)

```sql
SELECT COUNT(*) FROM public_funds WHERE thco_sale_yn='';                          -- 0  ✅
SELECT COUNT(*), COUNT(DISTINCT itm_no) FROM public_funds WHERE thco_sale_yn IS NULL;  -- 13,079 · 13,079 (행=종목)
SELECT sale_yn, thco_sale_yn, COUNT(*) FROM public_funds GROUP BY 1,2;
-- 판매완료: NULL 10,667 · Y 2,047 / 판매중: NULL 2,412 · Y 8,550
SELECT thco_sale_yn, COUNT(*) FROM public_funds WHERE sale_yn='판매중' AND prvo_pbff_desc='공모' GROUP BY 1;  -- NULL 419 · Y 8,550
```
- `=''` 함정은 2차에서도 동일(0행) → `IS NULL` 규칙 유지 ✅.
- 빈칸의 뜻 재정의: 판매중 NULL 2,412 = **사모 1,993(전부 NULL) + 공모 419**. 1차 "판매중 11종목 = 채널 미취급" 은 2차 **공모 419종목** 으로 확대. 사모는 당사 리테일 취급 대상이 아니므로 NULL 이 정상.
- **판정**: value_semantics 유지, 수치·해석 정정. answer_policy: 판매중·공모 NULL 419건 = "당사 채널 미취급(데이터 정상)", 사모 NULL = "리테일 취급 대상 아님", 판매완료 NULL = 레거시.
- **yaml 영향(정정 필요)**: `public_funds.yaml` `columns.thco_sale_yn` 수치(4,024·694·11 → 13,079·2,412·419)와 사모 분기 추가.

---

## 후속 (yaml 정정 필요 항목 모음 — 담당자 반영용)

| yaml | 항목 | 내용 |
| :-- | :-- | :-- |
| domestic_bonds | is_private / 특수구조제외 | `bd_ofr_tcd='사모'` 2,007 로 대체, 사모=발행방식 축 분리 확정 |
| domestic_bonds | is_perpetual | pattern `신종\|영구`, count 237 (450 종결) |
| domestic_bonds | is_frn / 이자유형분리 | 정규식 폐기 → `bd_inrt_tcd`, 이름 recall 44% 근거 |
| domestic_bonds | dur.answer_policy | "500건 영구채" 삭제, `dur>0` 단순 배제 |
| domestic_bonds | 유동화위험금지 | 조건식 확장 → 3,036건 |
| overseas_etfs | column_korean_names / constant_columns | `du_base_dt_match_yn` 전부 N · `pd_lst_price` 전부 0 명시 |
| domestic_etfs | axis_derivation.pending_workshop | 2차 재현 결과 한 줄(샘플 91·ref_ast_type 69%·부호 소실 확증) |
| public_funds | thco_sale_yn | 13,079 / 판매중 NULL = 사모 1,993 + 공모 419 |
