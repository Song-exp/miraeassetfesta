# -*- coding: utf-8 -*-
"""규칙 12종의 서술과 검토 체크리스트 — 사람이 쓰는 부분.

`gen_ontology_rules_doc.py` 가 이걸 읽어 문서를 만든다.
목록·수치는 yaml·DB 에서 매번 새로 뽑으므로 여기엔 **판단과 서술만** 둔다.

각 항목:
  n/slug/name/sub  식별·제목
  gist             한 줄 요약
  defect           데이터가 이랬다 (결함)
  rule             그래서 이렇게 정했다 (규칙)
  ev               근거 질의 [(설명, SQL), ...]
  risk             안 지키면 무슨 답이 나가나
  check            검토 체크리스트 — 사람이 판정할 것
"""

RULES = [
    {
        "n": "1", "slug": "naming", "name": "지칭 정리", "sub": "같은 것을 같다고 부르기",
        "gist": "한 개체가 소스마다 다른 문자열로 나타난다. 문자열을 맞추지 말고 **개체(노드)를 만들어 잇는다.**",
        "defect": [
            "발행사 이름이 `(주)` 위치·공백 때문에 갈라진다 — 같은 회사가 둘로 세어진다.",
            "신용등급이 `AA` 와 `AA0` 두 표기로 들어온다. 사용자는 'AA' 라고 묻는다.",
            "같은 종목이 국내는 티커, 해외는 영문명·CUSIP·LEI, 펀드는 ISIN 으로 온다. "
            "이름으로 매칭하면 **삼성전자 질의에 삼성전기가 섞인다.**",
        ],
        "rule": [
            "`normalization.trim_columns` — 비교 전 항상 TRIM (4개 도메인 전부).",
            "`normalization.grade_suffix` — `AA` → `AA0` 접미사 정규화 후 비교.",
            "`kg_alias`(노드 ↔ 테이블·컬럼·원시값) 로 **표기가 아니라 개체를 조인**한다. 코드북이 사람이 확정한 정본.",
        ],
        "ev": [
            ("발행사 표기 흔들림 — TRIM 하나로 19개가 합쳐진다",
             "select count(distinct pd_pbcm) as raw_distinct, count(distinct trim(pd_pbcm)) as trimmed "
             "from domestic_bonds"),
            ("신용등급 — `AA` 가 아니라 `AA0` 으로 수록된다",
             "select crd_grd as 등급, count(*) as n from domestic_bonds where crd_grd like 'AA%' "
             "group by 1 order by 2 desc"),
            ("🔴 이름 LIKE 가 왜 위험한가 — 삼성전자와 삼성전기가 접두사를 공유한다",
             "select holding_name as 표기, count(*) as n from ext_ovs_etf_holdings "
             "where holding_name like 'SAMSUNG ELECTRO%' group by 1 order by 2 desc limit 8"),
        ],
        "risk": "‘삼성전자를 보유한 ETF’ 질의에 **삼성전기 보유분이 섞인다.** 발행사 집계는 같은 회사를 둘로 센다.",
        "check": [
            "`kg_alias` 가 붙지 않은 이름 컬럼이 남아 있는가 — 특히 해외ETF·펀드의 종목명 계열.",
            "코드북의 `status: pending` alias 는 KG 에 들어가지 않는다. **몇 건이고 왜 pending 인지** 확인.",
            "종목 정본(`security_alias_manual.csv`) 18종으로 충분한가 — 교차질의에 자주 나올 종목이 빠지지 않았는지.",
            "`grade_suffix` 외에 접미사 정규화가 필요한 범주형이 더 있는가(운용사 약칭·지수명 등).",
            "TRIM 만으로 안 합쳐지는 표기(중간 공백·괄호 위치)가 발행사 1,818종 안에 남아 있는지 표본 검사.",
        ],
    },
    {
        "n": "2", "slug": "missing", "name": "결측 방어", "sub": "비어 있음의 뜻을 가른다",
        "gist": "주최: 0·결측은 **의도된 값**. 채우지 말고 **왜 비었는지를 선언**한다. 답변 문장이 여기서 갈린다.",
        "defect": [
            "채권 판매 조건이 97.1% 비어 있다. '값을 모른다' 가 아니라 **'당사 판매 목록에 없다'** 는 사실이다 "
            "— 주어가 시장이 아니라 미래에셋이다.",
            "값이 있는데 의미가 없는 칸이 있다(위장결측). 날짜 `0`, 듀레이션 `99`, 대표코드 더미.",
            "부재를 특정 값으로 표시한 칸이 있다(센티넬). 수익률 `-100`, 기초지수 문자열 — **`IS NULL` 로는 안 잡힌다.**",
        ],
        "rule": [
            "`missing_reason` 분류: `not_applicable` / `missing` / `present`·`none` / `mixed`.",
            "분류마다 **답변 문장이 고정**된다 — `not_applicable` 은 “해당 사항이 없습니다”, ❌ “모릅니다” 로 답하면 오답.",
            "위장결측은 `dummy_as_missing`·`invalid_values`, 센티넬은 `query_rules.수익률정상`·`기초지수유효` 로 배제.",
        ],
        "ev": [
            ("`not_applicable` 의 대표 사례 — 채권 판매 조건 결측은 '진열대에 없다' 는 뜻",
             "select count(*) as 전체, sum(case when buy_yield is null then 1 else 0 end) as 결측, "
             "round(sum(case when buy_yield is null then 1 else 0 end)*100.0/count(*),1) as pct from domestic_bonds"),
            ("위장결측 — 값은 있는데 의미가 없다",
             "select sum(case when dur=99 then 1 else 0 end) as 듀레이션99, "
             "sum(case when isu_dt=0 then 1 else 0 end) as 발행일0, "
             "sum(case when mat_dt=0 then 1 else 0 end) as 만기일0 from domestic_bonds"),
            ("센티넬 ① 수익률 -100 — `IS NULL` 로 안 잡힌다",
             "select count(*) as du_er_1y가_정확히_마이너스100 from domestic_etfs where du_er_1y = -100"),
            ("센티넬 ② 해외 기초지수 — 문자열로 부재를 표시 (NULL 은 11건뿐)",
             "select case when cu_base_index like '%not provided%' then 'not provided by Management Company' "
             "when cu_base_index like '%not available%' then 'not available on Lipper Database' end as 센티넬, "
             "count(*) as n from overseas_etfs where cu_base_index like '%not provided%' "
             "or cu_base_index like '%not available%' group by 1"),
        ],
        "risk": "결측을 '모른다' 로 답하면 오답이고, 센티넬을 못 거르면 "
                "**수익률 최하위 Top-N 이 전부 상장폐지 종목**으로 채워진다.",
        "check": [
            "🔴 분류 밖 값(`unresolved`·`None`)이 있는 컬럼 — **답변 규칙이 없는 상태**다. "
            "4분류 중 하나로 확정하거나 분류를 늘릴지 결정.",
            "`mixed` 컬럼에 `missing_semantics` 가 실제로 붙어 있는가. 없으면 분해 불가라 답변이 애매해진다.",
            "`present`·`none` 판정인데 실측 결측이 있는 컬럼 — `data_dictionary/` 의 ⚠️ 목록과 대조 (총 18건).",
            "위장결측 조건식이 2차에서도 유효한가 — 더미 패턴이 `000000000000` 외에 `00`·`00000` 등 길이 변형으로도 있다.",
            "센티넬이 더 있는가 — 전부 0 인 컬럼, 특정 상수로 채워진 컬럼을 `auto.yaml` 재생성 후 재확인.",
        ],
    },
    {
        "n": "3", "slug": "external", "name": "외부 데이터 병합", "sub": "마스터를 고치지 않고 옆에 붙인다",
        "gist": "마스터(L0) > 판정(L1) > 외부(L2). 외부는 **마스터가 비었을 때만**, 출처·기준일을 달고 별도 테이블에.",
        "defect": [
            "마스터에 아예 없는 사실이 있다 — ETF 구성종목, 펀드 설정일·보수 분해.",
            "외부 자료는 **기준일이 마스터와 다르다.** 국내 8/21, 해외는 상품마다 3/31~6/30.",
            "커버리지가 100% 가 아니다 — 종목 수로만 말하면 대표성을 과소평가한다"
            "(해외는 종목수 22.7% 지만 AUM 가중 88.6%).",
        ],
        "rule": [
            "외부는 `ext_*` **별도 테이블**. 마스터 값을 덮어쓰지 않는다.",
            "`validate_sql` 이 `ext_*` **단독 조회를 금지** — 반드시 마스터와 조인.",
            "답변에 `as_of`/`report_date` **병기 강제**. 해외 커버리지는 **AUM 가중**으로 말한다.",
            "시계열 값은 **일부러 적재하지 않았다** — 관측 시점이 기준일과 달라 근거로 못 쓴다.",
        ],
        "ev": [
            ("국내 ETF 구성종목 커버리지 — ETN 은 구조상 없다(‘해당 없음’)",
             "select (select count(distinct etf_code) from ext_etf_holdings) as 수집ETF, "
             "(select count(*) from domestic_etfs where pd_grp_no='ETF') as 전체ETF, "
             "(select count(*) from domestic_etfs where pd_grp_no='ETN') as ETN_구조상없음"),
            ("해외 Holdings 보고기준일 분포 — ETF 간 비중 비교 시 시점이 어긋난다",
             "select report_date as 보고기준일, count(distinct etf_ticker) as ETF수 "
             "from ext_ovs_etf_holdings group by 1 order by 2 desc limit 6"),
            ("외부가 채워 준 것 — 마스터에 없는 펀드 설정일",
             "select count(*) as 설정일_보강, min(estb_dt) as 최초, max(estb_dt) as 최근 "
             "from ext_fund_page where estb_dt is not null and trim(estb_dt)<>''"),
        ],
        "risk": "외부 값을 마스터에 덮어쓰면 주최 규칙 위반이고, 기준일을 안 밝히면 "
                "**8/22 기준 답변에 3/31 자료가 섞인다.**",
        "check": [
            "🆕 주최 8/26 답변 — **결측 보완은 정성평가 가점**이다. 지금 구조(마스터 불변 + `ext_*` 보강)로 "
            "“결측률을 얼마나 줄였는지” 를 수치로 낼 수 있는가.",
            "국내ETF 총보수 유효 67/1,235(5.4%) — 외부 보완 대상 1순위. 출처·매칭 키·검증 방법을 정할 것.",
            "`ext_fund_holdings` 의 `grp` 조인이 선행 0 때문에 몇 건 실패하는가.",
            "해외 `isin` 매핑 90.9% — 나머지 9.1% 는 마스터와 조인되지 않는다. 보완 가능한가.",
            "적재 제외한 시계열 값을 정말 안 써도 되는가 — 8/22 기준으로 재수집할 여지 확인.",
        ],
    },
    {
        "n": "4", "slug": "grain", "name": "행 단위(grain)", "sub": "`COUNT(*)` 는 종목 수가 아니다",
        "gist": "테이블의 한 행이 무엇 하나인지를 도메인마다 선언한다. 이걸 안 하면 **모든 집계가 틀린다.**",
        "defect": [
            "채권은 한 종목이 시장·기준일·`info_seq` 조합으로 **2~4행**이 된다.",
            "펀드 `mtco_itm_no` 는 운용사 내부 번호라 **여러 운용사에 걸쳐 중복**되고, 선행 0 손실로 길이가 1~7 로 섞인다.",
        ],
        "rule": [
            "`row_grain` 을 4개 도메인 전부에 선언 (100% 적용된 몇 안 되는 규칙).",
            "채권 `대표행` — 종목 단위 질의는 `GROUP BY pd_no` 또는 `pd_exg_mkt='장내'` 우선.",
            "펀드 `펀드단위` — 운용사코드 + 7자리 zero-pad 한 `mtco_itm_no` **합성키**.",
        ],
        "ev": [
            ("채권 — 행 수와 종목 수가 다르다",
             "select count(*) as 행, count(distinct pd_no) as 종목, count(*)-count(distinct pd_no) as 차이 "
             "from domestic_bonds"),
            ("종목당 행 수 분포 — 1,078 종목이 2행 이상",
             "select n as 행수, count(*) as 종목수 from (select pd_no, count(*) n from domestic_bonds group by 1) "
             "group by 1 order by 1"),
            ("펀드 — 클래스와 펀드묶음은 다른 단위",
             "select count(*) as 행_클래스, count(distinct itm_no) as 클래스, "
             "count(distinct mtco_itm_no) as 묶음키_원값 from public_funds"),
        ],
        "risk": "‘AA- 이상 채권 몇 개’ 에 **1,078 종목이 중복 계산**된다. "
                "펀드는 클래스와 펀드를 혼동해 개수가 몇 배로 부푼다.",
        "check": [
            "채권 `대표행` 을 `GROUP BY pd_no` 로 할지 `장내 우선` 으로 할지 — 두 방식의 결과가 다른 종목이 몇 개인가.",
            "펀드 합성키가 실제로 유일한가 — 운용사코드+zero-pad 후 중복이 남는지.",
            "`ext_fund_holdings` 는 묶음 단위인데 마스터는 클래스 단위다. 조인 후 **행이 부풀지 않는지** 확인.",
            "국내/해외ETF 는 1행=1종목이 맞는가 — 위 실측표의 중복 열을 확인.",
            "gold SQL 63문항 중 `COUNT(*)` 를 종목 수로 쓴 문항이 있는지 재검토.",
        ],
    },
    {
        "n": "5", "slug": "population", "name": "기본 모수", "sub": "말하지 않은 조건을 고정한다",
        "gist": "‘펀드’ 라고만 물으면 무엇을 세는가. 암묵 조건을 **규칙으로 박아** 질의마다 흔들리지 않게 한다.",
        "defect": [
            "2차에 **사모 8,960행이 유입**됐다. 사모는 일반 질의 대상이 아니다.",
            "판매완료 펀드는 평가 컬럼이 99% 결측이라 Top-N 표본을 망친다.",
            "국내ETF 테이블에 **ETN 545건**이 섞여 있다 — 구성종목·기초지수가 구조적으로 없다.",
        ],
        "rule": [
            "펀드 `기본모수` = `sale_yn='판매중' AND prvo_pbff_desc='공모'`.",
            "ETF `ETF만` = `pd_grp_no='ETF'`.",
            "`집계_TopN_필수` — 집계·Top-N 은 기본모수로 한정하고 **답변에 모수를 병기**.",
        ],
        "ev": [
            ("펀드 4분면 — 기본모수는 하나뿐",
             "select prvo_pbff_desc as 공모사모, sale_yn as 판매상태, count(*) as n "
             "from public_funds group by 1,2 order by 3 desc"),
            ("국내ETF 테이블의 ETN 혼입",
             "select pd_grp_no as 구분, count(*) as n from domestic_etfs group by 1 order by 2 desc"),
        ],
        "risk": "모수를 안 걸면 ‘수익률 좋은 펀드 Top10’ 이 **사모·판매완료로 채워진다.** ETN 이 ETF 답변에 섞인다.",
        "check": [
            "채권의 ‘기본 모수’ 는 무엇인가 — 펀드·ETF 와 달리 명시적 기본모수 규칙이 없다. 만기 미경과만으로 충분한가.",
            "해외ETF 는 `구매가능: 1=1`(전건) 이다. 상장폐지분이 정말 없는지 재확인.",
            "‘판매중’ 정의가 도메인마다 다르다(펀드 `sale_yn`, ETF `pd_sale_yn`, 채권 `mat_dt`). "
            "교차질의에서 일관되게 적용되는가.",
            "모수 병기 문구가 답변 템플릿에 강제돼 있는가(안건 §1-7).",
            "사모 1,993건이 ‘판매중’ 이다 — 사용자가 명시적으로 사모를 물으면 답할 것인가.",
        ],
    },
    {
        "n": "6", "slug": "derivation", "name": "파생·유도", "sub": "없는 축을 규칙으로 만든다",
        "gist": "사용자가 묻는 축(인버스·재간접·모자형·총보수)이 컬럼으로 없다. **다른 컬럼에서 유도**한다.",
        "defect": [
            "2차에서 `cu_lev_fector` 의 **인버스 음수 부호가 사라졌다.** 이름에 ‘인버스’ 가 있는 225건 중 음수는 22건뿐.",
            "‘총보수’ 컬럼이 없다. 운용·판매·수탁·사무관리 4개를 합쳐야 한다.",
            "재간접·모자형 여부가 플래그로 없다. 구성비·태그·종목명에서 판정해야 한다.",
        ],
        "rule": [
            "`inverse_direction` — **방향은 상품명 키워드**, 배수는 `ABS(cu_lev_fector)`. 답변에 “상품명 기준” 근거 병기.",
            "`totalFeeApprox` = (운용+판매+수탁+사무관리)/10 — 기타비용 미포함이라 TER 보다 작다는 것까지 규칙에 명시.",
            "`isFundOfFunds` · `isMasterFeeder` · `prfdAttrTag`(한 컬럼에 섞인 2종 코드를 **형태로 분리**).",
        ],
        "ev": [
            ("🔴 인버스 부호 소실 — 이름과 부호가 어긋난다",
             "select sum(case when pd_abrv_nm like '%인버스%' then 1 else 0 end) as 이름에_인버스, "
             "sum(case when cu_lev_fector<0 then 1 else 0 end) as 부호가_음수, "
             "sum(case when pd_abrv_nm like '%인버스%' and cu_lev_fector<0 then 1 else 0 end) as 둘_다 "
             "from domestic_etfs"),
            ("총보수는 합성 축 — 성분 4개가 따로 있다 (단위 ‰)",
             "select round(avg(or_co_rwrd_r),3) as 운용, round(avg(sale_co_rwrd_r),3) as 판매, "
             "round(avg(trusc_rwrd_r),3) as 수탁, round(avg(ofwk_trus_rwrd_r),3) as 사무관리 "
             "from public_funds where sale_yn='판매중' and prvo_pbff_desc='공모'"),
        ],
        "risk": "부호를 믿으면 **‘인버스 ETF’ 질의가 203건을 놓친다.** 총보수를 성분 하나로 답하면 값이 1/4 로 나온다.",
        "check": [
            "`inverse_direction` 이 이름 규칙이라 **오탐·누락**이 있다. ‘인버스’ 없는 인버스 상품, "
            "‘인버스’ 있는 비인버스 상품을 표본 확인.",
            "`totalFeeApprox` 에 `ofwk_trus_rwrd_r=0`(4,866건) 이 들어간다 — "
            "합산 성분이라 0 을 빼면 안 된다는 판정이 규칙에 명시돼 있는가.",
            "해외ETF 에는 파생 규칙이 하나도 없다. 인버스·레버리지 판정을 `cu_inverse_short_yn` 로만 하는데 신뢰 가능한가.",
            "채권에 `derivation_rules` 가 없다 — 유동화·영구채·FRN 판정이 `query_rules` 에 흩어져 있다. 옮길지 검토.",
            "파생 결과를 답변에 **‘추정’ 으로 표시**하는 규칙이 있는가(edge 와 같은 취급이 필요).",
        ],
    },
    {
        "n": "7", "slug": "disjoint", "name": "배타·분리", "sub": "한 축에 놓으면 안 되는 것들",
        "gist": "겉보기에 같은 컬럼인데 **서로 다른 종류**가 섞여 있다. 정렬·집계 전에 갈라야 한다.",
        "defect": [
            "`srfc_irt` 한 컬럼에 **세 의미** — 고정 이표(발행 시 약속·불변), 변동금리(기준일 스냅샷), 할인채(발행 할인율).",
            "ETF 와 ETN 은 같은 테이블인데 구성종목·기초지수 구조가 다르다.",
            "같은 종목이 장내·장외 양쪽에 있어 시장별 group-by 는 구성 효과에 교란된다.",
        ],
        "rule": [
            "ETF `DisjointWith` ETN — 온톨로지 수준의 배타 선언.",
            "`이자유형분리` — 표면금리 정렬은 `bd_intp_tcd`·`bd_inrt_tcd` 로 유형을 나눈 뒤에만.",
            "`시장집계금지` — `pd_exg_mkt` 단독 group-by 금지.",
        ],
        "ev": [
            ("표면금리 한 컬럼, 네 가지 이자 유형 — 섞어 정렬하면 의미가 없다",
             "select trim(bd_intp_tcd) as 이자유형, count(*) as n, round(min(srfc_irt),2) as 최소, "
             "round(max(srfc_irt),2) as 최대, round(avg(srfc_irt),2) as 평균 "
             "from domestic_bonds group by 1 order by 2 desc"),
            ("ETF/ETN 구조 차이 — 기초지수 수록 여부",
             "select pd_grp_no as 상품군, count(*) as n, "
             "sum(case when ref_base_index is null or trim(ref_base_index)='' then 1 else 0 end) as 기초지수없음 "
             "from domestic_etfs group by 1"),
        ],
        "risk": "‘표면금리 높은 채권’ 에 **할인율과 이표금리가 뒤섞여** 비교 불가능한 순위가 나온다.",
        "check": [
            "ETF/ETN DisjointWith 가 `.ttl` 에 실제로 있는가 — 제출 규격에서 OWL 어휘를 본다.",
            "이자유형 분리를 답변이 실제로 하는가 — 플래너 프롬프트에 이 규칙이 전달되는지 확인.",
            "펀드에도 배타 축이 필요한가(주식형/채권형/재간접이 배타인가 중첩인가).",
            "해외ETF `pd_grp_no` 에 ETN 이 섞여 있는지 실측 — 국내와 같은 문제가 있는가.",
            "‘한 축에 놓으면 안 되는’ 다른 컬럼이 더 있는가 — 수익률(누적 vs 연환산), 순자산(KRW vs USD).",
        ],
    },
    {
        "n": "8", "slug": "unit", "name": "단위·스케일", "sub": "같은 이름, 다른 눈금",
        "gist": "컬럼 이름은 ‘보수’ 인데 마스터는 **‰**, 설명서는 **%** 다. 단위를 선언하지 않으면 자릿수가 틀린다.",
        "defect": [
            "펀드 보수 컬럼의 단위가 스키마에 없다. 값만 보면 % 인지 ‰ 인지 알 수 없다.",
            "국내ETF 분배금 절대액 스케일이 의심스럽다 — 분배수익률과의 산식이 **588/588 정확히 성립**하는데, "
            "그러려면 절대액이 NAV 대비 100배여야 한다.",
            "해외ETF 는 USD, 국내는 KRW — 순자산 통합 정렬이 불가능하다.",
        ],
        "rule": [
            "`columns.<컬럼>.unit` 으로 단위를 **명시 선언**. 펀드 보수는 `‰`(값÷10 = %).",
            "분배금 **절대액은 답변 금지**, 분배수익률(%)·지급월만. 스케일 미확정.",
            "`통합정렬환율` — USD→KRW 환산 후 정렬 (`fx_rate.csv` 8/21 = 1,384.23).",
        ],
        "ev": [
            ("🔴 **‰ 의 결정적 증거** — 마스터 보수 합계와 설명서 총보수를 대조하면 정확히 10배",
             "select round(avg(p.or_co_rwrd_r+p.sale_co_rwrd_r+p.trusc_rwrd_r+p.ofwk_trus_rwrd_r),3) as 마스터_보수합계, "
             "round(avg(e.total_fee_pct),3) as 설명서_총보수_pct, "
             "round(avg(p.or_co_rwrd_r+p.sale_co_rwrd_r+p.trusc_rwrd_r+p.ofwk_trus_rwrd_r)/avg(e.total_fee_pct),2) as 배수, "
             "count(*) as 대조행 from public_funds p join ext_fund_page e on e.itm_no=p.itm_no "
             "where e.total_fee_pct>0"),
            ("분배금 스케일 의심 — 산식이 588/588 전건 성립한다",
             "select count(*) as 산식_성립 from domestic_etfs "
             "where pd_divd_amt_ann>0 and abs(pd_dvid_yield - pd_divd_amt_ann/pd_dvid_nav) < 0.001"),
        ],
        "risk": "‘보수 0.5% 이하 펀드’ 가 **10배 어긋난 모수**를 반환한다. 분배금 절대액을 답하면 100배 틀린 금액이 나간다.",
        "check": [
            "🔴 `unit` 표기가 통일돼 있지 않다(‰ 두 가지 표기, `yyyymmdd(REAL 저장)` 은 단위가 아니라 형식). "
            "**enum 으로 고정**할지 결정.",
            "`unit` 이 없는 수치 컬럼이 얼마나 되는가 — 단위 미상 컬럼은 비교·정렬 답변에 쓰면 안 된다.",
            "`percent` 와 `percent_cumulative` 의 차이가 답변에 반영되는가 — ‘3년 수익률 10.5%’ ≠ 연 10.5%.",
            "환율이 8/21 단일 시점이다. 해외 순자산 정렬 답변에 환율 기준일을 병기하는가.",
            "분배금 절대액 ‘답변 금지’ 를 플래너가 실제로 지키는가 — 컬럼이 SELECT 에 나오지 않도록 가드가 필요한지.",
        ],
    },
    {
        "n": "9", "slug": "forbid", "name": "금지 규칙", "sub": "이 컬럼으로는 답하지 마라",
        "gist": "존재하지만 **정보량이 없거나 신뢰할 수 없는** 컬럼이 있다. 배제를 명시적으로 선언한다.",
        "defect": [
            "값이 전부 0 인 컬럼이 있다 — 채우려다 만 것으로 보이나 근거가 없어 단정할 수 없다.",
            "2차에서 100% 결측이 된 컬럼이 있다. 필터에 쓰면 **전 행이 탈락**한다.",
            "다른 컬럼과 99% 동일값이라 정보량이 0 인 컬럼이 있다.",
        ],
        "rule": [
            "`전부0컬럼금지`·`과세수익률금지`·`더티금지`·`등급일사용금지` — **컬럼 이름으로 금지 목록을 선언**.",
            "금지 사유를 함께 적어 답변이 “데이터가 제공되지 않았습니다” 로 나가게 한다.",
        ],
        "ev": [
            ("전량 0 — non-null 이지만 값이 전부 0 이라 정보가 없다",
             "select count(*) as non_null, sum(case when avg_annual_tax_yield=0 then 1 else 0 end) as 값이_0 "
             "from domestic_bonds where avg_annual_tax_yield is not null"),
            ("100% 결측 — 필터에 쓰면 전 행 탈락",
             "select count(*) as 전체, sum(case when fd_wk1_ern_r is null then 1 else 0 end) as fd_wk1_ern_r_결측 "
             "from public_funds"),
        ],
        "risk": "‘기타비용 낮은 ETF’ 처럼 **전부 0 인 컬럼으로 순위를 매기면 아무 의미 없는 답**이 나간다.",
        "check": [
            "금지 컬럼이 SQL 가드(`validate_sql`)에서 **기계적으로 차단되는가**, 아니면 프롬프트 문구뿐인가. "
            "후자면 지켜진다는 보장이 없다.",
            "금지 목록이 2차에서도 유효한가 — 1차엔 전부 0 이었으나 2차에 채워진 컬럼이 있다"
            "(해외ETF `du_er_1d` 가 그 사례).",
            "해외ETF·펀드에도 전량 0/상수 컬럼이 있는가 — `auto.yaml` 재생성 후 전수 확인.",
            "금지 대신 ‘조건부 사용’ 이 맞는 컬럼이 있는가(예: 장내 한정으로는 유효한 컬럼).",
            "금지 사유가 답변 문구로 잘 번역되는가 — ‘제공되지 않았습니다’ vs ‘해당 없습니다’ 구분.",
        ],
    },
    {
        "n": "10", "slug": "absent", "name": "부재 선언", "sub": "컬럼이 없다는 사실도 지식이다",
        "gist": "값이 비어 있는 것과 **컬럼이 아예 없는 것**은 다르다. 후자는 HCX 호출 없이 즉시 기각한다.",
        "defect": [
            "해외ETF 에는 **기간 수익률 컬럼 자체가 없다.** 1일수익률 하나뿐.",
            "해외ETF 에 위험등급 컬럼이 없고, 채권에 기초지수 컬럼이 없다.",
            "이걸 모르면 플래너가 없는 컬럼으로 SQL 을 만들어 실행 오류를 낸다.",
        ],
        "rule": [
            "`absent_in` 으로 **컬럼 부재를 선언**하고 `.ttl` 에 속성 부재로 기록.",
            "`build_ontology.py` **V6 검증** — 부재 선언했는데 실제로 컬럼이 있으면 빌드를 거부.",
            "게이트가 이 선언을 보고 **HCX 호출 0회로 기각**한다.",
            "주최 확정(OQ-2, 8/26): 해외ETF 1년 수익률 질의는 출제되지 않으며 교차 TOP-N 에서 **제외해도 무방**.",
        ],
        "ev": [
            ("해외ETF 의 수익률 컬럼은 하나뿐 — 국내ETF 와 대조",
             "select '해외ETF' as 테이블, group_concat(name, ', ') as 수익률컬럼 "
             "from pragma_table_info('overseas_etfs') where name like 'du_er%' "
             "union all select '국내ETF', group_concat(name, ', ') "
             "from pragma_table_info('domestic_etfs') where name like 'du_er%'"),
        ],
        "risk": "없는 컬럼으로 SQL 을 만들면 실행 오류 → 무응답. 부재를 선언해 두면 **‘미수록’ 이라고 정확히 답한다.**",
        "check": [
            "부재 선언이 **개체 5종에만** 있다. 컬럼 수준 부재(해외ETF 기간수익률)는 어디에 선언돼 있는가 "
            "— `_absent_columns` 가 도메인 yaml 에 없다.",
            "게이트가 실제로 부재 선언을 읽어 기각하는가 — `tests/` 에 회귀 테스트가 있는가.",
            "부재인데 선언되지 않은 축이 더 있는가 — 도메인 × 축 교차표(`graph_sources_review` §0)와 대조.",
            "‘없음’ 을 답하는 문구가 `not_applicable` 과 구분되는가 — 컬럼 부재 vs 값 부재.",
            "OQ-2 답변 반영으로 해외ETF 관련 부재 선언 문구를 갱신했는가.",
        ],
    },
    {
        "n": "11", "slug": "hierarchy", "name": "계층", "sub": "‘미국’ 질의가 ‘북미’ 를 포함하는가",
        "gist": "개체에 부모를 달고 조상을 **빌드 타임에 전부 펼쳐** 둔다. 런타임 비용 0.",
        "defect": [
            "사용자는 ‘아시아 투자 ETF’ 라고 묻는데 데이터에는 ‘한국’·‘중국’ 이 들어 있다.",
            "신용등급은 서열이 있는 범주다 — ‘AA- 이상’ 은 문자열 비교로 안 풀린다.",
        ],
        "rule": [
            "`shared/<개체>.yaml` 의 `parent` 로 계층 선언 → `kg_closure` 에 **조상 전개**.",
            "CreditGrade 는 `rank` 와 투자/투기 밴드를 함께 선언해 ‘이상/이하’ 비교가 가능하게.",
        ],
        "ev": [
            ("개체별 노드 수",
             "select node_type as 개체, count(*) as 노드수 from kg_node group by 1 order by 2 desc"),
            ("조상 전개 결과 — 런타임 재귀 없이 조회된다",
             "select count(*) as kg_closure_행, count(distinct ancestor_id) as 조상노드, "
             "count(distinct descendant_id) as 자손노드 from kg_closure"),
        ],
        "risk": "계층이 없으면 ‘아시아’ 질의가 0건을 반환한다. **AssetClass·Currency·RiskGrade 는 아직 `parent` 가 없다.**",
        "check": [
            "🔴 `parent` 없는 개체(AssetClass·Currency·Organization·RiskGrade) 중 계층이 "
            "**정말 필요 없는 것**은 무엇인가. AssetClass 는 ‘주식형 ⊃ 국내주식형’ 이 필요해 보인다.",
            "Organization 계열사 관계(`subsidiaryOf`)가 3건뿐이다 — 운용사 275종에 계열 구조가 있는가.",
            "Region 계층이 사용자 어휘와 맞는가 — ‘신흥국’·‘선진국’ 같은 축이 있는가.",
            "CreditGrade `rank` 로 ‘AA- 이상’ 이 실제로 풀리는지 gold SQL 로 확인(OFFICIAL-001).",
            "Index 패밀리 계층(‘S&P500 계열’)이 어디까지 묶여 있는가.",
        ],
    },
    {
        "n": "12", "slug": "asof", "name": "기준일·시점", "sub": "언제 기준의 사실인가",
        "gist": "테이블마다 기준일이 다르다. 답변에 **어느 시점 사실인지**를 병기하고 미래 질의는 기각한다.",
        "defect": [
            "채권 마스터의 실제 정보 기준일은 **8/21**(영업일)인데 대회 기준일은 8/22 다.",
            "외부 Holdings 는 국내 8/21, 해외는 상품마다 3/31~6/30 로 흩어져 있다.",
            "‘2026년 10월 상장 예정’ 같은 **미래 질의**는 데이터로 답할 수 없다.",
        ],
        "rule": [
            "`query_rules.기준일` 로 도메인별 기준일 선언 + 답변 병기.",
            "`ext_*` 는 `as_of`/`report_date` **병기 강제**.",
            "게이트가 **컷오프 검사** — 8월까지 허용, 9월 이후는 HCX 호출 없이 기각.",
        ],
        "ev": [
            ("마스터와 채권 정보 기준일이 다르다",
             "select table_name as 테이블, as_of as 대회기준일 from build_info"),
            ("외부 자료 기준일 — 마스터와도, 서로도 다르다",
             "select 'ext_etf_holdings(국내)' as 소스, min(as_of) as 최소, max(as_of) as 최대 from ext_etf_holdings "
             "union all select 'ext_ovs_etf_holdings(해외)', min(report_date), max(report_date) from ext_ovs_etf_holdings "
             "union all select 'ext_fund_holdings(펀드)', min(bas_dt), max(bas_dt) from ext_fund_holdings"),
        ],
        "risk": "기준일을 안 밝히면 **8/22 답변에 3/31 구성종목이 섞인다.** 미래 질의에 억지로 답하면 환각이 된다.",
        "check": [
            "`기준일` 규칙이 채권에만 있다. 나머지 3도메인은 어디에 선언돼 있는가.",
            "답변 템플릿에 기준일 병기가 **필수 항목으로 강제**돼 있는가(안건 §1-7).",
            "컷오프 경계 — 8/23~8/31 질의는 허용인가. `tests/` 회귀가 8월 허용·9월 기각만 검사한다.",
            "외부 자료 발행일 상한 8/24 를 수집 스크립트가 `assert` 로 강제한다. 재수집 시에도 유지되는가.",
            "해외 Holdings 6/30 분이 적은 것(제출기한 8/29 미도래)을 ‘결측’ 이 아니라 ‘정상’ 으로 답하는 규칙이 있는가.",
        ],
    },
]
