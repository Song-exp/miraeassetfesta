# KG 구조 검증 실측 기록 — 2026-09-02 (35 + 형제 X25)

> 온톨로지·KG 구조를 시험하는 문항(설계 `docs/kg_structure_probe_design_2026-09-02.md`). 기준선 = 구조 큐 반영 전 · 2R = S1·S3~S6 + 검사기 일반화 · 3R = N1·N2·N4 + I~M. 채점: `docs/kg_structure_probe_round1~3_2026-09-02.md`.

## 판정 요약

| ID | 질문 | 기준선(31e72ef) | 2라운드(6bad723) | 3라운드(1e0e641) |
| :-- | :-- | :-- | :-- | :-- |
| KG-001 | Mirae Asset이 운용하는 공모펀드는 몇 개야? | ❌ 오거절 — Ground 가 'Asset' 을 파생 노드 Org_fund_00080164 에 오매칭, 영문 alias 는 ETF 컬럼에만 · HCX mgmt_co_nm LIKE 'Mirae Asset' 0행 → '수록되어 있지 않다' 거짓 사유 (gold 823/2,066) [KG 개체·alias → 조립] | ✅ 823/2,066 + 역외 5(00130006) 별도 병기 — S1 label_en 슬롯+_mgr_brand_en('Mirae Asset'), derived 'Asset' 키 제외 [개선 ❌→✅] | 200 · 2.6s |
| KG-002 | 프랭클린템플턴이 운용하는 공모펀드 알려줘 | ❌ — TRIM 가드가 public_funds.TRIM( 생성 → 기각, 재생성서 공백무시 가드가 p.REPLACE( 생성 → OperationalError → '오류'. 구상호→우리 이관 관계는 KG 에 없음 [SQL가드(별칭-함수 접두) → KG] | ❌ — 결정층은 옳음(former_names→IN('00040022','00040007')·27행·판매중클래스수 병기) 이나 HCX 가 Ground 주석('현재 우리자산운용이 운용')을 버리고 '프랭클린템플턴이 운용하며 판매중' 으로 서술, 판매완료 13펀드를 판매중으로 나열 (must '우리자산운용' 0회) [형태 변화 오류→오답 · 조립(개별조회 경로 HCX 전사)] | 200 · 15.4s |
| KG-003 | 메리츠자산운용이 운용하는 공모펀드는 몇 개야? | ❌ — HCX 가 or_co='A011' 날조, 검사기 통과, 개수 조립기 '0개' 단언. 값은 우연히 0 이나 근거 날조 · '해당 운용사 없음' 사유 부재 [HCX 날조 → SQL가드 → 조립(0행 단언)] | ✅ — '메리츠자산운용' 구상호 → KCGI 27/133 + '현재 케이씨지아이자산운용 기준' 병기. 날조 코드 소멸, 도메인 사실 부합(gold 의 KCGI 추정 안내 허용). 기계 말투 노출 🟢 [개선 ❌→✅ · S1 former_names] | 200 · 33.6s |
| KG-004 | 한국 투자 신탁 운용 이 운용하는 공모펀드는 몇 개야? | ❌ 거짓 0개 — 공백 삽입 표기가 Ground 부분일치에 안 걸림 → HCX or_co=80000000 날조 → 실재 143/541 을 '0개' 단언 (환각 동급) [KG 개체(정규화) → HCX → 조립] | ✅ 143/541 + '운용사 코드 2건(00040024·00040105) 합산' — S1 _flex_match 공백 정규화 [개선 ❌→✅] | 200 · 2.6s |
| KG-005 | 이름이 삼성으로 시작하는 공모펀드는 몇 개고, 그중 삼성자산운용이 운용하는 건 몇 개야? | ❌ — ext INNER JOIN + mgmt_co_nm 집계로 클래스 868/811 산출(ext 미수록 38행 탈락), 펀드단위 가드 미발동, HCX 가 '811개/811개' 전사 · 삼성액티브 분리 없음 (gold 217=207+10) [플래너 → SQL가드 → HCX] | 🟡 — 217/906 정확(1문) 이나 2문(삼성자산운용 207/850·삼성액티브 10/56) 통째로 누락: HCX 가 접두 COUNT 1개만 내고 기계 조립기가 1행 완결 처리 [개선 ❌→🟡 · 플래너(2집계→1)→조립] | 200 · 2.6s |
| KG-006 | 미래에셋코어테크 펀드의 운용사와 수탁사는 어디야? | ❌ 오거절 — mtco_nm·trusc_nm 환각 → 재생성도 실패. 수탁사 코드→이름이 KG 노드에만 있고 DB 테이블 없음 (gold 미래에셋자산운용/신한은행 00020088) [온톨로지(역할·이름 부재) → 플래너] | ❌ 오거절 유지 — S2 미착수. 재생성 SQL(mgmt_co_nm+trusc 코드)은 실행 가능했는데 ambiguous_columns 가 서브쿼리 스코프의 itm_no 를 모호로 오판해 기각 [온톨로지(S2)+가드(모호 검사 과잉 N8)] | 200 · 6.6s |
| KG-007 | 미래에셋자산운용에 의해 운용되는 공모펀드는 몇 개야? | ✅ 823/2,066 — '운용되는' 트리거 없이도 KG 매핑으로 수렴 (inverseOf 는 여전히 문서 장식) | ✅ 유지 823/2,066 (+역외 5 병기) | 200 · 2.7s |
| KG-008 | 공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘 | ❌ 오거절 — trusc_itt_nm 환각 2회 → 거절. 수탁사 이름 컬럼 부재 (gold HSBC 714 · 국민 516 · 씨티 465) [온톨로지 → 플래너] | ❌ 오거절 유지 — trusc_itt_nm_ko 환각 2회. 수탁사 이름이 SQL 층에 없음 [S2] | 200 · 46.7s |
| KG-009 | 미래에셋증권이 수탁사인 공모펀드도 있어? | ❌ — SQL·행은 정확(2펀드/14클래스) 인데 HCX 가 '없습니다 … 다른 기관이 수탁' 으로 반전 서술 [조립(HCX)] | ✅ — 전체 2개(14클래스) iM에셋 타이거 포커스 1,456억·6 / 머스트원앤온리 968억·8. 목록 기계 조립로 반전 서술 소멸 [개선 ❌→✅] | 200 · 2.6s |
| KG-010 | 미래에셋코어테크 펀드의 모펀드는 뭐야? | ❌ — '코어테크' 부분일치가 형제 6펀드 혼입 → HCX 가 글로벌코어테크EMP·차이나코어테크 모펀드를 답하고 정답 미래에셋코어테크증권모투자신탁(주식) 누락, '재간접' 노출 [SQL가드(상품명 필터) → 조립] | ❌ 유지 — 조회 30행에 정답 '미래에셋코어테크증권모투자신탁(주식)' 10회 실렸는데 HCX 가 형제 모펀드 2개를 답하고 '재간접형' 노출. 부분일치 41행(S8/R15 미착수) [가드→조립] | 200 · 5.0s |
| KG-011 | KB자산운용 펀드 중 국민은행이 수탁하는 공모펀드는 몇 개야? | 🟡 — 값 0 정확(두 조건 반영) 이나 머리말 'KB자산운용이 운용하는 공모펀드는 0개' 로 수탁 조건 탈락(거짓 문장) · 국민은행 제2코드·실제 수탁 분포 미병기 [조립] | ✅ — 'KB자산운용이 운용하고 국민은행이 수탁하는 … 0개(각 조건의 개체·값은 실재하며 교집합 0)' — R1(a) 단언 적절. 이웃 분포 미병기(가점) [개선 🟡→✅] | 200 · 2.7s |
| KG-012 | 해외주식형 중에서 중국주식 유형인 공모펀드는 몇 개야? | ❌ 거짓 0개 — yaml 템플릿 <코드> 를 '<CHN>' 리터럴로 복사 + '중국주식 유형' 을 국가 태그로 오해 → 실재 205/522 를 '0개' 단언 [플래너 → SQL가드(템플릿 잔재 미검사) → 조립] | 🟡 — 205/522 정확(precheck 템플릿 잔재 + R10 '유형'→zrin_ptn_nm) 이나 유형 기준 고지·'중국주식' 토큰 없음(gold must) [개선 ❌→🟡 · 조립 R8] | 200 · 2.7s |
| KG-013 | 위험등급 7등급인 공모펀드 알려줘 | 🟡 — 게이트 즉답 ✓ 이나 '0~6 범위' 문구(펀드는 1~6, 0 은 채권 미분류 코드) · must '1' 미충족 [게이트 상수/온톨로지 riskGradeValue 과대허용] | ✅ — 게이트 즉답 '1(매우 높은 위험)~6(매우 낮은 위험), 7등급 없음, 0등급 없음·미수록 NULL' — S6 range_by_table [개선 🟡→✅] | 200 · 0.2s |
| KG-014 | 위험등급 0등급 공모펀드는 몇 개야? | 🟡 — 게이트 미발동(0 허용) → SQL 0/0 → '0개' 단언. NULL 422 를 0 으로 읽진 않았으나 '펀드는 1~6, 0등급 없음' 설명 없음 [게이트 → 조립] | ✅ — 게이트 기각(0 정의역 밖) HCX 0회, 'NULL≠0' 설명 [개선 🟡→✅] | 200 · 0.3s |
| KG-015 | 위험등급이 '높은위험'인 공모펀드는 몇 개야? | ❌ — RiskGrade_2 에 '높은위험' alias 가 있으나 Ground 는 label 만 키로 써 미매칭 → HCX 정확일치 4/20 (gold 995/2,994) [KG 개체(alias 미승격) → 가드] | ✅ 995/2,994 — RiskGrade 이름형 alias raw 승격 → IN('높은위험','높은 위험') [개선 ❌→✅] | 200 · 2.2s |
| KG-016 | 채권혼합 공모펀드는 몇 개야? | 🟡 — 389/933 정확(약관 or_attr_desc) 이나 기준 미고지·제로인 240/534 미병기 → 부분 (Q8 로 해소 예상) [조립] | 🟡 유지 — 389/933(약관) 정확, 기준 미고지·제로인 240/534 미병기 [조립 R8] | 200 · 63.6s |
| KG-017 | 폐쇄형 공모펀드는 몇 개야? | ❌ 거짓 0개 — yaml '폐쇄 태그 미확인' 오서술이 실려 han_clas_policies LIKE '%폐쇄형%' 오선택 → 실재 3/6(C104) 을 '0개' 단언 [온톨로지 규칙(yaml) → 플래너 → 조립] | ✅ 3/6 — FundAttr_C104 token + R11 확정식(han_clas_policies 절 제거). 태그 미보유 418행 병기 없음(가점) [개선 ❌→✅] | 200 · 2.4s |
| KG-018 | 단위형이면서 개방형인 공모펀드도 있어? | ❌ — 조건을 버리고 zrin_btyp_nm 목록 조회 → '찾을 수 없다' + '단위형=설정액 규모 조건' 도메인 날조 (gold 31/189) [플래너 → 조립(HCX 환각)] | ❌ — canon C102∧C103 주입됐으나 HCX 의 itm_abrv_nm LIKE '%단위%'/'%개방%' 절을 못 걷어냄(통칭 낱말 기준) + sale_yn 미주입 → 0행 → '조건 중 일부는 상품 자체가 없다' 거짓 유보(실재 31/189). 도메인 날조는 소멸 [형태 변화 날조→거짓 유보 · 가드(N5)+R1(c) 오진] | 200 · 2.3s |
| KG-019 | 일본에 투자하는 공모펀드 알려줘 | 🟡 — SQL 정확(38/103, JPN ∪ 이름) 이나 30행 중 8행만 나열·'일부입니다'·피델리티재팬 누락 (Q5 로 해소 예상) [조립] | ✅ — 전체 31/79 + 순자산순 30행 전량, 피델리티재팬 239억 1위 — Country_JPN token + 목록 기계 조립. 같은 이름 펀드가 펀드키로 4~6행 갈림(약점 #1 노출 🟢) [개선 🟡→✅] | 200 · 2.5s |
| KG-020 | 미국에 투자하는 공모펀드는 몇 개야? | ✅ 98/333 — USA 태그 확정식 발동 | ✅ 유지 98/333 | 200 · 2.7s |
| KG-021 | 대만에 투자하는 공모펀드 있어? | ❌ 오거절 — '대만' 은 국가어 사전(11종) 밖·Region_Taiwan public_funds alias 0 → HCX 가 fd_estb_ctry_cd=410(설립국 한국) 오용 → '확인 불가' (gold 피델리티대만펀드 1) [라우터/가드 → 플래너 → KG] | ✅ — 피델리티대만펀드 1클래스 — Country_TWN 희소 판정(기본모수 0행) → 이름 폴백 OR. 설립국 오용 소멸 [개선 ❌→✅] | 200 · 4.0s |
| KG-022 | 유럽에 투자하는 공모펀드는 몇 개야? | 🟡 — 61/193 정확(지역 컬럼) 이나 기준 미고지·확장 93/259 미병기 → 부분 [조립] | 🟡 유지 — 61/193 정확, 기준 미고지·확장 91/257 미병기 [조립 R8] | 200 · 2.2s |
| KG-023 | 아시아에 투자하는 공모펀드 중 순자산 큰 5개 알려줘 | ❌ — Region_Asia closure 가 Region_Korea('국내') 유입 → IN('국내','아시아') → 국내 MMF 5개 도배(삼성MMF법인제1호 12.4조) [온톨로지 제약(closure) → 가드] | ✅ — KB중국본토A주 1,453·차이나솔로몬1호 1,393·한투베트남그로스 1,066·신한중국의꿈2호 1,038·다이와넥스트AP1호 668 (gold 5/5) — S4 closure scope(Region_Korea 제외, 후손 12) + 대표행 GROUP BY [개선 ❌→✅] | 200 · 50.6s |
| KG-024 | 반도체 테마 공모펀드는 몇 개야? | ✅ 12/78 — 이름 ∪ 태그 | ❌ 회귀 ✅→❌ — 10/50 (gold 12/78). '반도체'→FundAttr_N144 Ground 후 ① HCX 가 wrap 없는 LIKE '%,N144,%' (첫 토큰 14클래스 누락 64→50) ② 기준선의 '태그∪이름' 규칙(이름만 2펀드 14클래스) 소실. 속성 태그 확정식이 C축 통칭에만 걸림 [가드(token canon 전 축 미적용 N4)] | 200 · 2.5s |
| KG-025 | 삼성자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야? | ❌ — or_co_xtn_itt_cd IN ('삼성','삼성KODEX')(ETF alias 를 펀드 코드 컬럼에) → 0 → "'미수록'" · ETF 는 운용사 필터 없이 1,534 전체 (gold 207 · 224) [플래너 → SQL가드(IN 리터럴 미검증) → KG(교차 alias 오염)] | ❌ — 오거절: precheck 가 or_co IN('삼성','삼성KODEX') 를 실존 코드 아님으로 2회 기각(거짓 '미수록'/1,534 소멸). Ground 라인이 펀드 코드·ETF alias 를 한 줄에 실어 HCX 가 컬럼 혼동, 'ETF'→FundAttr_M113 오염 신규 [형태 변화 거짓→거절 · R4 미착수+N9] | 200 · 6.0s |
| KG-026 | KOSPI200을 벤치마크로 쓰는 공모펀드와 KOSPI200을 추종하는 국내 ETF는 각각 몇 개야? | ❌ 오거절 — pd_base_index 환각 2회 → 거절. 지수 alias(cu_base_index 'KOSPI200' 9 vs ref_base_index 'KOSPI 200 CR' 등) 불일치는 도달 전 실패로 잠재 확인 (gold 421 · 50) [플래너 → KG] | ❌ 형태 악화 거절→거짓 단언 — '펀드 2,888개(sale_yn 없음·클래스수; 기본모수 815/2,217·정확일치 421/1,266) · ETF 수록되지 않음(cu_base_index='KOSPI200' 9건 전부 pd_sale_yn=0; ref_base_index 정본 50)'. UNION 분기 0 을 거짓 0 으로 단언 — 신규 감점 [S7 지수 alias + 가드(교차 분기별 모수·0행 정책 N3)] | 200 · 46.7s |
| KG-027 | 미래에셋코어테크 펀드 설정 좌수 알려줘 | ❌❌ 환각 — fd_set_pcd='10'(설정유형코드) 를 '10좌' 로 6펀드 단언. 좌수 ABSENT 선언·게이트 부재 [게이트/온톨로지 → HCX] | ✅ — ABSENT(hasUnitsOutstanding, vocab 좌수) 게이트 즉답 HCX 0회 + 순자산·기준가 대체 안내. '10좌' 환각 소멸 [개선 ❌❌→✅ · S5/R2] | 200 · 0.2s |
| KG-028 | 미래에셋코어테크 펀드가 가장 많이 보유한 종목은 뭐야? | ❌ 오거절 — 라우팅 public_funds 인데 domestic_etfs+ext_etf_holdings 'SELECT TOP 1' 생성, 검사기가 대상 밖 테이블 통과 → OperationalError (gold 삼성전자 24.95%) [플래너 → SQL가드] | ❌ 형태 악화 오류→환각 — 'IBK K-AI반도체코어테크 ETF 57.12%': 펀드 질의에 domestic_etfs JOIN ext_etf_holdings 가 통과(교차 플래그로 라우팅 밖 테이블 검사 미발동) + 상품 고유명이 pd_nm 에 붙음. gold 삼성전자 24.95% 실재 [가드(N1 교차 시 테이블 범위)+Ground(N2 상품 고유명 핀)] | 200 · 8.0s |
| KG-029 | 우리자산운용 펀드 수를 대표예탁원종목번호 기준으로 세면 몇 개야? | ✅ 88 — 사용자 명시 기준(rptt) 존중, 가드 키 치환 없음 (현행키 235 병기 없어 만점 아님) | ✅ 유지 88 (rptt) | 200 · 3.9s |
| KG-030 | 미래에셋차이나솔로몬 시리즈는 몇 호까지 있고 각각 클래스가 몇 개야? | ❌ — 미특정 라우팅 → han_clas_policies IS NOT NULL 로 1호·3호 4행 탈락 → '5호까지'(근거 0)·3호 4·2호 5·합 9 날조 (gold 1호2·2호7·3호8) [라우터 → 플래너 → 조립] | 🟡 — '3호까지' ✓ 1호 2 ✓ 이나 2호 5(gold 7)·3호 5(gold 8)·합 12(gold 17): 17행 정확 조회 후 HCX 오산. '5호' 날조·정책 필터 소멸 [개선 ❌→🟡 · 조립(LLM 산술, R14 확정식 미착수)] | 200 · 52.8s |
| KG-031 | 피델리티가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야? | ❌ — '역외' 가 _POP_WIDEN 에 걸려 sale_yn 미주입 + HCX 가 JP모간 코드 00080030 을 IN 에 날조 → 167/350 (판매완료·JP모간 포함, 역외 00130001 미포함; gold 153/293) [SQL가드 → HCX → KG] | ❌ 유지 — 167/350 동일(JP모간 00080030 실존 코드라 precheck 통과·'역외' _POP_WIDEN 로 sale_yn 없음) + '역외펀드 47개는 별도 법인이라 포함하지 않았다' 가 질문('포함하면')과 모순. gold 153/293 [가드 R6(코드 집합 확장·Ground 밖 코드 기각)] | 200 · 2.2s |
| KG-032 | 2026년 9월 1일 기준으로 순자산이 가장 큰 공모펀드 알려줘 | ✅ 기준일 2026-08-22 명시 후 이후 시점 거절 — reject 형 정답 | ✅ 유지 — 기준일 2026-08-22 명시 후 이후 시점 거절 | 200 · 2.5s |
| KG-033 | 가장 최근에 설정된 공모펀드 알려줘 | 🟡 — KB K-성장과 지배구조 30 목표전환 2026-06-12 ✓ 이나 LIMIT 1 로 동률 2건 중 1건·커버리지 미병기 [플래너 → 조립] | 🟡 유지 — 2026-06-12 KB K-성장과 지배구조 30 ✓, LIMIT 1 로 동률(미래에셋국민참여형) 누락·커버리지 미병기 [R9] | 200 · 69.7s |
| KG-034 | 미래에셋코어테크 펀드는 운용한 지 얼마나 됐어? | ❌ 오거절 — '운용한 지' 가 설명서항목 트리거에 없어 ext 미조인 → fd_estb_dt 환각 2회 → 거절 (gold 2019-10-23, 6년 10개월) [라우터/규칙 트리거 → 플래너] | ❌ 형태 변화 거절→거짓 유보 — HCX 가 Ground 상품 고유명 '코어테크' 를 '코어텍' 으로 옮겨 0행 → '상품 자체가 없다'. '운용한 지' 트리거 부재로 estb_dt 조차 없음 [가드(N2 이름 리터럴 핀)+라우터(R9)+R1(c)] | 200 · 3.4s |
| KG-035 | 2026년에 설정된 공모펀드는 몇 개야? | ❌ — 재생성 JOIN COUNT(*) 에 펀드단위 가드 미적용 → 클래스 124 를 '124개' 펀드로 (gold 39/124) [SQL가드(JOIN·재생성 경로)] | ❌ 유지 — '124개'(클래스). 외부 JOIN 주입 가드는 발동했으나 JOIN 경로에 펀드단위 가드 미적용 [R7] | 200 · 3.7s |
| X1 | 미래에셋코어테크 펀드가 가장 많이 담은 종목 3개 알려줘 | — | — | 200 · 7.2s |
| X2 | KB중국본토A주 펀드가 가장 많이 보유한 종목은 뭐야? | — | — | 200 · 33.6s |
| X3 | 미래에셋 코어택 펀드 순자산 알려줘 | — | — | 200 · 2.6s |
| X4 | 친환경 테마 공모펀드는 몇 개야? | — | — | 200 · 2.4s |
| X5 | 2차전지 테마 공모펀드는 몇 개야? | — | — | 200 · 2.2s |
| X6 | 개방형이면서 추가형인 공모펀드는 몇 개야? | — | — | 200 · 2.8s |
| X7 | KOSPI200을 추종하는 국내 ETF는 몇 개야? | — | — | 200 · 48.7s |
| X8 | S&P500을 벤치마크로 쓰는 공모펀드와 S&P500 추종 국내 ETF는 각각 몇 개야? | — | — | 200 · 8.3s |
| X9 | 미래에셋자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야? | — | — | 200 · 51.7s |
| X10 | 이름이 KB로 시작하는 공모펀드는 몇 개고 그중 KB자산운용이 운용하는 건 몇 개야? | — | — | 200 · 3.1s |
| X11 | 동양자산운용이 운용하는 공모펀드 알려줘 | — | — | 200 · 9.1s |
| X12 | 슈로더가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야? | — | — | 200 · 5.8s |
| X13 | KB자산운용 펀드의 수탁사 분포 알려줘 | — | — | 200 · 45.7s |
| X14 | 삼성코리아대표 펀드의 수탁사는 어디야? | — | — | 200 · 3.7s |
| X15 | 중국에 투자하는 공모펀드와 국내 ETF는 각각 몇 개야? | — | — | 200 · 8.0s |
| X16 | ETF에 투자하는 공모펀드는 몇 개야? | — | — | 200 · 65.6s |
| X17 | 미래에셋차이나솔로몬 2호는 클래스가 몇 개야? | — | — | 200 · 5.4s |
| X18 | 미래에셋코어테크증권자투자신탁의 모펀드는 뭐야? | — | — | 200 · 4.6s |
| X19 | 2025년에 설정된 공모펀드는 몇 개야? | — | — | 200 · 51.4s |
| X20 | 가장 최근에 설정된 공모펀드 2개 알려줘 | — | — | 200 · 6.3s |
| X21 | 스페인에 투자하는 공모펀드 있어? | — | — | 200 · 2.8s |
| X22 | KB자산운용 펀드 중 국민은행이 수탁하는 공모펀드는 몇 개야? 실제 수탁사는 어디야? | — | — | 200 · 4.9s |
| X23 | 미래에셋코어테크 펀드 운용역이 누구야? | — | — | 200 · 0.2s |
| X24 | 미래에셋코어테크 펀드 기준가 추이 알려줘 | — | — | 200 · 0.3s |
| X25 | 미래에셋코어테크 펀드 기준가 알려줘 | — | — | 200 · 8.8s |

---

## KG-001. Mirae Asset이 운용하는 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 6.9s · ❌ 오거절 — Ground 가 'Asset' 을 파생 노드 Org_fund_00080164 에 오매칭, 영문 alias 는 ETF 컬럼에만 · HCX mgmt_co_nm LIKE 'Mirae Asset' 0행 → '수록되어 있지 않다' 거짓 사유 (gold 823/2,066) [KG 개체·alias → 조립]

**answer**

```text
미래에셋이 운용하는 공모펀드의 수는 확인할 수 없습니다. 이는 제공된 데이터에 수록되어 있지 않은 정보이기 때문입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'Asset' → Org_fund_00080164 (Organization) → public_funds.or_co_xtn_itt_cd='00080164'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,343자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
8. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
9. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(or_co_xtn_itt_cd) IN (SELECT or_co_xtn_itt_cd FROM ext_fund_page WHERE mgmt_co_nm LIKE '%Mirae Asset%') AND prvo_pbff_desc = '공모') LIMIT 30
11. [Guard] SQL 기각 — 여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): itm_no — 테이블 별칭을 붙이고 p.itm_no 처럼 모두 한정한다
12. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.4s)
13. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT COUNT(*) FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' AND ext_fund_page.mgmt_co_nm LIKE '%Mirae Asset%' LIMIT 30
14. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
15. [Execute] 1행 조회 (상한 30)
16. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
17. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(*)
0
```

</details>

### 2라운드(6bad723) — HTTP 200 · 54.9s · ✅ 823/2,066 + 역외 5(00130006) 별도 병기 — S1 label_en 슬롯+_mgr_brand_en('Mirae Asset'), derived 'Asset' 키 제외 [개선 ❌→✅]

**answer**

```text
미래에셋자산운용이 운용하는 공모펀드는 823개(클래스 2,066개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
종목명이 '미래에셋' 로 시작하는 역외펀드 5개(클래스 5개, 해외 운용법인 코드 00130006)는 별도 법인이라 이 수에 포함하지 않았습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'Mirae Asset' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
823 | 2066
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.6s

**answer**

```text
미래에셋자산운용이 운용하는 공모펀드는 823개(클래스 2,066개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
종목명이 '미래에셋' 로 시작하는 역외펀드 5개(클래스 5개, 해외 운용법인 코드 00130006)는 별도 법인이라 이 수에 포함하지 않았습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'Mirae Asset' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
823 | 2066
```

</details>

---

## KG-002. 프랭클린템플턴이 운용하는 공모펀드 알려줘

### 기준선(31e72ef) — HTTP 200 · 6.9s · ❌ — TRIM 가드가 public_funds.TRIM( 생성 → 기각, 재생성서 공백무시 가드가 p.REPLACE( 생성 → OperationalError → '오류'. 구상호→우리 이관 관계는 KG 에 없음 [SQL가드(별칭-함수 접두) → KG]

**answer**

```text
데이터 조회 중 오류가 발생해 확인할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '프랭클린' → Org_00040022 (Organization) → public_funds.or_co_xtn_itt_cd='00040022'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '템플턴' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,518자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 상품명 필터 주입 — 질문의 고유명 '템플턴' 이 SQL 에 없어 itm_nm LIKE 주입 + LIMIT 1 해제 (2026-08-31 밤 FND-016 실측: 운용사 코드만 필터한 모수 1,512행에서 임의 1행이 답으로 나갔다)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE public_funds.TRIM(or_co_xtn_itt_cd) = '00040022' AND public_funds.prvo_pbff_desc = '공모' AND public_funds.sale_yn = '판매중' AND ext_fund_page.mgmt_co_nm LIKE '%템플턴%' AND REPLACE(itm_nm,' ','') LIKE '%템플턴%' LIMIT 30
11. [Guard] SQL 기각 — public_funds 에 없는 컬럼: trim
12. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 3.3s)
13. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
14. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT DISTINCT p.itm_no, p.itm_nm FROM public_funds p JOIN ext_fund_page e ON e.itm_no = p.itm_no WHERE p.or_co_xtn_itt_cd = '00040022' AND p.prvo_pbff_desc = '공모' AND p.sale_yn = '판매중' AND e.mgmt_co_nm LIKE '%템플턴%' AND p.REPLACE(itm_nm,' ','') LIKE '%템플턴%' LIMIT 30
15. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
16. [Execute] 실행 실패 — OperationalError
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 2라운드(6bad723) — HTTP 200 · 17.2s · ❌ — 결정층은 옳음(former_names→IN('00040022','00040007')·27행·판매중클래스수 병기) 이나 HCX 가 Ground 주석('현재 우리자산운용이 운용')을 버리고 '프랭클린템플턴이 운용하며 판매중' 으로 서술, 판매완료 13펀드를 판매중으로 나열 (must '우리자산운용' 0회) [형태 변화 오류→오답 · 조립(개별조회 경로 HCX 전사)]

**answer**

```text
프랭클린템플턴이 운용하는 공모펀드는 다음과 같습니다.

1. 프랭클린템플턴포커스자주식C
2. 템플턴밸런스드20채권혼합1호
3. 템플턴프런티어마켓증권자투자신탁(주식)A
4. 우리템플턴글로벌증권자투자신탁(E)(주식)
5. 템플턴프런티어마켓증권자투자신탁(UH)(주식)A
6. 템플턴퇴직연금메이져아시아증권자투자신탁(채권혼합)
7. 템플턴프런티어마켓증권자투자신탁(UH)(주식)Ce
8. 우리템플턴글로벌증권자투자신탁(E)(채권-재간접형)
9. 우리템플턴퇴직연금글로벌40증권자투자신탁(채권혼합)
10. 우리템플턴퇴직연금글로벌증권자투자신탁(채권-재간접형)
11. 프랭클린템플턴파워리서치증권자투자신탁[주식]클래스C-F
12. 우리템플턴글로벌증권자투자신탁(채권-재간접형)ClassA
13. 우리템플턴차이나드래곤증권자투자신탁(E)(주식-재간접형)
14. 템플턴퇴직연금글로벌라이프2025증권자투자신탁[채권혼합]
15. 템플턴퇴직연금글로벌라이프2035증권자투자신탁[채권혼합]
16. 템플턴퇴직연금글로벌라이프2045증권자투자신탁[채권혼합]
17. 우리템플턴이스턴유럽증권자투자신탁(주식-재간접형)ClassA
18. 우리템플턴퇴직연금글로벌채권50증권자투자신탁(채권-재간접형)
19. 우리템플턴월지급글로벌증권자투자신탁(채권-재간접형)ClassA
20. 우리템플턴연금저축글로벌증권자투자신탁(채권-재간접형)ClassC
21. 우리템플턴월지급글로벌증권자투자신탁(채권-재간접형)ClassC-e
22. 우리템플턴연금저축글로벌증권자투자신탁(채권-재간접형)ClassC-e

위 리스트는 프랭클린템플턴이 운용하며 판매중인 공모펀드들 입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '프랭클린' → Org_00040022 (Organization, 정식명 프랭클린템플턴투자신탁운용) → public_funds.or_co_xtn_itt_cd='00040022' · public_funds.or_co_xtn_itt_cd='00040007' ℹ '프랭클린' 은(는) 구상호 — 현재 우리자산운용(00040007)이 운용하며 후계 코드를 함께 조회한다
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '템플턴' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,692자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040022', '00040007') AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%템플턴%' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 27행 조회 (상한 30)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | 대표번호
KR5134450022 | 템플턴이스턴유럽자투자주식C | 1 | 0 | KR0000000000
KR5134450010 | 프랭클린템플턴포커스자주식C | 1 | 0 | KR0000000000
KR5134601001 | 템플턴밸런스드20채권혼합1호 | 1 | 0 | KR0000000000
KR518102039M | 템플턴 퇴직연금 글로벌 증권 자투자신탁(주식) | 1 | 0 | 030440006129
KR512002042M | 템플턴프런티어마켓증권자투자신탁(주식)A | 1 | 0 | 030440631120
KR512002056M | 우리템플턴글로벌증권자투자신탁(E)(주식) | 1 | 1 | 03101000FS02
KR512002006M | 템플턴프런티어마켓증권자투자신탁(주식)Ce | 1 | 0 | 030440631120
KR512002057M | 우리템플턴글로벌증권자투자신탁(주식)ClassA | 1 | 1 | 03101000FS03
KR512002049M | 템플턴프런티어마켓증권자투자신탁(UH)(주식)A | 1 | 0 | 030440631520
KR5134530051 | 템플턴퇴직연금메이져아시아증권자투자신탁(채권혼함) | 1 | 0 | 030440006730
KR512002008M | 템플턴프런티어마켓증권자투자신탁(UH)(주식)Ce | 1 | 0 | 030440631520
KR5134401004 | 우리템플턴글로벌증권자투자신탁(E)(채권-재간접형) | 1 | 1 | 03101000FB19
KR5134530061 | 우리템플턴퇴직연금글로벌40증권자투자신탁(채권혼합) | 1 | 1 | 03101000FB06
KR5134520000 | 우리템플턴퇴직연금글로벌증권자투자신탁(채권-재간접형) | 1 | 1 | 03101000FB32
KR5134450005 | 프랭클린템플턴파워리서치증권자투자신탁[주식]클래스C-F | 1 | 0 | 030442101320
KR5134401003 | 우리템플턴글로벌증권자투자신탁(채권-재간접형)ClassA | 1 | 1 | 03101000FB20
KR512002011M | 우리템플턴차이나드래곤증권자투자신탁(E)(주식-재간접형) | 1 | 1 | 03101000FE10
KR5134530021 | 템플턴퇴직연금글로벌라이프2025증권자투자신탁[채권혼합] | 1 | 0 | 030440452520
KR5134530041 | 템플턴퇴직연금글로벌라이프2035증권자투자신탁[채권혼합] | 1 | 0 | 030440453520
KR5134530031 | 템플턴퇴직연금글로벌라이프2045증권자투자신탁[채권혼합] | 1 | 0 | 030440004545
KR5134450021 | 우리템플턴이스턴유럽증권자투자신탁(주식-재간접형)ClassA | 7 | 7 | 03101000FE02
KR5134520011 | 우리템플턴퇴직연금글로벌채권50증권자투자신탁(채권-재간접형) | 1 | 1 | 03101000FB33
KR5134420010 | 우리템플턴월지급글로벌증권자투자신탁(채권-재간접형)ClassA | 2 | 2 | 03101000FB28
KR512002010M | 우리템플턴차이나드래곤증권자투자신탁(주식-재간접형)ClassA | 1 | 1 | 03101000FE11
KR512001004M | 우리템플턴연금저축글로벌증권자투자신탁(채권-재간접형)ClassC | 1 | 1 | 03101000FB24
KR512009016M | 우리템플턴월지급글로벌증권자투자신탁(채권-재간접형)ClassC-e | 1 | 1 | 03101000FB28
KR512001005M | 우리템플턴연금저축글로벌증권자투자신탁(채권-재간접형)ClassC-e | 1 | 1 | 03101000FB24
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 15.4s

**answer**

```text
프랭클린템플턴이 운용하는 공모펀드는 다음과 같습니다.

1. 프랭클린템플턴포커스자주식C
2. 템플턴밸런스드20채권혼합1호
3. 템플턴프런티어마켓증권자투자신탁(주식)A
4. 우리템플턴글로벌증권자투자신탁(E)(주식)
5. 템플턴프런티어마켓증권자투자신탁(UH)(주식)A
6. 템플턴퇴직연금메이져아시아증권자투자신탁(채권혼합)
7. 템플턴프런티어마켓증권자투자신탁(UH)(주식)Ce
8. 우리템플턴글로벌증권자투자신탁(E)(채권-재간접형)
9. 우리템플턴퇴직연금글로벌40증권자투자신탁(채권혼합)
10. 우리템플턴퇴직연금글로벌증권자투자신탁(채권-재간접형)
11. 프랭클린템플턴파워리서치증권자투자신탁[주식]클래스C-F
12. 우리템플턴글로벌증권자투자신탁(채권-재간접형)ClassA
13. 우리템플턴차이나드래곤증권자투자신탁(E)(주식-재간접형)
14. 템플턴퇴직연금글로벌라이프2025증권자투자신탁[채권혼합]
15. 템플턴퇴직연금글로벌라이프2035증권자투자신탁[채권혼합]
16. 템플턴퇴직연금글로벌라이프2045증권자투자신탁[채권혼합]
17. 우리템플턴이스턴유럽증권자투자신탁(주식-재간접형)ClassA
18. 우리템플턴퇴직연금글로벌채권50증권자투자신탁(채권-재간접형)
19. 우리템플턴월지급글로벌증권자투자신탁(채권-재간접형)ClassA
20. 우리템플턴연금저축글로벌증권자투자신탁(채권-재간접형)ClassC

이상 20개의 공모펀드가 있으며, 모두 판매 중지된 상태입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '프랭클린' → Org_00040022 (Organization, 정식명 프랭클린템플턴투자신탁운용) → public_funds.or_co_xtn_itt_cd='00040022' · public_funds.or_co_xtn_itt_cd='00040007' ℹ '프랭클린' 은(는) 구상호 — 현재 우리자산운용(00040007)이 운용하며 후계 코드를 함께 조회한다
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '템플턴' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,692자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040022', '00040007') AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%템플턴%' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 27행 조회 (상한 30)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | 대표번호
KR5134450022 | 템플턴이스턴유럽자투자주식C | 1 | 0 | KR0000000000
KR5134450010 | 프랭클린템플턴포커스자주식C | 1 | 0 | KR0000000000
KR5134601001 | 템플턴밸런스드20채권혼합1호 | 1 | 0 | KR0000000000
KR518102039M | 템플턴 퇴직연금 글로벌 증권 자투자신탁(주식) | 1 | 0 | 030440006129
KR512002042M | 템플턴프런티어마켓증권자투자신탁(주식)A | 1 | 0 | 030440631120
KR512002056M | 우리템플턴글로벌증권자투자신탁(E)(주식) | 1 | 1 | 03101000FS02
KR512002006M | 템플턴프런티어마켓증권자투자신탁(주식)Ce | 1 | 0 | 030440631120
KR512002057M | 우리템플턴글로벌증권자투자신탁(주식)ClassA | 1 | 1 | 03101000FS03
KR512002049M | 템플턴프런티어마켓증권자투자신탁(UH)(주식)A | 1 | 0 | 030440631520
KR5134530051 | 템플턴퇴직연금메이져아시아증권자투자신탁(채권혼함) | 1 | 0 | 030440006730
KR512002008M | 템플턴프런티어마켓증권자투자신탁(UH)(주식)Ce | 1 | 0 | 030440631520
KR5134401004 | 우리템플턴글로벌증권자투자신탁(E)(채권-재간접형) | 1 | 1 | 03101000FB19
KR5134530061 | 우리템플턴퇴직연금글로벌40증권자투자신탁(채권혼합) | 1 | 1 | 03101000FB06
KR5134520000 | 우리템플턴퇴직연금글로벌증권자투자신탁(채권-재간접형) | 1 | 1 | 03101000FB32
KR5134450005 | 프랭클린템플턴파워리서치증권자투자신탁[주식]클래스C-F | 1 | 0 | 030442101320
KR5134401003 | 우리템플턴글로벌증권자투자신탁(채권-재간접형)ClassA | 1 | 1 | 03101000FB20
KR512002011M | 우리템플턴차이나드래곤증권자투자신탁(E)(주식-재간접형) | 1 | 1 | 03101000FE10
KR5134530021 | 템플턴퇴직연금글로벌라이프2025증권자투자신탁[채권혼합] | 1 | 0 | 030440452520
KR5134530041 | 템플턴퇴직연금글로벌라이프2035증권자투자신탁[채권혼합] | 1 | 0 | 030440453520
KR5134530031 | 템플턴퇴직연금글로벌라이프2045증권자투자신탁[채권혼합] | 1 | 0 | 030440004545
KR5134450021 | 우리템플턴이스턴유럽증권자투자신탁(주식-재간접형)ClassA | 7 | 7 | 03101000FE02
KR5134520011 | 우리템플턴퇴직연금글로벌채권50증권자투자신탁(채권-재간접형) | 1 | 1 | 03101000FB33
KR5134420010 | 우리템플턴월지급글로벌증권자투자신탁(채권-재간접형)ClassA | 2 | 2 | 03101000FB28
KR512002010M | 우리템플턴차이나드래곤증권자투자신탁(주식-재간접형)ClassA | 1 | 1 | 03101000FE11
KR512001004M | 우리템플턴연금저축글로벌증권자투자신탁(채권-재간접형)ClassC | 1 | 1 | 03101000FB24
KR512009016M | 우리템플턴월지급글로벌증권자투자신탁(채권-재간접형)ClassC-e | 1 | 1 | 03101000FB28
KR512001005M | 우리템플턴연금저축글로벌증권자투자신탁(채권-재간접형)ClassC-e | 1 | 1 | 03101000FB24
```

</details>

---

## KG-003. 메리츠자산운용이 운용하는 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.2s · ❌ — HCX 가 or_co='A011' 날조, 검사기 통과, 개수 조립기 '0개' 단언. 값은 우연히 0 이나 근거 날조 · '해당 운용사 없음' 사유 부재 [HCX 날조 → SQL가드 → 조립(0행 단언)]

**answer**

```text
조회 조건에 해당하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,183자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
8. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
9. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(or_co_xtn_itt_cd) = 'A011' AND prvo_pbff_desc = '공모') LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 1행 조회 (상한 30)
13. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.4s · ✅ — '메리츠자산운용' 구상호 → KCGI 27/133 + '현재 케이씨지아이자산운용 기준' 병기. 날조 코드 소멸, 도메인 사실 부합(gold 의 KCGI 추정 안내 허용). 기계 말투 노출 🟢 [개선 ❌→✅ · S1 former_names]

**answer**

```text
케이씨지아이자산운용이 운용하는 공모펀드는 27개(클래스 133개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
'메리츠자산운용' 은(는) 구상호 — 현재 케이씨지아이자산운용(코드 00040087) 기준으로 조회한다
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '메리츠자산운용' → Org_00040087 (Organization, 정식명 케이씨지아이자산운용) → public_funds.or_co_xtn_itt_cd='00040087' ℹ '메리츠자산운용' 은(는) 구상호 — 현재 케이씨지아이자산운용(코드 00040087) 기준으로 조회한다
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040087' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
27 | 133
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 33.6s

**answer**

```text
케이씨지아이자산운용이 운용하는 공모펀드는 27개(클래스 133개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
'메리츠자산운용' 은(는) 구상호 — 현재 케이씨지아이자산운용(코드 00040087) 기준으로 조회한다
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '메리츠자산운용' → Org_00040087 (Organization, 정식명 케이씨지아이자산운용) → public_funds.or_co_xtn_itt_cd='00040087' ℹ '메리츠자산운용' 은(는) 구상호 — 현재 케이씨지아이자산운용(코드 00040087) 기준으로 조회한다
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040087' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
27 | 133
```

</details>

---

## KG-004. 한국 투자 신탁 운용 이 운용하는 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.3s · ❌ 거짓 0개 — 공백 삽입 표기가 Ground 부분일치에 안 걸림 → HCX or_co=80000000 날조 → 실재 143/541 을 '0개' 단언 (환각 동급) [KG 개체(정규화) → HCX → 조립]

**answer**

```text
조회 조건에 해당하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,183자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = 80000000 AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.6s · ✅ 143/541 + '운용사 코드 2건(00040024·00040105) 합산' — S1 _flex_match 공백 정규화 [개선 ❌→✅]

**answer**

```text
한국투자신탁운용이 운용하는 공모펀드는 143개(클래스 541개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
운용사 코드 2건(00040024·00040105)을 합산했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '한국 투자 신탁 운용' → Org_00040024 (Organization, 정식명 한국투자신탁운용) → public_funds.or_co_xtn_itt_cd='00040024' · public_funds.or_co_xtn_itt_cd='00040105'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,460자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
143 | 541
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.6s

**answer**

```text
한국투자신탁운용이 운용하는 공모펀드는 143개(클래스 541개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
운용사 코드 2건(00040024·00040105)을 합산했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '한국 투자 신탁 운용' → Org_00040024 (Organization, 정식명 한국투자신탁운용) → public_funds.or_co_xtn_itt_cd='00040024' · public_funds.or_co_xtn_itt_cd='00040105'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,460자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00040024', '00040105') AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
143 | 541
```

</details>

---

## KG-005. 이름이 삼성으로 시작하는 공모펀드는 몇 개고, 그중 삼성자산운용이 운용하는 건 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 47.0s · ❌ — ext INNER JOIN + mgmt_co_nm 집계로 클래스 868/811 산출(ext 미수록 38행 탈락), 펀드단위 가드 미발동, HCX 가 '811개/811개' 전사 · 삼성액티브 분리 없음 (gold 217=207+10) [플래너 → SQL가드 → HCX]

**answer**

```text
이름이 삼성으로 시작하는 공모펀드는 총 811개이며, 그중 삼성자산운용이 운용하는 펀드는 811개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 49
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '삼성자산운용' → Org_00040010 (Organization) → public_funds.or_co_xtn_itt_cd='00040010'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,340자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(*) as cnt_all, SUM(CASE WHEN e.mgmt_co_nm LIKE '삼성자산운용%' THEN 1 ELSE 0 END) as cnt_samsung FROM public_funds p JOIN ext_fund_page e ON e.itm_no = p.itm_no WHERE p.sale_yn = '판매중' AND p.prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '삼성%' LIMIT 30
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
cnt_all | cnt_samsung
868 | 811
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.3s · 🟡 — 217/906 정확(1문) 이나 2문(삼성자산운용 207/850·삼성액티브 10/56) 통째로 누락: HCX 가 접두 COUNT 1개만 내고 기계 조립기가 1행 완결 처리 [개선 ❌→🟡 · 플래너(2집계→1)→조립]

**answer**

```text
조회 조건에 해당하는 공모펀드는 217개(클래스 906개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 49
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '삼성자산운용' → Org_00040010 (Organization) → public_funds.or_co_xtn_itt_cd='00040010'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,446자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' and sale_yn = '판매중' and REPLACE(itm_nm,' ','') LIKE '삼성%' LIMIT 5
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
217 | 906
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.6s

**answer**

```text
조회 조건에 해당하는 공모펀드는 352개(클래스 1,179개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 49
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '삼성자산운용' → Org_00040010 (Organization) → public_funds.or_co_xtn_itt_cd='00040010'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,446자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND (sale_yn = '판매중' OR sale_yn = '판매완료') AND (REPLACE(itm_nm,' ','') LIKE '삼성%' OR itm_abrv_nm LIKE '%삼성%') LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
352 | 1179
```

</details>

---

## KG-006. 미래에셋코어테크 펀드의 운용사와 수탁사는 어디야?

### 기준선(31e72ef) — HTTP 200 · 5.4s · ❌ 오거절 — mtco_nm·trusc_nm 환각 → 재생성도 실패. 수탁사 코드→이름이 KG 노드에만 있고 DB 테이블 없음 (gold 미래에셋자산운용/신한은행 00020088) [온톨로지(역할·이름 부재) → 플래너]

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 27
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 10,700자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT mtco_nm, trusc_nm, itm_no, TRIM(itm_nm) AS itm_nm FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 30)
11. [Guard] SQL 기각 — 스키마에 없는 컬럼: mtco_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: mgmt_co_nm, mtco_itm_no — 뜻이 같다는 보장은 없다), trusc_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_rwrd_r — 뜻이 같다는 보장은 없다)
12. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.4s)
13. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
14. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
15. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT mgmt_co_nm as 운용사, trusc_xtn_itt_cd as 수탁사, itm_no, TRIM(itm_nm) AS itm_nm FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE or_co_xtn_itt_cd IN ('00080008') AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 30)
16. [Guard] 재생성 후에도 실패 — 한정되지 않은 모호 컬럼: itm_no
17. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 2라운드(6bad723) — HTTP 200 · 56.8s · ❌ 오거절 유지 — S2 미착수. 재생성 SQL(mgmt_co_nm+trusc 코드)은 실행 가능했는데 ambiguous_columns 가 서브쿼리 스코프의 itm_no 를 모호로 오판해 기각 [온톨로지(S2)+가드(모호 검사 과잉 N8)]

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 27
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 10,806자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
10. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT mtco_nm AS 운용사, trusc_nm AS 수탁사, itm_no, TRIM(itm_nm) AS itm_nm FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모') LIMIT 30
12. [Guard] SQL 기각 — 스키마에 없는 컬럼: mtco_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: mgmt_co_nm, mtco_itm_no — 뜻이 같다는 보장은 없다), trusc_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_rwrd_r — 뜻이 같다는 보장은 없다)
13. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.9s)
14. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT mgmt_co_nm AS 운용사, trusc_xtn_itt_cd AS 수탁사, itm_no, TRIM(itm_nm) AS itm_nm FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE or_co_xtn_itt_cd = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모') LIMIT 30
15. [Guard] 재생성 후에도 실패 — 여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): itm_no — 테이블 별칭을 붙이고 p.itm_no 처럼 모두 한정한다
16. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 3라운드(1e0e641) — HTTP 200 · 6.6s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 27
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 10,806자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
10. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT mtco_nm AS 운용사, trusc_nm AS 수탁사, itm_no, TRIM(itm_nm) AS itm_nm FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모') LIMIT 30
12. [Guard] SQL 기각 — 스키마에 없는 컬럼: mtco_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: mgmt_co_nm, mtco_itm_no — 뜻이 같다는 보장은 없다), trusc_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_rwrd_r — 뜻이 같다는 보장은 없다)
13. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.9s)
14. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT mgmt_co_nm AS 운용사, trusc_xtn_itt_cd AS 수탁사, itm_no, TRIM(itm_nm) AS itm_nm FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE or_co_xtn_itt_cd = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모') LIMIT 30
15. [Guard] 재생성 후에도 실패 — 여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): itm_no — 테이블 별칭을 붙이고 p.itm_no 처럼 모두 한정한다
16. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-007. 미래에셋자산운용에 의해 운용되는 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.4s · ✅ 823/2,066 — '운용되는' 트리거 없이도 KG 매핑으로 수렴 (inverseOf 는 여전히 문서 장식)

**answer**

```text
미래에셋자산운용이 운용하는 공모펀드는 823개(클래스 2,066개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋자산운용' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,342자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
823 | 2066
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.4s · ✅ 유지 823/2,066 (+역외 5 병기)

**answer**

```text
미래에셋자산운용이 운용하는 공모펀드는 823개(클래스 2,066개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
종목명이 '미래에셋' 로 시작하는 역외펀드 5개(클래스 5개, 해외 운용법인 코드 00130006)는 별도 법인이라 이 수에 포함하지 않았습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋자산운용' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
823 | 2066
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.7s

**answer**

```text
미래에셋자산운용이 운용하는 공모펀드는 823개(클래스 2,066개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
종목명이 '미래에셋' 로 시작하는 역외펀드 5개(클래스 5개, 해외 운용법인 코드 00130006)는 별도 법인이라 이 수에 포함하지 않았습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋자산운용' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
823 | 2066
```

</details>

---

## KG-008. 공모펀드를 가장 많이 수탁하는 수탁사 상위 3개 알려줘

### 기준선(31e72ef) — HTTP 200 · 4.8s · ❌ 오거절 — trusc_itt_nm 환각 2회 → 거절. 수탁사 이름 컬럼 부재 (gold HSBC 714 · 국민 516 · 씨티 465) [온톨로지 → 플래너]

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,601자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT trusc_xtn_itt_cd, trusc_itt_nm, itm_no, TRIM(itm_nm) AS itm_nm FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모') GROUP BY trusc_xtn_itt_cd ORDER BY SUM(zrin_fd_cmst_rt) DESC LIMIT 3
9. [Guard] SQL 기각 — 스키마에 없는 컬럼: trusc_itt_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_xtn_itt_cd, mtco_itm_no — 뜻이 같다는 보장은 없다)
10. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.2s)
11. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT trusc_xtn_itt_cd, trusc_itt_nm, COUNT(*) as cnt FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY trusc_xtn_itt_cd ORDER BY cnt DESC LIMIT 3
12. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: trusc_itt_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_xtn_itt_cd, mtco_itm_no — 뜻이 같다는 보장은 없다)
13. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 2라운드(6bad723) — HTTP 200 · 5.7s · ❌ 오거절 유지 — trusc_itt_nm_ko 환각 2회. 수탁사 이름이 SQL 층에 없음 [S2]

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,707자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT trusc_xtn_itt_cd, trusc_itt_nm_ko, SUM(fd_nast_suma) as fund_suma, itm_no, TRIM(itm_nm) AS itm_nm, CAST(ROUND(SUM(fd_nast_suma)/100000000.0) AS INTEGER) || '억원' AS "순자산합계_억원" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모') GROUP BY trusc_xtn_itt_cd ORDER BY 3 DESC LIMIT 3
9. [Guard] SQL 기각 — 스키마에 없는 컬럼: trusc_itt_nm_ko(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_xtn_itt_cd, mtco_itm_no — 뜻이 같다는 보장은 없다)
10. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.4s)
11. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
12. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT trusc_xtn_itt_cd, trusc_itt_nm_ko, SUM(fd_nast_suma) as fund_suma, itm_no, TRIM(itm_nm) AS itm_nm, CAST(ROUND(SUM(fd_nast_suma)/100000000.0) AS INTEGER) || '억원' AS "순자산합계_억원" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY trusc_xtn_itt_cd ORDER BY 3 DESC LIMIT 3
13. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: trusc_itt_nm_ko(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_xtn_itt_cd, mtco_itm_no — 뜻이 같다는 보장은 없다)
14. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 3라운드(1e0e641) — HTTP 200 · 46.7s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,707자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT trusc_xtn_itt_cd, trusc_itt_nm, SUM(fd_nast_suma) as fund_sum, itm_no, TRIM(itm_nm) AS itm_nm, CAST(ROUND((SUM(fd_nast_suma))/100000000.0) AS INTEGER) || '억원' AS "fund_sum_억원" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모') GROUP BY trusc_xtn_itt_cd ORDER BY 3 DESC LIMIT 3
9. [Guard] SQL 기각 — 스키마에 없는 컬럼: trusc_itt_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_xtn_itt_cd, mtco_itm_no — 뜻이 같다는 보장은 없다)
10. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.3s)
11. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
12. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT trusc_xtn_itt_cd, trusc_itt_nm, SUM(fd_nast_suma) as fund_sum, itm_no, TRIM(itm_nm) AS itm_nm, CAST(ROUND((SUM(fd_nast_suma))/100000000.0) AS INTEGER) || '억원' AS "fund_sum_억원" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY trusc_xtn_itt_cd, trusc_itt_nm ORDER BY 3 DESC LIMIT 3
13. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: trusc_itt_nm(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: trusc_xtn_itt_cd, mtco_itm_no — 뜻이 같다는 보장은 없다)
14. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-009. 미래에셋증권이 수탁사인 공모펀드도 있어?

### 기준선(31e72ef) — HTTP 200 · 48.1s · ❌ — SQL·행은 정확(2펀드/14클래스) 인데 HCX 가 '없습니다 … 다른 기관이 수탁' 으로 반전 서술 [조립(HCX)]

**answer**

```text
제공된 데이터에 따르면 미래에셋증권이 수탁사로 되어있는 공모펀드는 없습니다. 대신 사모투자재간접형 펀드 2개가 검색되었습니다. 이 펀드들은 미래에셋증권이 아닌 다른 금융기관이 수탁사로 지정되어 있습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋증권' → Org_trustee_0016022 (Organization) → public_funds.trusc_xtn_itt_cd='0016022'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,767자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", trusc_xtn_itt_cd FROM public_funds WHERE TRIM(trusc_xtn_itt_cd) = '0016022' AND prvo_pbff_desc = '공모' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 2행 조회 (상한 30)
13. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | 순자산_억원 | trusc_xtn_itt_cd
KR5181490230 | iM에셋 타이거 포커스 증권투자신탁(사모투자재간접형) A | 6 | 145648915928.0 | 1456억원 | 0016022
KR512F490004 | 머스트원앤온리증권자투자신탁(사모투자재간접형) 종류 A | 8 | 96890608358.0 | 968억원 | 0016022
```

</details>

### 2라운드(6bad723) — HTTP 200 · 3.1s · ✅ — 전체 2개(14클래스) iM에셋 타이거 포커스 1,456억·6 / 머스트원앤온리 968억·8. 목록 기계 조립로 반전 서술 소멸 [개선 ❌→✅]

**answer**

```text
조건에 해당하는 공모펀드는 전체 2개(클래스 14개)이며, 순자산 순으로 다음과 같습니다 (기준일 2026-08-22).

1. iM에셋 타이거 포커스 증권투자신탁(사모투자재간접형): 순자산 1,456억원 · 클래스 6개
2. 머스트원앤온리증권자투자신탁(사모투자재간접형): 순자산 968억원 · 클래스 8개
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋증권' → Org_trustee_0016022 (Organization) → public_funds.trusc_xtn_itt_cd='0016022'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,873자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", trusc_xtn_itt_cd FROM public_funds WHERE TRIM(trusc_xtn_itt_cd) = '0016022' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 2행 조회 (상한 30)
12. [Answer] 목록 답변 기계 조립 — 순자산순 펀드 목록 전 행 + 총량 머리줄 (2026-09-02 R3·S7: 30행 중 5·10행만 옮김 · S6: 총량 대신 '더 있을 수 있음')
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | 순자산_억원 | trusc_xtn_itt_cd
KR5181490230 | iM에셋 타이거 포커스 증권투자신탁(사모투자재간접형) A | 6 | 145648915928.0 | 1456억원 | 0016022
KR512F490004 | 머스트원앤온리증권자투자신탁(사모투자재간접형) 종류 A | 8 | 96890608358.0 | 968억원 | 0016022
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.6s

**answer**

```text
조건에 해당하는 공모펀드는 전체 2개(클래스 14개)이며, 순자산 순으로 다음과 같습니다 (기준일 2026-08-22, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위·순자산 = 대표 클래스 기준(MAX)).

1. iM에셋 타이거 포커스 증권투자신탁(사모투자재간접형): 순자산 1,456억원 · 클래스 6개
2. 머스트원앤온리증권자투자신탁(사모투자재간접형): 순자산 968억원 · 클래스 8개
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋증권' → Org_trustee_0016022 (Organization) → public_funds.trusc_xtn_itt_cd='0016022'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,873자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, trusc_xtn_itt_cd, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE TRIM(trusc_xtn_itt_cd) = '0016022' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 2행 조회 (상한 30)
12. [Answer] 목록 답변 기계 조립 — 순자산순 펀드 목록 전 행 + 총량 머리줄 (2026-09-02 R3·S7: 30행 중 5·10행만 옮김 · S6: 총량 대신 '더 있을 수 있음')
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | trusc_xtn_itt_cd | 순자산_억원
KR5181490230 | iM에셋 타이거 포커스 증권투자신탁(사모투자재간접형) A | 6 | 145648915928.0 | 0016022 | 1456억원
KR512F490004 | 머스트원앤온리증권자투자신탁(사모투자재간접형) 종류 A | 8 | 96890608358.0 | 0016022 | 968억원
```

</details>

---

## KG-010. 미래에셋코어테크 펀드의 모펀드는 뭐야?

### 기준선(31e72ef) — HTTP 200 · 4.9s · ❌ — '코어테크' 부분일치가 형제 6펀드 혼입 → HCX 가 글로벌코어테크EMP·차이나코어테크 모펀드를 답하고 정답 미래에셋코어테크증권모투자신탁(주식) 누락, '재간접' 노출 [SQL가드(상품명 필터) → 조립]

**answer**

```text
미래에셋코어테크 펀드의 모펀드는 미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형), 미래에셋차이나코어테크증권모투자신탁(주식)입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
7. [Plan] 근거문서 조립 — 대상 public_funds · 12,397자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
8. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT mother_fund_names_raw FROM public_funds JOIN ext_fund_page ON public_funds.itm_no = ext_fund_page.itm_no WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 30행 조회 (상한 30)
13. [Answer] 커버리지 병기 — LIMIT 도달, 전체 41행 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
mother_fund_names_raw
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
```

</details>

### 2라운드(6bad723) — HTTP 200 · 6.6s · ❌ 유지 — 조회 30행에 정답 '미래에셋코어테크증권모투자신탁(주식)' 10회 실렸는데 HCX 가 형제 모펀드 2개를 답하고 '재간접형' 노출. 부분일치 41행(S8/R15 미착수) [가드→조립]

**answer**

```text
미래에셋코어테크 펀드의 모펀드는 미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형), 미래에셋차이나코어테크증권모투자신탁(주식)입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
7. [Plan] 근거문서 조립 — 대상 public_funds · 12,503자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
8. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT mother_fund_names_raw FROM public_funds JOIN ext_fund_page ON public_funds.itm_no = ext_fund_page.itm_no WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 30행 조회 (상한 30)
13. [Answer] 커버리지 병기 — LIMIT 도달, 전체 41행 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
mother_fund_names_raw
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
미래에셋코어테크증권모투자신탁(주식)
미래에셋글로벌코어테크EMP증권모투자신탁(주식-재간접형)
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 5.0s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
7. [Plan] 근거문서 조립 — 대상 public_funds · 12,503자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
8. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT mother_fund_names_raw, itm_no, TRIM(itm_nm) AS itm_nm FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 30)
12. [Guard] SQL 기각 — 여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): itm_no — 테이블 별칭을 붙이고 p.itm_no 처럼 모두 한정한다
13. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.4s)
14. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
15. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
16. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT DISTINCT mother_fund_names_raw, itm_no, TRIM(itm_nm) AS itm_nm FROM ext_fund_page WHERE itm_no IN (SELECT itm_no FROM public_funds WHERE or_co_xtn_itt_cd = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 30)
17. [Guard] 재생성 후에도 실패 — 여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): itm_no — 테이블 별칭을 붙이고 p.itm_no 처럼 모두 한정한다
18. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-011. KB자산운용 펀드 중 국민은행이 수탁하는 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.9s · 🟡 — 값 0 정확(두 조건 반영) 이나 머리말 'KB자산운용이 운용하는 공모펀드는 0개' 로 수탁 조건 탈락(거짓 문장) · 국민은행 제2코드·실제 수탁 분포 미병기 [조립]

**answer**

```text
KB자산운용이 운용하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 34
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035' / '국민은행' → Org_trustee_00020004 (Organization) → public_funds.trusc_xtn_itt_cd='00020004'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,410자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' AND TRIM(trusc_xtn_itt_cd) = '00020004' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

### 2라운드(6bad723) — HTTP 200 · 41.8s · ✅ — 'KB자산운용이 운용하고 국민은행이 수탁하는 … 0개(각 조건의 개체·값은 실재하며 교집합 0)' — R1(a) 단언 적절. 이웃 분포 미병기(가점) [개선 🟡→✅]

**answer**

```text
KB자산운용이 운용하고 국민은행이 수탁하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
(각 조건의 개체·값은 데이터에 실재하며 그 교집합이 0입니다)
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 34
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035' / '국민은행' → Org_trustee_00020004 (Organization) → public_funds.trusc_xtn_itt_cd='00020004'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,516자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' AND TRIM(trusc_xtn_itt_cd) = '00020004' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.7s

**answer**

```text
KB자산운용이 운용하고 국민은행이 수탁하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
(각 조건의 개체·값은 데이터에 실재하며 그 교집합이 0입니다)
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 34
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035' / '국민은행' → Org_trustee_00020004 (Organization) → public_funds.trusc_xtn_itt_cd='00020004'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,516자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040035' AND TRIM(trusc_xtn_itt_cd) = '00020004' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

---

## KG-012. 해외주식형 중에서 중국주식 유형인 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.5s · ❌ 거짓 0개 — yaml 템플릿 <코드> 를 '<CHN>' 리터럴로 복사 + '중국주식 유형' 을 국가 태그로 오해 → 실재 205/522 를 '0개' 단언 [플래너 → SQL가드(템플릿 잔재 미검사) → 조립]

**answer**

```text
조회 조건에 해당하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['해외주식형']
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,565자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND zrin_btyp_nm = '해외주식형' AND ',' || prfd_attr_cds || ',' LIKE '%,<CHN>,%' AND sale_yn = '판매중' LIMIT 30
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.9s · 🟡 — 205/522 정확(precheck 템플릿 잔재 + R10 '유형'→zrin_ptn_nm) 이나 유형 기준 고지·'중국주식' 토큰 없음(gold must) [개선 ❌→🟡 · 조립 R8]

**answer**

```text
조회 조건에 해당하는 공모펀드는 205개(클래스 522개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['해외주식형']
3. [Ground] KG 개체 매핑 — '중국' → Country_CHN (Country) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,CHN,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,869자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 국가어 질의의 지역·설립국·태그·속성명·이름 OR 절을 KG Country 토큰 canon 하나로 접음 (KG 1R S3·3R C: 어떤 태그를 썼든 교정 · '유형' 이면 zrin_ptn_nm) · 전: WHERE prvo_pbff_desc = '공모' AND zrin_btyp_nm IN ('주식형','해외주식형') AND ',' || prfd_attr_cds || ',' LIKE '%,CHN,%' AND sale_
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND zrin_btyp_nm IN ('주식형','해외주식형') AND zrin_ptn_nm = '중국주식' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
205 | 522
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.7s

**answer**

```text
조회 조건에 해당하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
(각 조건의 개체·값은 데이터에 실재하며 그 교집합이 0입니다)
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['해외주식형']
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,671자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND zrin_btyp_nm = '해외주식형' AND fd_ivst_rgn_desc LIKE '%중국%' AND sale_yn = '판매중' LIMIT 30
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

---

## KG-013. 위험등급 7등급인 공모펀드 알려줘

### 기준선(31e72ef) — HTTP 200 · 0.2s · 🟡 — 게이트 즉답 ✓ 이나 '0~6 범위' 문구(펀드는 1~6, 0 은 채권 미분류 코드) · must '1' 미충족 [게이트 상수/온톨로지 riskGradeValue 과대허용]

**answer**

```text
위험등급은 0~6 범위로 정의되어 있습니다. 7등급은 존재하지 않습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 기각 — 위험등급 7 는 정의 범위(0~6)를 벗어남
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 2라운드(6bad723) — HTTP 200 · 0.2s · ✅ — 게이트 즉답 '1(매우 높은 위험)~6(매우 낮은 위험), 7등급 없음, 0등급 없음·미수록 NULL' — S6 range_by_table [개선 🟡→✅]

**answer**

```text
공모펀드 위험등급은 1(매우 높은 위험)~6(매우 낮은 위험) 범위로 정의되어 있어 7등급은 없습니다. (0등급 없음 — 등급 미수록 클래스는 NULL(0 아님))
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 기각 — 위험등급 7 는 정의 범위(1~6, 테이블별 선언 range_by_table)를 벗어남
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 3라운드(1e0e641) — HTTP 200 · 0.2s

**answer**

```text
공모펀드 위험등급은 1(매우 높은 위험)~6(매우 낮은 위험) 범위로 정의되어 있어 7등급은 없습니다. (0등급 없음 — 등급 미수록 클래스는 NULL(0 아님))
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 기각 — 위험등급 7 는 정의 범위(1~6, 테이블별 선언 range_by_table)를 벗어남
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-014. 위험등급 0등급 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.2s · 🟡 — 게이트 미발동(0 허용) → SQL 0/0 → '0개' 단언. NULL 422 를 0 으로 읽진 않았으나 '펀드는 1~6, 0등급 없음' 설명 없음 [게이트 → 조립]

**answer**

```text
조회 조건에 해당하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,295자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_gcd = 0) LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

### 2라운드(6bad723) — HTTP 200 · 0.3s · ✅ — 게이트 기각(0 정의역 밖) HCX 0회, 'NULL≠0' 설명 [개선 🟡→✅]

**answer**

```text
공모펀드 위험등급은 1(매우 높은 위험)~6(매우 낮은 위험) 범위로 정의되어 있어 0등급은 없습니다. (0등급 없음 — 등급 미수록 클래스는 NULL(0 아님))
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 기각 — 위험등급 0 는 정의 범위(1~6, 테이블별 선언 range_by_table)를 벗어남
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 3라운드(1e0e641) — HTTP 200 · 0.3s

**answer**

```text
공모펀드 위험등급은 1(매우 높은 위험)~6(매우 낮은 위험) 범위로 정의되어 있어 0등급은 없습니다. (0등급 없음 — 등급 미수록 클래스는 NULL(0 아님))
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 기각 — 위험등급 0 는 정의 범위(1~6, 테이블별 선언 range_by_table)를 벗어남
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-015. 위험등급이 '높은위험'인 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.2s · ❌ — RiskGrade_2 에 '높은위험' alias 가 있으나 Ground 는 label 만 키로 써 미매칭 → HCX 정확일치 4/20 (gold 995/2,994) [KG 개체(alias 미승격) → 가드]

**answer**

```text
조회 조건에 해당하는 공모펀드는 4개(클래스 20개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['높은위험']
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,601자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_grd_nm = '높은위험') LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
4 | 20
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.3s · ✅ 995/2,994 — RiskGrade 이름형 alias raw 승격 → IN('높은위험','높은 위험') [개선 ❌→✅]

**answer**

```text
조회 조건에 해당하는 공모펀드는 995개(클래스 2,994개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['높은위험']
3. [Ground] KG 개체 매핑 — '높은위험' → RiskGrade_2 (RiskGrade) → public_funds.zrin_fd_ivst_risk_gcd='2.0' · public_funds.zrin_fd_ivst_risk_grd_nm='높은 위험' · public_funds.zrin_fd_ivst_risk_grd_nm='높은위험'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,945자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_grd_nm IN ('높은위험', '높은 위험')) LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
995 | 2994
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.2s

**answer**

```text
조회 조건에 해당하는 공모펀드는 995개(클래스 2,994개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['높은위험']
3. [Ground] KG 개체 매핑 — '높은위험' → RiskGrade_2 (RiskGrade) → public_funds.zrin_fd_ivst_risk_gcd='2.0' · public_funds.zrin_fd_ivst_risk_grd_nm='높은 위험' · public_funds.zrin_fd_ivst_risk_grd_nm='높은위험'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,945자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모' AND zrin_fd_ivst_risk_grd_nm IN ('높은위험', '높은 위험')) LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
995 | 2994
```

</details>

---

## KG-016. 채권혼합 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 42.8s · 🟡 — 389/933 정확(약관 or_attr_desc) 이나 기준 미고지·제로인 240/534 미병기 → 부분 (Q8 로 해소 예상) [조립]

**answer**

```text
조회 조건에 해당하는 공모펀드는 389개(클래스 933개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 16
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['채권혼합']
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,295자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND or_attr_desc = '채권혼합' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
389 | 933
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.1s · 🟡 유지 — 389/933(약관) 정확, 기준 미고지·제로인 240/534 미병기 [조립 R8]

**answer**

```text
조회 조건에 해당하는 공모펀드는 389개(클래스 933개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 16
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['채권혼합']
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,401자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND or_attr_desc = '채권혼합' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
389 | 933
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 63.6s

**answer**

```text
조회 조건에 해당하는 공모펀드는 389개(클래스 933개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 16
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['채권혼합']
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,401자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND or_attr_desc = '채권혼합' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
389 | 933
```

</details>

---

## KG-017. 폐쇄형 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 3.2s · ❌ 거짓 0개 — yaml '폐쇄 태그 미확인' 오서술이 실려 han_clas_policies LIKE '%폐쇄형%' 오선택 → 실재 3/6(C104) 을 '0개' 단언 [온톨로지 규칙(yaml) → 플래너 → 조립]

**answer**

```text
조회 조건에 해당하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 15
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,295자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND han_clas_policies LIKE '%폐쇄형%' LIMIT 30
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.2s · ✅ 3/6 — FundAttr_C104 token + R11 확정식(han_clas_policies 절 제거). 태그 미보유 418행 병기 없음(가점) [개선 ❌→✅]

**answer**

```text
조회 조건에 해당하는 공모펀드는 3개(클래스 6개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 15
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['폐쇄형']
3. [Ground] KG 개체 매핑 — '폐쇄형' → FundAttr_C104 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,C104,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,607자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prfd_attr_cds LIKE '%C104%' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND ',' || prfd_attr_cds || ',' LIKE '%,C104,%' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
3 | 6
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.4s

**answer**

```text
조회 조건에 해당하는 공모펀드는 3개(클래스 6개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 15
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드 · 값 ['폐쇄형']
3. [Ground] KG 개체 매핑 — '폐쇄형' → FundAttr_C104 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,C104,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,607자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,C104,%' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
3 | 6
```

</details>

---

## KG-018. 단위형이면서 개방형인 공모펀드도 있어?

### 기준선(31e72ef) — HTTP 200 · 6.5s · ❌ — 조건을 버리고 zrin_btyp_nm 목록 조회 → '찾을 수 없다' + '단위형=설정액 규모 조건' 도메인 날조 (gold 31/189) [플래너 → 조립(HCX 환각)]

**answer**

```text
제공된 데이터에서는 단위형이면서 개방형인 공모펀드에 대한 정보를 찾을 수 없습니다. 따라서 이에 대해 답변을 드릴 수 없습니다. 하지만, 일반적으로 공모펀드는 개방형으로 운영될 수 있으며, 이는 투자자들이 펀드에 자유롭게 가입하거나 탈퇴할 수 있다는 것을 의미합니다. 단위형은 펀드의 설정액이 일정 규모 이상이 되어야 하며, 이를 충족하지 못할 경우 펀드가 해지될 수 있습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,295자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT zrin_btyp_nm, itm_no, TRIM(itm_nm) AS itm_nm FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND zrin_btyp_nm IS NOT NULL LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 30행 조회 (상한 30)
11. [Answer] 커버리지 병기 — LIMIT 도달, 전체 8,551행 / 2,908펀드 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)
12. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
zrin_btyp_nm | itm_no | itm_nm
외화 MMF | KR5018410041 | 우리다같이국공채법인달러MMF1호(USD)ClassC-e
MMF | KR5062101401 | Plus 신종 법인용 MMF1호 종류C
해외주식형 | KR510102009M | 미래에셋인디아솔로몬증권투자신탁1호(주식)(C-I)
해외주식형 | KR510502099M | 삼성중국본토중소형FOCUS증권자투자신탁UH(주식)Ce
해외주식형 | KR510509003M | 삼성누버거버먼차이나증권자투자신탁H(주식-재간접형)A
해외주식형 | KR510902594M | 미래에셋인디아인프라섹터증권자투자신탁1호(주식)C4
해외주식형 | KR510902681M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C2
해외주식형 | KR510902684M | 미래에셋차이나솔로몬증권투자신탁2호(주식)C5
해외주식형 | KR510902914M | 미래에셋인도중소형포커스증권자투자신탁(주식)A-e
주식혼합형 | KR510903125M | 미래에셋배당과롱숏증권자투자신탁(주식혼합)C-Pe
해외채권혼합형 | KR510904073M | 미래에셋 글로벌인컴 증권자투자신탁1호(채권혼합)A-e
채권혼합형 | KR510904123M | 미래에셋개인연금코어밸류20증권전환형자투자신탁1호(채권혼합)
해외채권혼합형 | KR510906162M | 미래에셋글로벌배당과인컴증권자투자신탁1호(채권혼합)C
해외주식형 | KR510909231M | 미래에셋다이와연금넥스트AP증권자투자신탁(주식)C-P
해외주식형 | KR5110450037 | 미래에셋삼바브라질포커스증권자투자신탁 [주식]종류C1d
주식형 | KR5110450211 | 미래에셋코리아인덱스소득공제 증권자투자신탁[주식]C
주식형 | KR511102054M | 한국투자테크증권자투자신탁2호(주식)C3
주식형 | KR511102056M | 한국투자테크증권자투자신탁2호(주식)C5
해외주식형 | KR511102070M | 한국투자글로벌브랜드파워증권자투자신탁2호(주식)A
채권혼합형 | KR511104010M | 한국투자재형한국의힘증권자투자신탁(채권혼합)
해외부동산형 | KR5111490002 | 하나글로벌리츠부동산자투자신탁[재간접형]종류A-E
주식형 | KR5111601008 | 하나그레이터코리아증권자투자신탁[주식] C5
해외채권혼합형 | KR5113430101 | 한국투자미국배당귀족증권자투자신탁(채권혼합)(C-Re)
주식형 | KR5113450070 | 한국투자삼성그룹증권자투자신탁 1(주식)(A)
해외주식형 | KR5113450131 | 한국투자골드플랜차이나연금증권전환형자투자신탁 1호(주식) C
해외주식형 | KR5113450195 | 한국투자베트남그로스증권자투자신탁(주식) 종류Ae
채권형 | KR5118420005 | 우리나라초단기채권증권투자신탁[채권]ClassC-P
해외주식형 | KR5113450261 | 한국투자웰링턴글로벌퀄리티증권자투자신탁UH(주식) 종류 C
해외주식형 | KR5113450264 | 한국투자웰링턴글로벌퀄리티증권자투자신탁UH(주식) 종류 C4
해외주식형 | KR5113450280 | 한국투자글로벌전기차&자율주행증권투자신탁(주식) 종류 A
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.3s · ❌ — canon C102∧C103 주입됐으나 HCX 의 itm_abrv_nm LIKE '%단위%'/'%개방%' 절을 못 걷어냄(통칭 낱말 기준) + sale_yn 미주입 → 0행 → '조건 중 일부는 상품 자체가 없다' 거짓 유보(실재 31/189). 도메인 날조는 소멸 [형태 변화 날조→거짓 유보 · 가드(N5)+R1(c) 오진]

**answer**

```text
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 조건 중 일부는 수록된 데이터에 해당하는 상품 자체가 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,401자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND (itm_abrv_nm LIKE '%단위%' AND itm_abrv_nm LIKE '%개방%') AND ',' || prfd_attr_cds || ',' LIKE '%,C102,%' AND ',' || prfd_attr_cds || ',' LIKE '%,C103,%' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 0행 조회 (상한 30)
12. [Diagnose] 0행 원인 — 조건별 단독 조회: prvo_pbff_desc = '공모' → 14,716건 / (itm_abrv_nm LIKE '%단위%' AND itm_abrv_nm LIKE '%개방%') → 0건 / ',' || prfd_attr_cds || ',' LIKE '%,C102,%' → 622건 / ',' || prfd_attr_cds || ',' LIKE '%,C103,%' → 11,085건. 값 자체가 없는 조건: (itm_abrv_nm LIKE '%단위%' AND itm_abrv_nm LIKE '%개방%').
13. [Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | 순자산_억원 | prfd_attr_cds

```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.3s

**answer**

```text
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 조건 중 일부는 수록된 데이터에 해당하는 상품 자체가 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,401자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, prfd_attr_cds, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE prvo_pbff_desc = '공모' AND (itm_abrv_nm LIKE '%단위%' AND itm_abrv_nm LIKE '%개방%') AND ',' || prfd_attr_cds || ',' LIKE '%,C102,%' AND ',' || prfd_attr_cds || ',' LIKE '%,C103,%' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 0행 조회 (상한 30)
12. [Diagnose] 0행 원인 — 조건별 단독 조회: prvo_pbff_desc = '공모' → 14,716건 / (itm_abrv_nm LIKE '%단위%' AND itm_abrv_nm LIKE '%개방%') → 0건 / ',' || prfd_attr_cds || ',' LIKE '%,C102,%' → 622건 / ',' || prfd_attr_cds || ',' LIKE '%,C103,%' → 11,085건. 값 자체가 없는 조건: (itm_abrv_nm LIKE '%단위%' AND itm_abrv_nm LIKE '%개방%').
13. [Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | prfd_attr_cds | 순자산_억원

```

</details>

---

## KG-019. 일본에 투자하는 공모펀드 알려줘

### 기준선(31e72ef) — HTTP 200 · 9.7s · 🟡 — SQL 정확(38/103, JPN ∪ 이름) 이나 30행 중 8행만 나열·'일부입니다'·피델리티재팬 누락 (Q5 로 해소 예상) [조립]

**answer**

```text
조회 결과에 따르면, 일본에 투자하는 공모펀드는 다음과 같습니다.

1. 슈로더일본주식펀드(OS557302004M)
2. 일본오퍼튜니티펀드(OS5501602003)
3. 일본 중소형주 펀드-A(OS5502601001)
4. 피델리티펀드일본펀드(OS555085006M)
5. 피델리티펀드일본중소형주펀드(OS555085007M)
6. 우리재팬증권자투자신탁(E)(주식)(KR5134651002)
7. 하나재팬코어플러스증권투자신탁[주식]C(KR512302011M)
8. 우리재팬증권자투자신탁(주식)ClassA(KR5134651001)

이 외에도 다양한 일본 투자 공모펀드들이 있으며, 위 리스트는 그 중 일부입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,731자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
7. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND (prfd_attr_cds LIKE '%JPN%' OR REPLACE(itm_nm,' ','') LIKE '%일본%') AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 30행 조회 (상한 30)
12. [Answer] 내부 코드 컬럼 숨김 — prfd_attr_cds (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)
13. [Answer] 커버리지 병기 — LIMIT 도달, 전체 103행 / 38펀드 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)
14. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
15. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | prfd_attr_cds
OS557302004M | 슈로더일본주식펀드 | 1 | 1 | 
OS5501602003 | 일본오퍼튜니티펀드 | 1 | 1 | 
OS5502601001 | 일본 중소형주 펀드-A | 1 | 1 | 
OS555085006M | 피델리티펀드일본펀드 | 1 | 1 | 
OS555085007M | 피델리티펀드일본중소형주펀드 | 1 | 1 | 
KR5134651002 | 우리재팬증권자투자신탁(E)(주식) | 1 | 1 | V102,N109,JPN,C103,G118,D102,M109,C101
KR512302011M | 하나재팬코어플러스증권투자신탁[주식]C | 1 | 1 | M111,V102,P101,C101,G118,C103,JPN,D102
KR5134651001 | 우리재팬증권자투자신탁(주식)ClassA | 1 | 1 | M109,W111,C101,G118,C103,D102,N109,JPN,M111,V102
KR5129450050 | 한화재팬코아증권투자신탁1호(주식) 종류A | 2 | 2 | N109,JPN,M111,V102,C101,C103,G118,D102
KR5134450078 | 우리연금재팬증권자투자신탁(주식)ClassC | 2 | 2 | F103,M111,V102,C103,D102,M109,G110,JPN,C101,W111
KR512002067M | 우리재팬증권자투자신탁(주식)ClassA-e | 1 | 1 | W111,C101,JPN,M109,D102,C103,G118,N109,D106,V102,M111
KR512002074M | 우리재팬증권자투자신탁(주식)ClassC-F | 1 | 1 | C101,W111,M109,D102,JPN,C103,G118,N109,V102,M111
KR5148450038 | 피델리티재팬증권자투자신탁(주식-재간접)종류A | 10 | 10 | N109,M111,JPN,V102,M109,D105,C101,M112,W111,G118,C103,D102
KR512002065M | 우리연금재팬증권자투자신탁(주식)ClassC-e | 1 | 1 | G110,M109,C101,W111,C103,D102,F103,M111,JPN,V102,D106
KR5134651003 | 우리재팬증권자투자신탁(UH)(주식)ClassA | 1 | 1 | N109,V102,M111,C101,M109,JPN,D102,G118,C103
KR515009096M | 피델리티재팬증권자투자신탁(주식-재간접형)A-e | 1 | 1 | D106,V102,M111,N109,D102,JPN,C103,G118,C101,W111,M112,M109
KR515009097M | 피델리티재팬증권자투자신탁(주식-재간접형)C-e | 1 | 1 | N109,JPN,M111,D106,V102,M109,W111,M112,C101,C103,G118,D102
KR515009098M | 피델리티재팬증권자투자신탁(주식-재간접형)PRS | 1 | 1 | C103,G118,D102,G110,M109,C101,W111,M112,F103,JPN,M111,V102,N109
KR5114450388 | 삼성일본리더스증권전환형자투자신탁제1호[주식]CP | 2 | 2 | C101,G115,M109,D102,G118,C103,V102,M111,F103
KR5114450350 | 삼성일본중소형 FOCUS 증권자투자신탁 H[주식]_A | 11 | 11 | V102,JPN,M111,D102,G118,C103,C101,P104,M109
KR5114450360 | 삼성일본중소형 FOCUS 증권자투자신탁 UH[주식]_C1 | 10 | 10 | V102,N135,M111,JPN,W111,C101,M109,D102,C103,G118
KR515009099M | 피델리티재팬증권자투자신탁(주식-재간접형)PRS-e | 1 | 1 | G110,M109,W111,M112,C101,C103,G118,JPN,D102,N109,M111,F103,D106,V102
KR510906191M | 미래에셋재팬인덱스증권자투자신탁1호(주식-파생형)종류A | 5 | 5 | C103,D102,M109,C101,JPN,M111,V102,S104
KR5116450079 | 브이아이일본고배당포커스증권자투자신탁 H[주식] 종류 C-F | 1 | 1 | V102,M111,D102,C103,G118,C101,P101,M109
KR5114800001 | 삼성J-REITs부동산투자신탁 1[REITs-재간접형](A) | 9 | 9 | W111,M112,N154,C101,D102,C103,V102,JPN,M111
KR5114530040 | 삼성퇴직연금일본리더스40증권자투자신탁제1호(채권혼합)C | 2 | 2 | M111,F103,JPN,G115,M109,C101,C103,V103,D102
KR5119450060 | 신한일본인덱스증권자투자신탁제1호(H)[주식](종류A1) | 1 | 1 | M109,W111,C101,C103,G118,JPN,D102,S104,M111,V102
KR5114450450 | 삼성클래식일본중소형FOCUS연금증권자투자신탁H[주식]_C | 2 | 2 | V102,JPN,F103,M111,D102,C103,C101,G110,P104,M109
KR5153450540 | 미래에셋퇴직연금다이와일본밸류중소형증권자투자신탁1호(주식)C | 2 | 2 | V102,F103,M111,D102,C103,C101,P104,M109,JPN,G115
KR5114450460 | 삼성클래식일본중소형FOCUS연금증권자투자신탁UH[주식]_C | 2 | 2 | D102,C103,C101,G110,P104,M109,V102,F103,M111,JPN
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.7s · ✅ — 전체 31/79 + 순자산순 30행 전량, 피델리티재팬 239억 1위 — Country_JPN token + 목록 기계 조립. 같은 이름 펀드가 펀드키로 4~6행 갈림(약점 #1 노출 🟢) [개선 🟡→✅]

**answer**

```text
조건에 해당하는 공모펀드는 전체 31개(클래스 79개)이며, 순자산 상위 30개 펀드는 다음과 같습니다 (기준일 2026-08-22, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위).

1. 피델리티재팬증권자투자신탁(주식-재간접): 순자산 239억원 · 클래스 10개
2. 우리재팬증권자투자신탁(주식): 순자산 187억원 · 클래스 1개
3. 피델리티재팬증권자투자신탁(주식-재간접형): 순자산 101억원 · 클래스 1개
4. 미래에셋퇴직연금다이와일본밸류중소형증권자투자신탁1호(주식): 순자산 96억원 · 클래스 2개
5. 피델리티재팬증권자투자신탁(주식-재간접형): 순자산 82억원 · 클래스 1개
6. 우리재팬증권자투자신탁(주식): 순자산 76억원 · 클래스 1개
7. 피델리티재팬증권자투자신탁(주식-재간접형): 순자산 46억원 · 클래스 1개
8. 삼성일본중소형 FOCUS 증권자투자신탁 H[주식]: 순자산 37억원 · 클래스 8개
9. 삼성J-REITs부동산투자신탁 제1호[REITs-재간접형]: 순자산 33억원 · 클래스 9개
10. 신한일본인덱스증권자투자신탁제1호(H)[주식]: 순자산 29억원 · 클래스 1개
11. 우리재팬증권자투자신탁(E)(주식): 순자산 28억원 · 클래스 1개
12. 하나재팬코어플러스증권투자신탁[주식]: 순자산 26억원 · 클래스 1개
13. 우리재팬증권자투자신탁(UH)(주식): 순자산 25억원 · 클래스 1개
14. 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식): 순자산 23억원 · 클래스 1개
15. 우리연금재팬증권자투자신탁(주식): 순자산 21억원 · 클래스 2개
16. 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식): 순자산 20억원 · 클래스 1개
17. 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식): 순자산 16억원 · 클래스 1개
18. 미래에셋재팬인덱스증권자투자신탁1호(주식-파생형): 순자산 15억원 · 클래스 5개
19. 우리연금재팬증권자투자신탁(주식): 순자산 15억원 · 클래스 1개
20. 삼성퇴직연금일본리더스40증권자투자신탁제1호(채권혼합): 순자산 13억원 · 클래스 1개
21. 우리재팬증권자투자신탁(주식): 순자산 13억원 · 클래스 1개
22. 삼성일본중소형FOCUS증권자투자신탁UH[주식]: 순자산 11억원 · 클래스 10개
23. 한화재팬코아증권투자신탁1호(주식): 순자산 11억원 · 클래스 2개
24. 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식): 순자산 10억원 · 클래스 6개
25. 피델리티재팬증권자투자신탁(주식-재간접형): 순자산 9억원 · 클래스 1개
26. 삼성클래식일본중소형FOCUS연금증권자투자신탁H[주식]: 순자산 6억원 · 클래스 1개
27. 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식): 순자산 4억원 · 클래스 1개
28. 삼성클래식일본중소형FOCUS연금증권자투자신탁UH[주식]: 순자산 4억원 · 클래스 2개
29. 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식): 순자산 2억원 · 클래스 1개
30. 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식): 순자산 1억원 · 클래스 1개
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '일본' → Country_JPN (Country) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,JPN,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,035자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 국가어 질의의 지역·설립국·태그·속성명·이름 OR 절을 KG Country 토큰 canon 하나로 접음 (KG 1R S3·3R C: 어떤 태그를 썼든 교정 · '유형' 이면 zrin_ptn_nm) · 전: WHERE prfd_attr_cds LIKE '%,JPN,%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", prfd_attr_cds FROM public_funds WHERE ',' || prfd_attr_cds || ',' LIKE '%,JPN,%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 30행 조회 (상한 30)
12. [Answer] 목록 답변 기계 조립 — 순자산순 펀드 목록 전 행 + 총량 머리줄 (2026-09-02 R3·S7: 30행 중 5·10행만 옮김 · S6: 총량 대신 '더 있을 수 있음')
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | 순자산_억원 | prfd_attr_cds
KR5148490027 | 피델리티재팬증권자투자신탁(주식-재간접)종류CP-e | 10 | 23927498519.0 | 239억원 | D106,V102,JPN,F103,M111,F101,D102,C103,G118,W111,M112,C101,G115,M109
KR512002074M | 우리재팬증권자투자신탁(주식)ClassC-F | 1 | 18779316843.0 | 187억원 | C101,W111,M109,D102,JPN,C103,G118,N109,V102,M111
KR515009097M | 피델리티재팬증권자투자신탁(주식-재간접형)C-e | 1 | 10186942147.0 | 101억원 | N109,JPN,M111,D106,V102,M109,W111,M112,C101,C103,G118,D102
KR5153450540 | 미래에셋퇴직연금다이와일본밸류중소형증권자투자신탁1호(주식)종류C-P2e | 2 | 9617648756.0 | 96억원 | V102,D106,M111,F103,KOR,D102,C103,C101,G115,JPN,P104,M109
KR515009099M | 피델리티재팬증권자투자신탁(주식-재간접형)PRS-e | 1 | 8294414003.0 | 82억원 | G110,M109,W111,M112,C101,C103,G118,JPN,D102,N109,M111,F103,D106,V102
KR5134651001 | 우리재팬증권자투자신탁(주식)ClassA | 1 | 7691198442.0 | 76억원 | M109,W111,C101,G118,C103,D102,N109,JPN,M111,V102
KR515009096M | 피델리티재팬증권자투자신탁(주식-재간접형)A-e | 1 | 4681894922.0 | 46억원 | D106,V102,M111,N109,D102,JPN,C103,G118,C101,W111,M112,M109
KR5114450356 | 삼성일본중소형 FOCUS 증권자투자신탁 H[주식]_Ce | 8 | 3792427520.0 | 37억원 | M111,V102,D106,G118,C103,D102,M109,P104,C101,JPN
KR5114800003 | 삼성J-REITs부동산투자신탁 제1호[REITs-재간접형]Ci | 9 | 3305207227.0 | 33억원 | W111,N154,C101,C103,D102,M111,V102,JPN
KR5119450060 | 신한일본인덱스증권자투자신탁제1호(H)[주식](종류A1) | 1 | 2992435476.0 | 29억원 | M109,W111,C101,C103,G118,JPN,D102,S104,M111,V102
KR5134651002 | 우리재팬증권자투자신탁(E)(주식) | 1 | 2877204740.0 | 28억원 | V102,N109,JPN,C103,G118,D102,M109,C101
KR512302011M | 하나재팬코어플러스증권투자신탁[주식]C | 1 | 2698923455.0 | 26억원 | M111,V102,P101,C101,G118,C103,JPN,D102
KR5134651003 | 우리재팬증권자투자신탁(UH)(주식)ClassA | 1 | 2547121158.0 | 25억원 | N109,V102,M111,C101,M109,JPN,D102,G118,C103
KR510902899M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식)C-e | 1 | 2398620745.0 | 23억원 | D102,G118,C103,C101,M109,V102,D106,JPN,M111
KR5134450078 | 우리연금재팬증권자투자신탁(주식)ClassC | 2 | 2186010016.0 | 21억원 | F103,M111,V102,C103,D102,M109,G110,JPN,C101,W111
KR510902901M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식)C-Pe | 1 | 2042704048.0 | 20억원 | C101,G110,M109,D102,JPN,C103,G118,D106,V102,M111,F103
KR510902894M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식)A-e | 1 | 1621671961.0 | 16억원 | JPN,G118,C103,D102,M109,C101,M111,V102,D106
KR513506008M | 미래에셋재팬인덱스증권자투자신탁1호(주식-파생형)종류A | 5 | 1575886662.0 | 15억원 | C101,M109,D102,C103,S104,JPN,V102,M111
KR512002065M | 우리연금재팬증권자투자신탁(주식)ClassC-e | 1 | 1523482366.0 | 15억원 | G110,M109,C101,W111,C103,D102,F103,M111,JPN,V102,D106
KR5114530040 | 삼성퇴직연금일본리더스40증권자투자신탁제1호(채권혼합)C | 1 | 1372162070.0 | 13억원 | M111,F103,JPN,G115,M109,C101,C103,V103,D102
KR512002067M | 우리재팬증권자투자신탁(주식)ClassA-e | 1 | 1320574811.0 | 13억원 | W111,C101,JPN,M109,D102,C103,G118,N109,D106,V102,M111
KR5114450368 | 삼성일본중소형FOCUS증권자투자신탁UH[주식]_Cpe(퇴직연금) | 10 | 1187461788.0 | 11억원 | F101,N135,V102,D106,F103,M111,C101,W111,JPN,M109,G115,D102,G118,C103
KR5129450050 | 한화재팬코아증권투자신탁1호(주식) 종류A | 2 | 1175251742.0 | 11억원 | M111,V102,N109,G118,C103,D102,JPN,C101
KR5153450300 | 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식)종류A | 6 | 1064307248.0 | 10억원 | C101,M109,D102,C103,G118,V102,JPN,M111
KR515009098M | 피델리티재팬증권자투자신탁(주식-재간접형)PRS | 1 | 960709492.0 | 9억원 | C103,G118,D102,G110,M109,C101,W111,M112,F103,JPN,M111,V102,N109
KR5114450450 | 삼성클래식일본중소형FOCUS연금증권자투자신탁H[주식]_C | 1 | 639373614.0 | 6억원 | V102,JPN,F103,M111,D102,C103,C101,G110,P104,M109
KR510902911M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식)C-Pe | 1 | 461858690.0 | 4억원 | C101,M109,G110,D102,C103,G118,D106,V102,F103,M111,JPN
KR5114450461 | 삼성클래식일본중소형FOCUS연금증권자투자신탁UH[주식]_Ce | 2 | 456367635.0 | 4억원 | D102,C103,C101,P104,M109,G110,JPN,D106,V102,F103,M111
KR510902904M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식)A-e | 1 | 261975002.0 | 2억원 | V102,D106,M111,D102,JPN,G118,C103,C101,M109
KR510902909M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식)C-e | 1 | 150724892.0 | 1억원 | JPN,M111,V102,D106,M109,C101,G118,C103,D102
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.5s

**answer**

```text
조건에 해당하는 공모펀드는 전체 31개(클래스 79개)이며, 순자산 상위 30개 펀드는 다음과 같습니다 (기준일 2026-08-22, 펀드 = 운용사 종목번호 기준·클래스 = 판매 단위·순자산 = 대표 클래스 기준(MAX)).

1. 피델리티재팬증권자투자신탁(주식-재간접): 순자산 239억원 · 클래스 10개
2. 우리재팬증권자투자신탁(주식): 순자산 187억원 · 클래스 1개
3. 피델리티재팬증권자투자신탁(주식-재간접형): 순자산 101억원 · 클래스 1개
4. 미래에셋퇴직연금다이와일본밸류중소형증권자투자신탁1호(주식): 순자산 96억원 · 클래스 2개
5. 피델리티재팬증권자투자신탁(주식-재간접형): 순자산 82억원 · 클래스 1개
6. 우리재팬증권자투자신탁(주식): 순자산 76억원 · 클래스 1개
7. 피델리티재팬증권자투자신탁(주식-재간접형): 순자산 46억원 · 클래스 1개
8. 삼성일본중소형 FOCUS 증권자투자신탁 H[주식]: 순자산 37억원 · 클래스 8개
9. 삼성J-REITs부동산투자신탁 제1호[REITs-재간접형]: 순자산 33억원 · 클래스 9개
10. 신한일본인덱스증권자투자신탁제1호(H)[주식]: 순자산 29억원 · 클래스 1개
11. 우리재팬증권자투자신탁(E)(주식): 순자산 28억원 · 클래스 1개
12. 하나재팬코어플러스증권투자신탁[주식]: 순자산 26억원 · 클래스 1개
13. 우리재팬증권자투자신탁(UH)(주식): 순자산 25억원 · 클래스 1개
14. 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식): 순자산 23억원 · 클래스 1개
15. 우리연금재팬증권자투자신탁(주식): 순자산 21억원 · 클래스 2개
16. 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식): 순자산 20억원 · 클래스 1개
17. 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식): 순자산 16억원 · 클래스 1개
18. 미래에셋재팬인덱스증권자투자신탁1호(주식-파생형): 순자산 15억원 · 클래스 5개
19. 우리연금재팬증권자투자신탁(주식): 순자산 15억원 · 클래스 1개
20. 삼성퇴직연금일본리더스40증권자투자신탁제1호(채권혼합): 순자산 13억원 · 클래스 1개
21. 우리재팬증권자투자신탁(주식): 순자산 13억원 · 클래스 1개
22. 삼성일본중소형FOCUS증권자투자신탁UH[주식]: 순자산 11억원 · 클래스 10개
23. 한화재팬코아증권투자신탁1호(주식): 순자산 11억원 · 클래스 2개
24. 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식): 순자산 10억원 · 클래스 6개
25. 피델리티재팬증권자투자신탁(주식-재간접형): 순자산 9억원 · 클래스 1개
26. 삼성클래식일본중소형FOCUS연금증권자투자신탁H[주식]: 순자산 6억원 · 클래스 1개
27. 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식): 순자산 4억원 · 클래스 1개
28. 삼성클래식일본중소형FOCUS연금증권자투자신탁UH[주식]: 순자산 4억원 · 클래스 2개
29. 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식): 순자산 2억원 · 클래스 1개
30. 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식): 순자산 1억원 · 클래스 1개
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '일본' → Country_JPN (Country) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,JPN,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,035자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 국가어 질의의 지역·설립국·태그·속성명·이름 OR 절을 KG Country 토큰 canon 하나로 접음 (KG 1R S3·3R C: 어떤 태그를 썼든 교정 · '유형' 이면 zrin_ptn_nm) · 전: WHERE prfd_attr_cds LIKE '%,JPN,%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, prfd_attr_cds, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE ',' || prfd_attr_cds || ',' LIKE '%,JPN,%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 30행 조회 (상한 30)
12. [Answer] 목록 답변 기계 조립 — 순자산순 펀드 목록 전 행 + 총량 머리줄 (2026-09-02 R3·S7: 30행 중 5·10행만 옮김 · S6: 총량 대신 '더 있을 수 있음')
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | prfd_attr_cds | 순자산_억원
KR5148490027 | 피델리티재팬증권자투자신탁(주식-재간접)종류CP-e | 10 | 23927498519.0 | D106,V102,JPN,F103,M111,F101,D102,C103,G118,W111,M112,C101,G115,M109 | 239억원
KR512002074M | 우리재팬증권자투자신탁(주식)ClassC-F | 1 | 18779316843.0 | C101,W111,M109,D102,JPN,C103,G118,N109,V102,M111 | 187억원
KR515009097M | 피델리티재팬증권자투자신탁(주식-재간접형)C-e | 1 | 10186942147.0 | N109,JPN,M111,D106,V102,M109,W111,M112,C101,C103,G118,D102 | 101억원
KR5153450540 | 미래에셋퇴직연금다이와일본밸류중소형증권자투자신탁1호(주식)종류C-P2e | 2 | 9617648756.0 | V102,D106,M111,F103,KOR,D102,C103,C101,G115,JPN,P104,M109 | 96억원
KR515009099M | 피델리티재팬증권자투자신탁(주식-재간접형)PRS-e | 1 | 8294414003.0 | G110,M109,W111,M112,C101,C103,G118,JPN,D102,N109,M111,F103,D106,V102 | 82억원
KR5134651001 | 우리재팬증권자투자신탁(주식)ClassA | 1 | 7691198442.0 | M109,W111,C101,G118,C103,D102,N109,JPN,M111,V102 | 76억원
KR515009096M | 피델리티재팬증권자투자신탁(주식-재간접형)A-e | 1 | 4681894922.0 | D106,V102,M111,N109,D102,JPN,C103,G118,C101,W111,M112,M109 | 46억원
KR5114450356 | 삼성일본중소형 FOCUS 증권자투자신탁 H[주식]_Ce | 8 | 3792427520.0 | M111,V102,D106,G118,C103,D102,M109,P104,C101,JPN | 37억원
KR5114800003 | 삼성J-REITs부동산투자신탁 제1호[REITs-재간접형]Ci | 9 | 3305207227.0 | W111,N154,C101,C103,D102,M111,V102,JPN | 33억원
KR5119450060 | 신한일본인덱스증권자투자신탁제1호(H)[주식](종류A1) | 1 | 2992435476.0 | M109,W111,C101,C103,G118,JPN,D102,S104,M111,V102 | 29억원
KR5134651002 | 우리재팬증권자투자신탁(E)(주식) | 1 | 2877204740.0 | V102,N109,JPN,C103,G118,D102,M109,C101 | 28억원
KR512302011M | 하나재팬코어플러스증권투자신탁[주식]C | 1 | 2698923455.0 | M111,V102,P101,C101,G118,C103,JPN,D102 | 26억원
KR5134651003 | 우리재팬증권자투자신탁(UH)(주식)ClassA | 1 | 2547121158.0 | N109,V102,M111,C101,M109,JPN,D102,G118,C103 | 25억원
KR510902899M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식)C-e | 1 | 2398620745.0 | D102,G118,C103,C101,M109,V102,D106,JPN,M111 | 23억원
KR5134450078 | 우리연금재팬증권자투자신탁(주식)ClassC | 2 | 2186010016.0 | F103,M111,V102,C103,D102,M109,G110,JPN,C101,W111 | 21억원
KR510902901M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식)C-Pe | 1 | 2042704048.0 | C101,G110,M109,D102,JPN,C103,G118,D106,V102,M111,F103 | 20억원
KR510902894M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식)A-e | 1 | 1621671961.0 | JPN,G118,C103,D102,M109,C101,M111,V102,D106 | 16억원
KR513506008M | 미래에셋재팬인덱스증권자투자신탁1호(주식-파생형)종류A | 5 | 1575886662.0 | C101,M109,D102,C103,S104,JPN,V102,M111 | 15억원
KR512002065M | 우리연금재팬증권자투자신탁(주식)ClassC-e | 1 | 1523482366.0 | G110,M109,C101,W111,C103,D102,F103,M111,JPN,V102,D106 | 15억원
KR5114530040 | 삼성퇴직연금일본리더스40증권자투자신탁제1호(채권혼합)C | 1 | 1372162070.0 | M111,F103,JPN,G115,M109,C101,C103,V103,D102 | 13억원
KR512002067M | 우리재팬증권자투자신탁(주식)ClassA-e | 1 | 1320574811.0 | W111,C101,JPN,M109,D102,C103,G118,N109,D106,V102,M111 | 13억원
KR5114450368 | 삼성일본중소형FOCUS증권자투자신탁UH[주식]_Cpe(퇴직연금) | 10 | 1187461788.0 | F101,N135,V102,D106,F103,M111,C101,W111,JPN,M109,G115,D102,G118,C103 | 11억원
KR5129450050 | 한화재팬코아증권투자신탁1호(주식) 종류A | 2 | 1175251742.0 | M111,V102,N109,G118,C103,D102,JPN,C101 | 11억원
KR5153450300 | 미래에셋다이와일본밸류중소형증권자투자신탁1호(H)(주식)종류A | 6 | 1064307248.0 | C101,M109,D102,C103,G118,V102,JPN,M111 | 10억원
KR515009098M | 피델리티재팬증권자투자신탁(주식-재간접형)PRS | 1 | 960709492.0 | C103,G118,D102,G110,M109,C101,W111,M112,F103,JPN,M111,V102,N109 | 9억원
KR5114450450 | 삼성클래식일본중소형FOCUS연금증권자투자신탁H[주식]_C | 1 | 639373614.0 | V102,JPN,F103,M111,D102,C103,C101,G110,P104,M109 | 6억원
KR510902911M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식)C-Pe | 1 | 461858690.0 | C101,M109,G110,D102,C103,G118,D106,V102,F103,M111,JPN | 4억원
KR5114450461 | 삼성클래식일본중소형FOCUS연금증권자투자신탁UH[주식]_Ce | 2 | 456367635.0 | D102,C103,C101,P104,M109,G110,JPN,D106,V102,F103,M111 | 4억원
KR510902904M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식)A-e | 1 | 261975002.0 | V102,D106,M111,D102,JPN,G118,C103,C101,M109 | 2억원
KR510902909M | 미래에셋다이와일본밸류중소형증권자투자신탁1호(UH)(주식)C-e | 1 | 150724892.0 | JPN,M111,V102,D106,M109,C101,G118,C103,D102 | 1억원
```

</details>

---

## KG-020. 미국에 투자하는 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.2s · ✅ 98/333 — USA 태그 확정식 발동

**answer**

```text
조회 조건에 해당하는 공모펀드는 98개(클래스 333개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,731자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 지역 컬럼 등호·미래핑 태그 LIKE 를 ','||prfd_attr_cds||',' 정식형으로 교체 (2026-09-01 FND-026 재검: ='글로벌' 오모수 + wrap 없는 LIKE 가 98/560행 누락)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,USA,%' AND sale_yn = '판매중' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
98 | 333
```

</details>

### 2라운드(6bad723) — HTTP 200 · 64.8s · ✅ 유지 98/333

**answer**

```text
조회 조건에 해당하는 공모펀드는 98개(클래스 333개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미국' → Country_USA (Country) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,USA,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,035자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,USA,%' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
98 | 333
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.7s

**answer**

```text
조회 조건에 해당하는 공모펀드는 98개(클래스 333개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미국' → Country_USA (Country) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,USA,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,035자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,USA,%' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
98 | 333
```

</details>

---

## KG-021. 대만에 투자하는 공모펀드 있어?

### 기준선(31e72ef) — HTTP 200 · 40.2s · ❌ 오거절 — '대만' 은 국가어 사전(11종) 밖·Region_Taiwan public_funds alias 0 → HCX 가 fd_estb_ctry_cd=410(설립국 한국) 오용 → '확인 불가' (gold 피델리티대만펀드 1) [라우터/가드 → 플래너 → KG]

**answer**

```text
제공된 데이터에 대만에 투자하는 공모펀드가 수록되어 있는지 확인할 수 없습니다. 따라서 답변을 드릴 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,295자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", fd_estb_ctry_cd FROM public_funds WHERE prvo_pbff_desc = '공모' AND fd_estb_ctry_cd = 410 AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 30행 조회 (상한 30)
11. [Answer] 커버리지 병기 — LIMIT 도달, 전체 298행 / 69펀드 를 답변 입력에 굽는다 (2026-09-02 R3 재검: 30행 중 5행 나열 + 총량 미고지)
12. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm | 클래스수 | fd_nast_suma | 순자산_억원 | fd_estb_ctry_cd
KR5114490239 | 삼성 글로벌액티브 적격TDF 2050증권투자신탁UH[주식혼합-재간접형]_Cpe(퇴직연금) | 5 | 402990070845.0 | 4029억원 | 410
KR5127470095 | KB스타 미국 나스닥 100 인덱스 증권 자투자신탁(주식-파생형)(H) C-퇴직e | 10 | 322471828490.0 | 3224억원 | 410
KR5129490051 | 한화 LIFEPLUS 적격 TDF 2045 증권투자신탁(주식혼합-재간접형) 종류 C-RPe(퇴직연금) | 4 | 186804724218.0 | 1868억원 | 410
KR5129490049 | 한화 LIFEPLUS 적격 TDF 2040 증권 자투자신탁(주식혼합-재간접형) 종류 C-RPe(퇴직연금) | 4 | 133496555564.0 | 1334억원 | 410
KR5117420097 | 신한초단기채증권투자신탁[채권](종류C-re) | 4 | 126306046394.0 | 1263억원 | 410
KR5172470008 | 트러스톤인덱스알파증권자투자신탁[주식-파생형]Ci클래스 | 1 | 122386876226.0 | 1223억원 | 410
KR5114490229 | 삼성 글로벌액티브 적격TDF 2050증권투자신탁H[주식혼합-재간접형] CPe(퇴직연금) | 4 | 121271432912.0 | 1212억원 | 410
KR5114490338 | 삼성 글로벌 EMP 적격 TDF 2035 증권자투자신탁[주식혼합-재간접형]_Cpe(퇴직연금) | 3 | 114952589677.0 | 1149억원 | 410
KR5114490419 | 삼성EMP리얼리턴증권자투자신탁UH[주식혼합-재간접형]_Cpe(퇴직) | 2 | 99886616854.0 | 998억원 | 410
KR5114490429 | 삼성OCIO솔루션성장형증권투자신탁[혼합-재간접형]_Cpe(퇴직) | 3 | 93900168725.0 | 939억원 | 410
KR5113490119 | 한국투자OCIO알아서증권자투자신탁(채권혼합-재간접형)C-R2 | 4 | 89493957750.0 | 894억원 | 410
KR5153420265 | 미래에셋미국달러채권증권자투자신탁1호(UH)(채권) 종류CP2e | 8 | 88196691419.0 | 881억원 | 410
KR5114490255 | 삼성 글로벌액티브 적격TDF 2055 증권투자신탁H[주식혼합-재간접형]_Cpe(퇴직연금) | 4 | 80920867296.0 | 809억원 | 410
KR5153480030 | 미래에셋개인연금평생소득TIF혼합자산자투자신탁 | 1 | 76909804131.0 | 769억원 | 410
KR5149490004 | IBK플레인바닐라EMP증권투자신탁[혼합-재간접형] 종류C-Re | 9 | 75786648814.0 | 757억원 | 410
KR5114490378 | 삼성 글로벌 EMP 적격 TDF 2055 증권자투자신탁[주식혼합-재간접형]_Cpe(퇴직연금) | 3 | 68491882686.0 | 684억원 | 410
KR5117450113 | 신한글로벌탄소중립솔루션증권투자신탁(H)[주식](종류C-re) | 4 | 61846980873.0 | 618억원 | 410
KR5114490409 | 삼성디딤밀당다람쥐글로벌EMP증권자투자신탁[채권혼합-재간접형]_Cpe(퇴직연금) | 4 | 55997519049.0 | 559억원 | 410
KR5114490328 | 삼성 글로벌 EMP 적격 TDF 2030 증권자투자신탁[주식혼합-재간접형]_Cpe(퇴직연금) | 3 | 55924182506.0 | 559억원 | 410
KR5123450125 | 키움글로벌차세대IT&네트워크증권자투자신탁(UH)[주식] Class C-P2e(퇴직연금) | 8 | 41874226230.0 | 418억원 | 410
KR5149490049 | IBK 로우코스트 적격 TDF 2040 증권자투자신탁[주식혼합-재간접형] C-Re | 4 | 39669945266.0 | 396억원 | 410
KR5149490079 | IBK 로우코스트 적격 TDF 2055 증권자투자신탁[주식혼합-재간접형] C-Re | 4 | 38977575148.0 | 389억원 | 410
KR5114490368 | 삼성 글로벌 EMP 적격 TDF 2050 증권자투자신탁[주식혼합-재간접형]_Cpe(퇴직연금) | 3 | 32156088060.0 | 321억원 | 410
KR5114490348 | 삼성 글로벌 EMP 적격 TDF 2040 증권자투자신탁[주식혼합-재간접형]_Cpe(퇴직연금) | 3 | 31063026367.0 | 310억원 | 410
KR5127450310 | KB주주가치포커스증권투자신탁[주식]A | 12 | 28715247139.0 | 287억원 | 410
KR5114490388 | 삼성타겟리스크OCIO솔루션1성장형증권투자신탁[혼합-재간접형]_Cpe(퇴직) | 3 | 25902161967.0 | 259억원 | 410
KR5123450115 | 키움글로벌차세대IT&네트워크증권자투자신탁H[주식]C-P2e(퇴직연금) | 9 | 25449757030.0 | 254억원 | 410
KR5114490358 | 삼성 글로벌 EMP 적격 TDF 2045 증권자투자신탁[주식혼합-재간접형]_Cpe(퇴직연금) | 3 | 24099178343.0 | 240억원 | 410
KR5153450940 | 미래에셋아시아테크증권투자신탁(주식) 종류A | 9 | 20677000298.0 | 206억원 | 410
KR5117450009 | 신한얼리버드증권자투자신탁[주식]종류C-Re | 5 | 16925977805.0 | 169억원 | 410
```

</details>

### 2라운드(6bad723) — HTTP 200 · 4.0s · ✅ — 피델리티대만펀드 1클래스 — Country_TWN 희소 판정(기본모수 0행) → 이름 폴백 OR. 설립국 오용 소멸 [개선 ❌→✅]

**answer**

```text
네, 대만 투자 공모펀드로 '**피델리티대만펀드**'가 있습니다. 이는 1개의 클래스로 구성되어 있으며 현재 모든 클래스가 판매 중입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '대만' → Country_TWN (Country) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,TWN,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,599자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 국가어 질의의 지역·설립국·태그·속성명·이름 OR 절을 KG Country 토큰 canon 하나로 접음 (KG 1R S3·3R C: 어떤 태그를 썼든 교정 · '유형' 이면 zrin_ptn_nm) · 전: WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND ',' || prfd_attr_cds || ',' LIKE '%,TWN,%' LIMIT 30
7. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MIN(rptt_ksd_itm_no) AS 대표번호, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND (',' || prfd_attr_cds || ',' LIKE '%,TWN,%' OR REPLACE(itm_nm,' ','') LIKE '%대만%') GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 내부 코드 컬럼 숨김 — prfd_attr_cds (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | 대표번호 | prfd_attr_cds
OS555085013M | 피델리티대만펀드 | 1 | 1 |  | 
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 4.0s

**answer**

```text
네, 대만 투자 공모펀드로 '**피델리티대만펀드**'가 있습니다. 이는 대만을 주요 투자 대상으로 하는 펀드로, 현재 판매 중인 클래스 수는 1개 입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 17
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '대만' → Country_TWN (Country) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,TWN,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,599자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 국가어 질의의 지역·설립국·태그·속성명·이름 OR 절을 KG Country 토큰 canon 하나로 접음 (KG 1R S3·3R C: 어떤 태그를 썼든 교정 · '유형' 이면 zrin_ptn_nm) · 전: WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND ',' || prfd_attr_cds || ',' LIKE '%,TWN,%' LIMIT 30
7. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MIN(rptt_ksd_itm_no) AS 대표번호, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND (',' || prfd_attr_cds || ',' LIKE '%,TWN,%' OR REPLACE(itm_nm,' ','') LIKE '%대만%') GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 내부 코드 컬럼 숨김 — prfd_attr_cds (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | 대표번호 | prfd_attr_cds
OS555085013M | 피델리티대만펀드 | 1 | 1 |  | 
```

</details>

---

## KG-022. 유럽에 투자하는 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.2s · 🟡 — 61/193 정확(지역 컬럼) 이나 기준 미고지·확장 93/259 미병기 → 부분 [조립]

**answer**

```text
조회 조건에 해당하는 공모펀드는 61개(클래스 193개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '유럽' → Region_Europe (Region) [+후손 18: Region_EuroZone, Region_UK, Region_Switzerland …] → public_funds.fd_ivst_rgn_desc='유럽'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,440자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE fd_ivst_rgn_desc = '유럽' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
61 | 193
```

</details>

### 2라운드(6bad723) — HTTP 200 · 2.3s · 🟡 유지 — 61/193 정확, 기준 미고지·확장 91/257 미병기 [조립 R8]

**answer**

```text
조회 조건에 해당하는 공모펀드는 61개(클래스 193개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '유럽' → Region_Europe (Region) [+후손 18: Region_EuroZone, Region_UK, Region_Switzerland …] → public_funds.fd_ivst_rgn_desc='유럽'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,546자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE fd_ivst_rgn_desc = '유럽' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
61 | 193
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.2s

**answer**

```text
조회 조건에 해당하는 공모펀드는 61개(클래스 193개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 20
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '유럽' → Region_Europe (Region) [+후손 18: Region_EuroZone, Region_UK, Region_Switzerland …] → public_funds.fd_ivst_rgn_desc='유럽'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,546자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE fd_ivst_rgn_desc = '유럽' AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
61 | 193
```

</details>

---

## KG-023. 아시아에 투자하는 공모펀드 중 순자산 큰 5개 알려줘

### 기준선(31e72ef) — HTTP 200 · 7.0s · ❌ — Region_Asia closure 가 Region_Korea('국내') 유입 → IN('국내','아시아') → 국내 MMF 5개 도배(삼성MMF법인제1호 12.4조) [온톨로지 제약(closure) → 가드]

**answer**

```text
아시아에 투자하는 공모펀드 중 순자산이 큰 5개의 펀드는 다음과 같습니다.

1. 삼성MMF법인제1호 C 클래스: 124295억원
2. KB법인용MMF I - 1 종류C: 96265억원
3. 우리큰만족법인MMF1호(국공채)ClassC: 90389억원
4. 우리큰만족신종MMF3호 ClassC: 80496억원
5. 신영법인용MMF 제4-26호 C-I형: 76370억원
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '아시아' → Region_Asia (Region) [+후손 13: Region_Korea, Region_China, Region_Japan …] → public_funds.fd_ivst_rgn_desc='아시아' · public_funds.fd_ivst_rgn_desc='국내'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 대표행 보정 — GROUP BY 펀드키 주입 + MAX/MIN 감싸기 + 클래스수 병기 (2026-09-02 R7 실측: 미특정 경로에서 HCX 가 GROUP BY 를 버려 한화2.2배 3클래스 도배 — gold 는 NH-Amundi·삼성KOSPI200)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", fd_ivst_rgn_desc FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_ivst_rgn_desc IN ('국내', '아시아') AND fd_nast_suma IS NOT NULL AND fd_nast_suma > 0 GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY 3 DESC LIMIT 5
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 5행 조회 (상한 30)
11. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
12. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | TRIM(itm_nm) | fd_nast_suma | 클래스수 | 순자산_억원 | fd_ivst_rgn_desc
KR5014410030 | 삼성MMF법인제1호 C 클래스 | 12429536252016.0 | 4 | 124295억원 | 국내
KR5027410010 | KB법인용MMF I- 1 종류C | 9626578656529.0 | 2 | 96265억원 | 국내
KR5018410030 | 우리큰만족법인MMF1호(국공채)ClassC | 9038952435738.0 | 2 | 90389억원 | 국내
KR5018101412 | 우리큰만족신종MMF3호 ClassC | 8049692532381.0 | 1 | 80496억원 | 국내
KR5025101000 | 신영법인용MMF 제4-26호 C-I형 | 7637051696362.0 | 2 | 76370억원 | 국내
```

</details>

### 2라운드(6bad723) — HTTP 200 · 8.4s · ✅ — KB중국본토A주 1,453·차이나솔로몬1호 1,393·한투베트남그로스 1,066·신한중국의꿈2호 1,038·다이와넥스트AP1호 668 (gold 5/5) — S4 closure scope(Region_Korea 제외, 후손 12) + 대표행 GROUP BY [개선 ❌→✅]

**answer**

```text
아시아에 투자하는 공모펀드 중 순자산이 큰 5개의 펀드는 다음과 같습니다.

1. KB중국본토A주증권자투자신탁[주식]A: 1,453억원
2. 미래에셋차이나솔로몬증권투자신탁1호(주식)종류A: 1,393억원
3. 한국투자베트남그로스증권자투자신탁(주식) 종류A: 1,066억원
4. 신한중국의꿈증권자투자신탁제2호(H)[주식]종류A: 1,038억원
5. 미래에셋다이와넥스트아시아퍼시픽증권자투자신탁1호(H-JPY)(주식)종류F: 668억원

이 펀드들은 모두 아시아 지역에 투자하는 공모펀드로, 순자산이 큰 상위 5개 펀드들입니다. 다만, 클래스 수가 여러 개인 경우 하나의 대표 클래스만을 기재하였으니 참고 부탁드립니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '아시아' → Region_Asia (Region) [+후손 12: Region_China, Region_Japan, Region_India …] → public_funds.fd_ivst_rgn_desc='아시아'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,548자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 대표행 보정 — GROUP BY 펀드키 주입 + MAX/MIN 감싸기 + 클래스수 병기 (2026-09-02 R7 실측: 미특정 경로에서 HCX 가 GROUP BY 를 버려 한화2.2배 3클래스 도배 — gold 는 NH-Amundi·삼성KOSPI200)
7. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원", fd_ivst_rgn_desc FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_ivst_rgn_desc = '아시아' AND fd_nast_suma IS NOT NULL AND fd_nast_suma > 0 GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY 3 DESC LIMIT 5
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 5행 조회 (상한 30)
11. [Answer] 내부 코드 컬럼 숨김 — fd_nast_suma (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)
12. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
13. [Guard] 상품명 전사 교정 — '미래에셋다이내믹아시아퍼시픽증권자투자신탁1호' → '미래에셋다이와넥스트아시아퍼시픽증권자투자신탁1호' (조회 원문 밖 이름 1건 — 2026-09-02 R3 재검: '삼성중국본토중소형FOSS' 는 DB 에 0행, 실제 FOCUS)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | TRIM(itm_nm) | fd_nast_suma | 클래스수 | 순자산_억원 | fd_ivst_rgn_desc
KR5127450020 | KB중국본토A주증권자투자신탁[주식]A | 145347201786.0 | 14 | 1453억원 | 아시아
KR5153651002 | 미래에셋차이나솔로몬증권투자신탁1호(주식)종류A | 139343522568.0 | 1 | 1393억원 | 아시아
KR5113450190 | 한국투자베트남그로스증권자투자신탁(주식) 종류A | 106602228139.0 | 6 | 1066억원 | 아시아
KR5117651001 | 신한중국의꿈증권자투자신탁제2호(H)[주식]종류A | 103801550961.0 | 3 | 1038억원 | 아시아
KR5153450368 | 미래에셋다이와넥스트아시아퍼시픽증권자투자신탁1호(H-JPY)(주식)종류F | 66896057477.0 | 6 | 668억원 | 아시아
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 50.6s

**answer**

```text
아시아에 투자하는 공모펀드 중 순자산이 큰 5개의 펀드는 다음과 같습니다.

1. 마이다스아시아리더스성장주연금증권자투자신탁(UH)(주식) C-Pe2: 635억원
2. 마이다스 아시아 리더스 성장주 증권 자투자신탁(H)(주식) W클래스: 609억원
3. 마이다스 아시아 리더스 성장주 증권 자투자신탁(UH)(주식) C-P1클래스: 309억원
4. 삼성퇴직연금아세안40증권자투자신탁 제1호[채권혼합]_Ce: 308억원
5. 미래에셋아시아테크증권투자신탁(주식) 종류A: 206억원

위의 순서는 순자산의 크기에 따른 것이며, 클래스 수는 괄호 안의 내용을 참고해주세요.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 29
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '아시아' → Region_Asia (Region) [+후손 12: Region_China, Region_Japan, Region_India …] → public_funds.fd_ivst_rgn_desc='아시아'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,548자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 대표행 보정 — GROUP BY 펀드키 주입 + MAX/MIN 감싸기 + 클래스수 병기 (2026-09-02 R7 실측: 미특정 경로에서 HCX 가 GROUP BY 를 버려 한화2.2배 3클래스 도배 — gold 는 NH-Amundi·삼성KOSPI200)
7. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_no, TRIM(itm_nm), MAX(fd_nast_suma) AS fd_nast_suma, COUNT(*) AS "클래스수", prfd_attr_cds, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND fd_nast_suma IS NOT NULL AND fd_nast_suma > 0 AND ',' || prfd_attr_cds || ',' LIKE '%,W108,%' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY 3 DESC LIMIT 5
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 5행 조회 (상한 30)
12. [Answer] 내부 코드 컬럼 숨김 — fd_nast_suma, prfd_attr_cds (2026-09-02 R3 재검: 태그 코드 C101·M109·V102 가 답변에 원문 노출)
13. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | TRIM(itm_nm) | fd_nast_suma | 클래스수 | prfd_attr_cds | 순자산_억원
KR5157450112 | 마이다스아시아리더스성장주연금증권자투자신탁(UH)(주식) C-Pe2 | 63575276180.0 | 4 | C103,W108,D102,P103,G115,M109,C101,M111,F103,V102,D106,N135 | 635억원
KR5157450117 | 마이다스 아시아 리더스 성장주 증권 자투자신탁(H)(주식) W클래스 | 60956175315.0 | 13 | P103,D102,W108,C103,C101,M109,N135,V102,M105,M111 | 609억원
KR5157450138 | 마이다스 아시아 리더스 성장주 증권 자투자신탁(UH)(주식) C-P1클래스 | 30995414365.0 | 11 | C103,P103,D102,W108,M109,G110,C101,F103,M111,N135,V102 | 309억원
KR5114430072 | 삼성퇴직연금아세안40증권자투자신탁 제1호[채권혼합]_Ce | 30842400276.0 | 2 | G115,M109,C101,C103,V103,W108,D102,M111,F103,D106 | 308억원
KR5153450940 | 미래에셋아시아테크증권투자신탁(주식) 종류A | 20677000298.0 | 9 | V102,M111,C101,W108,D102,C103 | 206억원
```

</details>

---

## KG-024. 반도체 테마 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.0s · ✅ 12/78 — 이름 ∪ 태그

**answer**

```text
조회 조건에 해당하는 공모펀드는 12개(클래스 78개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,295자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (prvo_pbff_desc = '공모' AND (REPLACE(itm_nm,' ','') LIKE '%반도체%' OR zrin_attr_nms LIKE '%반도체%')) LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
12 | 78
```

</details>

### 2라운드(6bad723) — HTTP 200 · 3.1s · ❌ 회귀 ✅→❌ — 10/50 (gold 12/78). '반도체'→FundAttr_N144 Ground 후 ① HCX 가 wrap 없는 LIKE '%,N144,%' (첫 토큰 14클래스 누락 64→50) ② 기준선의 '태그∪이름' 규칙(이름만 2펀드 14클래스) 소실. 속성 태그 확정식이 C축 통칭에만 걸림 [가드(token canon 전 축 미적용 N4)]

**answer**

```text
조회 조건에 해당하는 공모펀드는 10개(클래스 50개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '반도체' → FundAttr_N144 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,N144,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,608자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prfd_attr_cds LIKE '%,N144,%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
10 | 50
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.5s

**answer**

```text
조회 조건에 해당하는 공모펀드는 12개(클래스 78개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '반도체' → FundAttr_N144 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,N144,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,608자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (',' || prfd_attr_cds || ',' LIKE '%,N144,%' OR REPLACE(itm_nm,' ','') LIKE '%반도체%') LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
12 | 78
```

</details>

---

## KG-025. 삼성자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 4.7s · ❌ — or_co_xtn_itt_cd IN ('삼성','삼성KODEX')(ETF alias 를 펀드 코드 컬럼에) → 0 → "'미수록'" · ETF 는 운용사 필터 없이 1,534 전체 (gold 207 · 224) [플래너 → SQL가드(IN 리터럴 미검증) → KG(교차 alias 오염)]

**answer**

```text
삼성자산운용이 운용하는 공모펀드는 '미수록'이며, 국내 ETF는 1,534개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 35
2. [Route] 상품군 — domestic_etfs, public_funds · 근거: 머리명사 펀드/ETF
3. [Ground] KG 개체 매핑 — '삼성자산운용' → Org_00040010 (Organization) → public_funds.or_co_xtn_itt_cd='00040010' · domestic_etfs.cu_fund_mgmt_co='삼성' · domestic_etfs.ref_fund_mgmt_co='Samsung Asset Management Co Ltd' · domestic_etfs.cu_fund_mgmt_co='삼성KODEX' … 외 13종 / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs', 'public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 domestic_etfs, public_funds · 28,977자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT '삼성자산운용 공모펀드' AS 분류, COUNT(*) AS 갯수 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('삼성', '삼성KODEX') AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' UNION ALL SELECT '국내 ETF' AS 분류, COUNT(*) FROM domestic_etfs WHERE pd_sale_yn = 1 AND pd_lste_dt = 99991231 LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 2행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 7,122자 적용 (domestic_etfs, public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
분류 | 갯수
삼성자산운용 공모펀드 | 0
국내 ETF | 1534
```

</details>

### 2라운드(6bad723) — HTTP 200 · 43.2s · ❌ — 오거절: precheck 가 or_co IN('삼성','삼성KODEX') 를 실존 코드 아님으로 2회 기각(거짓 '미수록'/1,534 소멸). Ground 라인이 펀드 코드·ETF alias 를 한 줄에 실어 HCX 가 컬럼 혼동, 'ETF'→FundAttr_M113 오염 신규 [형태 변화 거짓→거절 · R4 미착수+N9]

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 35
2. [Route] 상품군 — domestic_etfs, public_funds · 근거: 머리명사 펀드/ETF
3. [Ground] KG 개체 매핑 — '삼성자산운용' → Org_00040010 (Organization) → public_funds.or_co_xtn_itt_cd='00040010' · domestic_etfs.cu_fund_mgmt_co='삼성' · domestic_etfs.ref_fund_mgmt_co='Samsung Asset Management Co Ltd' · domestic_etfs.cu_fund_mgmt_co='삼성KODEX' / 'ETF' → FundAttr_M113 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,M113,%' / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs', 'public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 domestic_etfs, public_funds · 28,790자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT '삼성자산운용 공모펀드' AS 구분, COUNT(*) AS 개수 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('삼성', '삼성KODEX') AND prvo_pbff_desc = '공모' UNION ALL SELECT '국내 ETF' AS 구분, COUNT(*) FROM domestic_etfs WHERE cu_fund_mgmt_co = 'Samsung Asset Management Co Ltd' LIMIT 30
9. [Guard] SQL 기각 — 코드 컬럼 리터럴 검증 실패: or_co_xtn_itt_cd = '삼성' 은 데이터에 없는 코드; or_co_xtn_itt_cd = '삼성KODEX' 은 데이터에 없는 코드 — 코드는 'KG 개체 매핑' 의 값만 쓴다. 매핑이 없으면 지어내지 말고 REFUSE: 로 답한다
10. [Guard] 재생성 후에도 실패 — 코드 컬럼 리터럴 검증 실패: or_co_xtn_itt_cd = '삼성' 은 데이터에 없는 코드; or_co_xtn_itt_cd = '삼성KODEX' 은 데이터에 없는 코드 — 코드는 'KG 개체 매핑' 의 값만 쓴다. 매핑이 없으면 지어내지 말고 REFUSE: 로 답한다
11. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 3라운드(1e0e641) — HTTP 200 · 6.0s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 35
2. [Route] 상품군 — domestic_etfs, public_funds · 근거: 머리명사 펀드/ETF
3. [Ground] KG 개체 매핑 — '삼성자산운용' → Org_00040010 (Organization) → public_funds.or_co_xtn_itt_cd='00040010' · domestic_etfs.cu_fund_mgmt_co='삼성' · domestic_etfs.ref_fund_mgmt_co='Samsung Asset Management Co Ltd' · domestic_etfs.cu_fund_mgmt_co='삼성KODEX' / 'ETF' → FundAttr_M113 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,M113,%' / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs', 'public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 domestic_etfs, public_funds · 28,790자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT '삼성자산운용 공모펀드' AS 구분, COUNT(*) AS 개수 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('삼성', '삼성KODEX') AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 30
10. [Guard] SQL 기각 — 코드 컬럼 리터럴 검증 실패: or_co_xtn_itt_cd = '삼성' 은 데이터에 없는 코드; or_co_xtn_itt_cd = '삼성KODEX' 은 데이터에 없는 코드 — 코드는 'KG 개체 매핑' 의 값만 쓴다. 매핑이 없으면 지어내지 말고 REFUSE: 로 답한다
11. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.3s)
12. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
13. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT '삼성자산운용 공모펀드' AS 구분, COUNT(*) AS 개수 FROM public_funds WHERE or_co_xtn_itt_cd = '00040010' AND prvo_pbff_desc = '공모' AND pd_sale_yn = 1 AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 2
14. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: pd_sale_yn(→ domestic_etfs 컬럼이다. 이 테이블에는 없다)
15. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-026. KOSPI200을 벤치마크로 쓰는 공모펀드와 KOSPI200을 추종하는 국내 ETF는 각각 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 43.5s · ❌ 오거절 — pd_base_index 환각 2회 → 거절. 지수 alias(cu_base_index 'KOSPI200' 9 vs ref_base_index 'KOSPI 200 CR' 등) 불일치는 도달 전 실패로 잠재 확인 (gold 421 · 50) [플래너 → KG]

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 56
2. [Route] 상품군 — domestic_etfs, public_funds · 근거: 머리명사 펀드/ETF · 값 ['KOSPI200']
3. [Ground] KG 개체 매핑 — 'KOSPI200' → Idx_a_fa21f0fb15 (Index) [+후손 4: Idx_KOSPI200, Idx_v_865a261002, Idx_v_92f77e875b …] → domestic_etfs.cu_base_index='KOSPI200' · public_funds.bmrk_nm='KOSPI200' · public_funds.bmrk_nm='KOSPI200 10% + KIS종합채권 01Y 90%' · public_funds.bmrk_nm='KOSPI200 10% + 종합채권 01Y 90%' … 외 21종 / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs', 'public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 domestic_etfs, public_funds · 28,805자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT 'KOSPI200을 벤치마크로 쓰는 공모펀드' AS 질문, COUNT(*) AS 개수 FROM public_funds WHERE prvo_pbff_desc = '공모' AND bmrk_nm LIKE '%KOSPI200%' UNION ALL SELECT 'KOSPI200을 추종하는 국내 ETF' AS 질문, COUNT(*) FROM domestic_etfs WHERE pd_base_index = 'KOSPI200' LIMIT 30
8. [Guard] SQL 기각 — 스키마에 없는 컬럼: pd_base_index(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: cu_base_index, ref_base_index — 뜻이 같다는 보장은 없다)
9. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: pd_base_index(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: cu_base_index, ref_base_index — 뜻이 같다는 보장은 없다)
10. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 2라운드(6bad723) — HTTP 200 · 8.1s · ❌ 형태 악화 거절→거짓 단언 — '펀드 2,888개(sale_yn 없음·클래스수; 기본모수 815/2,217·정확일치 421/1,266) · ETF 수록되지 않음(cu_base_index='KOSPI200' 9건 전부 pd_sale_yn=0; ref_base_index 정본 50)'. UNION 분기 0 을 거짓 0 으로 단언 — 신규 감점 [S7 지수 alias + 가드(교차 분기별 모수·0행 정책 N3)]

**answer**

```text
KOSPI200을 벤치마크로 사용하는 공모펀드는 2888개이며, KOSPI200을 추종하는 국내 ETF는 현재 수록되지 않았습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 56
2. [Route] 상품군 — domestic_etfs, public_funds · 근거: 머리명사 펀드/ETF · 값 ['KOSPI200']
3. [Ground] KG 개체 매핑 — 'KOSPI200' → Idx_a_fa21f0fb15 (Index) [+후손 4: Idx_KOSPI200, Idx_v_865a261002, Idx_v_92f77e875b …] → domestic_etfs.cu_base_index='KOSPI200' · public_funds.bmrk_nm='KOSPI200' · public_funds.bmrk_nm='KOSPI200 10% + KIS종합채권 01Y 90%' · public_funds.bmrk_nm='KOSPI200 10% + 종합채권 01Y 90%' … 외 21종 / 'ETF' → FundAttr_M113 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,M113,%' / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs', 'public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 domestic_etfs, public_funds · 29,029자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT 'KOSPI200을 벤치마크로 쓰는 공모펀드' AS 구분, COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' AND bmrk_nm LIKE '%KOSPI200%' UNION ALL SELECT 'KOSPI200을 추종하는 국내 ETF' AS 구분, COUNT(*) FROM domestic_etfs WHERE pd_base_index = 'KOSPI200' AND pd_sale_yn = 1 LIMIT 30
8. [Guard] SQL 기각 — 스키마에 없는 컬럼: pd_base_index(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: cu_base_index, ref_base_index — 뜻이 같다는 보장은 없다)
9. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 3.1s)
10. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT 'KOSPI200을 벤치마크로 쓰는 공모펀드', COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' AND bmrk_nm LIKE '%KOSPI200%' UNION ALL SELECT 'KOSPI200을 추종하는 국내 ETF', COUNT(*) FROM domestic_etfs WHERE cu_base_index = 'KOSPI200' AND pd_sale_yn = 1 LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 2행 조회 (상한 30)
13. [Answer] 답변 생성 완료 — 답변 규칙 7,122자 적용 (domestic_etfs, public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
'KOSPI200을 벤치마크로 쓰는 공모펀드' | COUNT(*)
KOSPI200을 벤치마크로 쓰는 공모펀드 | 2888
KOSPI200을 추종하는 국내 ETF | 0
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 46.7s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 56
2. [Route] 상품군 — domestic_etfs, public_funds · 근거: 머리명사 펀드/ETF · 값 ['KOSPI200']
3. [Ground] KG 개체 매핑 — 'KOSPI200' → Idx_a_fa21f0fb15 (Index) [+후손 4: Idx_KOSPI200, Idx_v_865a261002, Idx_v_92f77e875b …] → domestic_etfs.cu_base_index='KOSPI200' · public_funds.bmrk_nm='KOSPI200' · public_funds.bmrk_nm='KOSPI200 10% + KIS종합채권 01Y 90%' · public_funds.bmrk_nm='KOSPI200 10% + 종합채권 01Y 90%' … 외 21종 / 'ETF' → FundAttr_M113 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,M113,%' / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs', 'public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 domestic_etfs, public_funds · 29,029자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT 'KOSPI200을 벤치마크로 쓰는 공모펀드' AS 구분, COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' AND pd_sale_yn = 1 AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 30
9. [Guard] SQL 기각 — 스키마에 없는 컬럼: pd_sale_yn(→ domestic_etfs 컬럼이다. 이 테이블에는 없다)
10. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: pd_sale_yn(→ domestic_etfs 컬럼이다. 이 테이블에는 없다)
11. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-027. 미래에셋코어테크 펀드 설정 좌수 알려줘

### 기준선(31e72ef) — HTTP 200 · 8.2s · ❌❌ 환각 — fd_set_pcd='10'(설정유형코드) 를 '10좌' 로 6펀드 단언. 좌수 ABSENT 선언·게이트 부재 [게이트/온톨로지 → HCX]

**answer**

```text
미래에셋코어테크 펀드의 설정좌수는 다음과 같습니다.

1. 미래에셋코어테크증권자투자신탁(주식) 종류 A: 10좌
2. 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류 A: 10좌
3. 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류 A-e: 10좌
4. 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류 A-e: 10좌
5. 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류 A: 10좌
6. 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류 A-e: 10좌

이는 모두 10좌씩 설정된 상태입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,812자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(fd_set_pcd) AS fd_set_pcd FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 6행 조회 (상한 30)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_set_pcd
KR5153450780 | 미래에셋코어테크증권자투자신탁(주식) 종류A | 10 | 10 | 10
KR5153450910 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A | 4 | 4 | 10
KR5153451150 | 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류A-e | 5 | 5 | 10
KR5153451160 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류A-e | 5 | 5 | 10
KR5153490560 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류A | 13 | 13 | 10
KR5153490736 | 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류A-e | 4 | 4 | 10
```

</details>

### 2라운드(6bad723) — HTTP 200 · 0.2s · ✅ — ABSENT(hasUnitsOutstanding, vocab 좌수) 게이트 즉답 HCX 0회 + 순자산·기준가 대체 안내. '10좌' 환각 소멸 [개선 ❌❌→✅ · S5/R2]

**answer**

```text
공모펀드 마스터·설명서 수집분 어디에도 좌수(설정 좌수·잔존 좌수·잔고 좌수) 컬럼이 없어 좌수는 답할 수 없습니다. 규모는 순자산(fd_nast_suma), 가격은 기준가(bns_bpr, 기준일 단일 스냅샷)로 안내할 수 있습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 기각 — 온톨로지 ABSENT — public_funds 에 hasUnitsOutstanding 속성 없음 · 질문의 '좌수' (enums absent_properties → HCX 0회)
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 3라운드(1e0e641) — HTTP 200 · 0.2s

**answer**

```text
공모펀드 마스터·설명서 수집분 어디에도 좌수(설정 좌수·잔존 좌수·잔고 좌수) 컬럼이 없어 좌수는 답할 수 없습니다. 규모는 순자산(fd_nast_suma), 가격은 기준가(bns_bpr, 기준일 단일 스냅샷)로 안내할 수 있습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 기각 — 온톨로지 ABSENT — public_funds 에 hasUnitsOutstanding 속성 없음 · 질문의 '좌수' (enums absent_properties → HCX 0회)
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-028. 미래에셋코어테크 펀드가 가장 많이 보유한 종목은 뭐야?

### 기준선(31e72ef) — HTTP 200 · 2.9s · ❌ 오거절 — 라우팅 public_funds 인데 domestic_etfs+ext_etf_holdings 'SELECT TOP 1' 생성, 검사기가 대상 밖 테이블 통과 → OperationalError (gold 삼성전자 24.95%) [플래너 → SQL가드]

**answer**

```text
데이터 조회 중 오류가 발생해 확인할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,577자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT TOP 1 constituent, weight_pct FROM domestic_etfs JOIN ext_etf_holdings ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no WHERE domestic_etfs.pd_abrv_nm LIKE '%미래에셋 코어테크%' ORDER BY weight_pct DESC LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 실행 실패 — OperationalError
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 2라운드(6bad723) — HTTP 200 · 54.5s · ❌ 형태 악화 오류→환각 — 'IBK K-AI반도체코어테크 ETF 57.12%': 펀드 질의에 domestic_etfs JOIN ext_etf_holdings 가 통과(교차 플래그로 라우팅 밖 테이블 검사 미발동) + 상품 고유명이 pd_nm 에 붙음. gold 삼성전자 24.95% 실재 [가드(N1 교차 시 테이블 범위)+Ground(N2 상품 고유명 핀)]

**answer**

```text
미래에셋코어테크 펀드가 가장 많이 보유한 종목은 'IBK K-AI반도체코어테크'이며, 해당 종목의 보유 비율은 57.12%입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,683자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT domestic_etfs.pd_abrv_nm AS abrv_nm, domestic_etfs.pd_nm AS nm, domestic_etfs.pd_itm_no, ext_etf_holdings.weight_pct, ext_etf_holdings.quantity FROM domestic_etfs JOIN ext_etf_holdings ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no WHERE domestic_etfs.pd_nm LIKE '%코어테크%' ORDER BY 5 DESC LIMIT 1
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
abrv_nm | nm | pd_itm_no | weight_pct | quantity
IBK K-AI반도체코어테크 | IBK IBK K-AI반도체 코어테크 증권상장지수투자신탁[주식] | KR70005G0001 | 0.5712069951252513 | 14449989.0
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 8.0s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,683자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT TOP 1 constituent, weight_pct FROM domestic_etfs JOIN ext_etf_holdings ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no WHERE domestic_etfs.pd_abrv_nm LIKE '%미래에셋 코어테크%' ORDER BY weight_pct DESC LIMIT 30
9. [Guard] SQL 기각 — SQLite 문법이 아니다(TOP n) — LIMIT n 을 쓴다
10. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 5.1s)
11. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT TOP 1 constituent, weight_pct FROM domestic_etfs JOIN ext_etf_holdings ON ext_etf_holdings.etf_code = domestic_etfs.pd_itm_no WHERE domestic_etfs.pd_abrv_nm LIKE '%미래에셋 코어테크%' ORDER BY weight_pct DESC LIMIT 1
12. [Guard] 재생성 후에도 실패 — SQLite 문법이 아니다(TOP n) — LIMIT n 을 쓴다
13. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-029. 우리자산운용 펀드 수를 대표예탁원종목번호 기준으로 세면 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 3.7s · ✅ 88 — 사용자 명시 기준(rptt) 존중, 가드 키 치환 없음 (현행키 235 병기 없어 만점 아님)

**answer**

```text
우리자산운용 펀드 수는 대표예탁원종목번호 기준으로 총 88개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 36
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '우리자산운용' → Org_00040007 (Organization) → public_funds.or_co_xtn_itt_cd='00040007'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,520자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT rptt_ksd_itm_no) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040007' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(DISTINCT rptt_ksd_itm_no)
88
```

</details>

### 2라운드(6bad723) — HTTP 200 · 3.4s · ✅ 유지 88 (rptt)

**answer**

```text
우리자산운용 펀드 수는 대표예탁원종목번호 기준으로 총 88개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 36
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '우리자산운용' → Org_00040007 (Organization) → public_funds.or_co_xtn_itt_cd='00040007'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,626자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT rptt_ksd_itm_no) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (TRIM(or_co_xtn_itt_cd) = '00040007') LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(DISTINCT rptt_ksd_itm_no)
88
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 3.9s

**answer**

```text
우리자산운용 펀드 수는 대표예탁원종목번호 기준으로 총 88개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 36
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '우리자산운용' → Org_00040007 (Organization) → public_funds.or_co_xtn_itt_cd='00040007'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,626자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT rptt_ksd_itm_no) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00040007' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(DISTINCT rptt_ksd_itm_no)
88
```

</details>

---

## KG-030. 미래에셋차이나솔로몬 시리즈는 몇 호까지 있고 각각 클래스가 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 50.1s · ❌ — 미특정 라우팅 → han_clas_policies IS NOT NULL 로 1호·3호 4행 탈락 → '5호까지'(근거 0)·3호 4·2호 5·합 9 날조 (gold 1호2·2호7·3호8) [라우터 → 플래너 → 조립]

**answer**

```text
미래에셋차이나솔로몬 시리즈는 총 5호까지 있으며, 각 호마다 클래스는 다음과 같습니다.

- 미래에셋차이나솔로몬증권투자신탁 3호(이하 3호): C2, C3, C4, C5 (총 4개)
- 미래에셋차이나솔로몬증권투자신탁 2호(이하 2호): C1, C2, C3, C4, C5 (총 5개)

따라서, 미래에셋차이나솔로몬 시리즈 내 클래스는 총 9개가 됩니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 38
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008' · domestic_etfs.cu_fund_mgmt_co='미래에셋' · domestic_etfs.cu_fund_mgmt_co='TIGER' · domestic_etfs.ref_fund_mgmt_co='Mirae Asset Global Investments Co Ltd' … 외 40종
4. [Gate] 통과 — 대상 테이블 미특정
5. [Plan] 근거문서 조립 — 대상 마스터 4테이블 · 52,925자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Route] SQL 사후 보정 — FROM public_funds → 그 상품군의 답변 규칙·이름 필터 적용 (2026-09-02 R7 재검: 미특정 경로는 답변 규칙이 4도메인으로 희석되고 상품명 필터 가드가 꺼진다)
7. [Ground] 잔여 상품 고유명 '차이나솔로몬' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (사후 보정 경로)
8. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_nm, han_clas_policies FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%차이나솔로몬%' AND han_clas_policies IS NOT NULL LIMIT 30
12. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
13. [Execute] 11행 조회 (상한 30)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_nm | han_clas_policies
미래에셋차이나솔로몬증권투자신탁 3(주식)종류C 1 | 보수체감
미래에셋차이나솔로몬증권투자신탁 3(주식)종류C-w | 랩
미래에셋차이나솔로몬증권투자신탁2호(주식)C1 | 보수체감
미래에셋차이나솔로몬증권투자신탁2호(주식)C2 | 보수체감
미래에셋차이나솔로몬증권투자신탁2호(주식)C3 | 보수체감
미래에셋차이나솔로몬증권투자신탁2호(주식)C4 | 보수체감
미래에셋차이나솔로몬증권투자신탁2호(주식)C5 | 보수체감
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C2 | 보수체감
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C3 | 보수체감
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C4 | 보수체감
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C5 | 보수체감
```

</details>

### 2라운드(6bad723) — HTTP 200 · 7.7s · 🟡 — '3호까지' ✓ 1호 2 ✓ 이나 2호 5(gold 7)·3호 5(gold 8)·합 12(gold 17): 17행 정확 조회 후 HCX 오산. '5호' 날조·정책 필터 소멸 [개선 ❌→🟡 · 조립(LLM 산술, R14 확정식 미착수)]

**answer**

```text
미래에셋차이나솔로몬 시리즈는 총 3호까지 있으며, 각 호 별로 클래스는 다음과 같습니다.

- 미래에셋차이나솔로몬증권투자신탁 3호: 클래스 5개(C2, C3, C4, C5, A-e)
- 미래에셋차이나솔로몬증권투자신탁 2호: 클래스 5개(C1, C2, C3, C4, A-e)
- 미래에셋차이나솔로몬증권투자신탁 1호: 클래스 2개(A, A-e)

따라서, 미래에셋차이나솔로몬 시리즈 내 클래스는 총 12개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 38
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008' · domestic_etfs.cu_fund_mgmt_co='미래에셋' · domestic_etfs.cu_fund_mgmt_co='TIGER' · domestic_etfs.ref_fund_mgmt_co='Mirae Asset Global Investments Co Ltd' … 외 1종
4. [Gate] 통과 — 대상 테이블 미특정
5. [Plan] 근거문서 조립 — 대상 마스터 4테이블 · 53,392자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Route] SQL 사후 보정 — FROM public_funds → 그 상품군의 답변 규칙·이름 필터 적용 · 재생성 문서도 그 상품군으로 (2026-09-02 R7 재검: 미특정 경로는 답변 규칙이 4도메인으로 희석되고 상품명 필터 가드가 꺼진다)
7. [Ground] 잔여 상품 고유명 '차이나솔로몬' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (사후 보정 경로)
8. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_nm, COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬%') GROUP BY itm_nm LIMIT 30
12. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
13. [Execute] 17행 조회 (상한 30)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_nm | COUNT(*)
미래에셋차이나솔로몬증권투자신탁 3(주식)종류A | 1
미래에셋차이나솔로몬증권투자신탁 3(주식)종류C 1 | 1
미래에셋차이나솔로몬증권투자신탁 3(주식)종류C-e | 1
미래에셋차이나솔로몬증권투자신탁 3(주식)종류C-w | 1
미래에셋차이나솔로몬증권투자신탁1호(주식)A-e | 1
미래에셋차이나솔로몬증권투자신탁1호(주식)종류A | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)(C-A) | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)A-e | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C1 | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C2 | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C3 | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C4 | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C5 | 1
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C2 | 1
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C3 | 1
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C4 | 1
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C5 | 1
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 52.8s

**answer**

```text
미래에셋차이나솔로몬 시리즈는 총 3호까지 있으며, 각 호 별로 클래스는 다음과 같습니다.

- 미래에셋차이나솔로몬증권투자신탁 3호: 클래스 5개(C2, C3, C4, C5, A-e)
- 미래에셋차이나솔로몬증권투자신탁 2호: 클래스 5개(C1, C2, C3, C4, A-e)
- 미래에셋차이나솔로몬증권투자신탁 1호: 클래스 2개(A, A-e)

따라서, 미래에셋차이나솔로몬 시리즈 내 클래스는 총 12개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 38
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008' · domestic_etfs.cu_fund_mgmt_co='미래에셋' · domestic_etfs.cu_fund_mgmt_co='TIGER' · domestic_etfs.ref_fund_mgmt_co='Mirae Asset Global Investments Co Ltd' … 외 1종
4. [Gate] 통과 — 대상 테이블 미특정
5. [Plan] 근거문서 조립 — 대상 마스터 4테이블 · 53,392자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Route] SQL 사후 보정 — FROM public_funds → 그 상품군의 답변 규칙·이름 필터 적용 · 재생성 문서도 그 상품군으로 (2026-09-02 R7 재검: 미특정 경로는 답변 규칙이 4도메인으로 희석되고 상품명 필터 가드가 꺼진다)
7. [Ground] 잔여 상품 고유명 '차이나솔로몬' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (사후 보정 경로)
8. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_nm, COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬%') GROUP BY itm_nm LIMIT 30
12. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
13. [Execute] 17행 조회 (상한 30)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_nm | COUNT(*)
미래에셋차이나솔로몬증권투자신탁 3(주식)종류A | 1
미래에셋차이나솔로몬증권투자신탁 3(주식)종류C 1 | 1
미래에셋차이나솔로몬증권투자신탁 3(주식)종류C-e | 1
미래에셋차이나솔로몬증권투자신탁 3(주식)종류C-w | 1
미래에셋차이나솔로몬증권투자신탁1호(주식)A-e | 1
미래에셋차이나솔로몬증권투자신탁1호(주식)종류A | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)(C-A) | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)A-e | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C1 | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C2 | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C3 | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C4 | 1
미래에셋차이나솔로몬증권투자신탁2호(주식)C5 | 1
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C2 | 1
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C3 | 1
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C4 | 1
미래에셋차이나솔로몬증권투자신탁3호(주식) 종류C5 | 1
```

</details>

---

## KG-031. 피델리티가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 2.2s · ❌ — '역외' 가 _POP_WIDEN 에 걸려 sale_yn 미주입 + HCX 가 JP모간 코드 00080030 을 IN 에 날조 → 167/350 (판매완료·JP모간 포함, 역외 00130001 미포함; gold 153/293) [SQL가드 → HCX → KG]

**answer**

```text
피델리티가 운용하는 공모펀드는 167개(클래스 350개)입니다 (공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 34
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '피델리티' → Org_00080029 (Organization) → public_funds.or_co_xtn_itt_cd='00080029'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,342자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00080029', '00080030') AND prvo_pbff_desc = '공모' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
167 | 350
```

</details>

### 2라운드(6bad723) — HTTP 200 · 50.4s · ❌ 유지 — 167/350 동일(JP모간 00080030 실존 코드라 precheck 통과·'역외' _POP_WIDEN 로 sale_yn 없음) + '역외펀드 47개는 별도 법인이라 포함하지 않았다' 가 질문('포함하면')과 모순. gold 153/293 [가드 R6(코드 집합 확장·Ground 밖 코드 기각)]

**answer**

```text
피델리티자산운용이 운용하는 공모펀드는 167개(클래스 350개)입니다 (공모 기준, 기준일 2026-08-22).
종목명이 '피델리티' 로 시작하는 역외펀드 47개(클래스 47개, 해외 운용법인 코드 00130001)는 별도 법인이라 이 수에 포함하지 않았습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 34
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '피델리티' → Org_00080029 (Organization, 정식명 피델리티자산운용) → public_funds.or_co_xtn_itt_cd='00080029'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00080029', '00080030') AND prvo_pbff_desc = '공모' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
167 | 350
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 2.2s

**answer**

```text
피델리티자산운용이 운용하는 공모펀드는 167개(클래스 350개)입니다 (공모 기준, 기준일 2026-08-22).
종목명이 '피델리티' 로 시작하는 역외펀드 47개(클래스 47개, 해외 운용법인 코드 00130001)는 별도 법인이라 이 수에 포함하지 않았습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 34
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '피델리티' → Org_00080029 (Organization, 정식명 피델리티자산운용) → public_funds.or_co_xtn_itt_cd='00080029'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,448자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('00080029', '00080030') AND prvo_pbff_desc = '공모' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
167 | 350
```

</details>

---

## KG-032. 2026년 9월 1일 기준으로 순자산이 가장 큰 공모펀드 알려줘

### 기준선(31e72ef) — HTTP 200 · 2.7s · ✅ 기준일 2026-08-22 명시 후 이후 시점 거절 — reject 형 정답

**answer**

```text
제공된 데이터의 기준일은 2026-08-22입니다. 이후 시점의 정보는 확인할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 35
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 기준일 이후 시점 ['202609'] 포함 → SQL 의 mat_dt 사용 여부로 사후 판정
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,418자 · 구성: 도메인 규칙 + 시점 주의 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 기준일 이후 시점 ['202609'] 이(가) SQL 의 mat_dt 조건에 쓰이지 않음 → 만기 질의가 아닌 시점·전망 질의로 판정
7. [Decision] HCX SQL 은 만들었으나 기준일 이후 근거가 DB 에 없어 종료
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 2라운드(6bad723) — HTTP 200 · 2.2s · ✅ 유지 — 기준일 2026-08-22 명시 후 이후 시점 거절

**answer**

```text
제공된 데이터의 기준일은 2026-08-22입니다. 이후 시점의 정보는 확인할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 35
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 기준일 이후 시점 ['202609'] 포함 → SQL 의 mat_dt 사용 여부로 사후 판정
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,524자 · 구성: 도메인 규칙 + 시점 주의 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 기준일 이후 시점 ['202609'] 이(가) SQL 의 mat_dt 조건에 쓰이지 않음 → 만기 질의가 아닌 시점·전망 질의로 판정
7. [Decision] HCX SQL 은 만들었으나 기준일 이후 근거가 DB 에 없어 종료
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 3라운드(1e0e641) — HTTP 200 · 2.5s

**answer**

```text
제공된 데이터의 기준일은 2026-08-22입니다. 이후 시점의 정보는 확인할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 35
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 기준일 이후 시점 ['202609'] 포함 → SQL 의 mat_dt 사용 여부로 사후 판정
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,524자 · 구성: 도메인 규칙 + 시점 주의 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 기준일 이후 시점 ['202609'] 이(가) SQL 의 mat_dt 조건에 쓰이지 않음 → 만기 질의가 아닌 시점·전망 질의로 판정
7. [Decision] HCX SQL 은 만들었으나 기준일 이후 근거가 DB 에 없어 종료
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## KG-033. 가장 최근에 설정된 공모펀드 알려줘

### 기준선(31e72ef) — HTTP 200 · 49.8s · 🟡 — KB K-성장과 지배구조 30 목표전환 2026-06-12 ✓ 이나 LIMIT 1 로 동률 2건 중 1건·커버리지 미병기 [플래너 → 조립]

**answer**

```text
가장 최근에 설정된 공모펀드는 '**KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A**' 입니다. 이 펀드는 2026년 6월 12일에 설정되었습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 19
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Plan] 근거문서 조립 — 대상 public_funds · 12,060자 · 구성: 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_nm, estb_dt FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' ORDER BY estb_dt DESC LIMIT 1
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_nm | estb_dt
KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A | 20260612
```

</details>

### 2라운드(6bad723) — HTTP 200 · 4.6s · 🟡 유지 — 2026-06-12 KB K-성장과 지배구조 30 ✓, LIMIT 1 로 동률(미래에셋국민참여형) 누락·커버리지 미병기 [R9]

**answer**

```text
가장 최근에 설정된 공모펀드는 '**KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A**'입니다. 이 펀드는 2026년 6월 12일에 설정되었습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 19
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Plan] 근거문서 조립 — 대상 public_funds · 12,166자 · 구성: 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_nm, estb_dt FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' ORDER BY estb_dt DESC LIMIT 1
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_nm | estb_dt
KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A | 20260612
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 69.7s

**answer**

```text
가장 최근에 설정된 공모펀드는 '**KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A**' 입니다. 이 펀드는 2026년 6월 12일에 설정되었습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 19
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Plan] 근거문서 조립 — 대상 public_funds · 12,166자 · 구성: 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_nm, estb_dt FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' ORDER BY estb_dt DESC LIMIT 1
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_nm | estb_dt
KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A | 20260612
```

</details>

---

## KG-034. 미래에셋코어테크 펀드는 운용한 지 얼마나 됐어?

### 기준선(31e72ef) — HTTP 200 · 6.4s · ❌ 오거절 — '운용한 지' 가 설명서항목 트리거에 없어 ext 미조인 → fd_estb_dt 환각 2회 → 거절 (gold 2019-10-23, 6년 10개월) [라우터/규칙 트리거 → 플래너]

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 26
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,812자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT fd_estb_ctry_cd, fd_estb_dt, fd_daily_bas_dt, itm_no, TRIM(itm_nm) AS itm_nm FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' LIMIT 1
11. [Guard] SQL 기각 — 스키마에 없는 컬럼: fd_estb_dt(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: estb_dt, fd_estb_ctry_cd — 뜻이 같다는 보장은 없다)
12. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.4s)
13. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
14. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
15. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
16. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT fd_estb_dt, itm_no, TRIM(itm_nm) AS itm_nm FROM public_funds WHERE or_co_xtn_itt_cd IN ('00080008') AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' LIMIT 30
17. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: fd_estb_dt(어느 테이블에도 없는 컬럼이다. 철자가 비슷한 실제 컬럼: estb_dt, fd_estb_ctry_cd — 뜻이 같다는 보장은 없다)
18. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

### 2라운드(6bad723) — HTTP 200 · 2.1s · ❌ 형태 변화 거절→거짓 유보 — HCX 가 Ground 상품 고유명 '코어테크' 를 '코어텍' 으로 옮겨 0행 → '상품 자체가 없다'. '운용한 지' 트리거 부재로 estb_dt 조차 없음 [가드(N2 이름 리터럴 핀)+라우터(R9)+R1(c)]

**answer**

```text
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 조건 중 일부는 수록된 데이터에 해당하는 상품 자체가 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 26
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,918자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(fd_daily_bas_dt) AS fd_daily_bas_dt, MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어텍%' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 0행 조회 (상한 30)
13. [Diagnose] 0행 원인 — 조건별 단독 조회: TRIM(or_co_xtn_itt_cd) = '00080008' → 4,536건 / REPLACE(itm_nm,' ','') LIKE '%코어텍%' → 0건. 값 자체가 없는 조건: REPLACE(itm_nm,' ','') LIKE '%코어텍%'.
14. [Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_daily_bas_dt | 대표번호

```

</details>

### 3라운드(1e0e641) — HTTP 200 · 3.4s

**answer**

```text
제공된 데이터에 미래에셋코어테크 펀드의 운용 기간이 명시되어 있지 않습니다. 따라서 해당 정보를 확인할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 26
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,918자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 상품명 필터 주입 — 질문의 고유명 '코어테크' 이 SQL 에 없어 itm_nm LIKE 주입 + LIMIT 1 해제 (2026-08-31 밤 FND-016 실측: 운용사 코드만 필터한 모수 1,512행에서 임의 1행이 답으로 나갔다)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
11. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(fd_daily_bas_dt) AS fd_daily_bas_dt, MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
12. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
13. [Execute] 6행 조회 (상한 30)
14. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
15. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_daily_bas_dt | 대표번호
KR5153450780 | 미래에셋코어테크증권자투자신탁(주식) 종류A | 10 | 10 | 20260821 | 031910536840
KR5153450910 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A | 4 | 4 | 20260821 | 031910536890
KR5153451150 | 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류A-e | 5 | 5 | 20260821 | 031910539310
KR5153451160 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류A-e | 5 | 5 | 20260821 | 031910539320
KR5153490560 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류A | 13 | 13 | 20260821 | 031910482550
KR5153490736 | 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류A-e | 4 | 4 | 20260821 | 031910539100
```

</details>

---

## KG-035. 2026년에 설정된 공모펀드는 몇 개야?

### 기준선(31e72ef) — HTTP 200 · 5.8s · ❌ — 재생성 JOIN COUNT(*) 에 펀드단위 가드 미적용 → 클래스 124 를 '124개' 펀드로 (gold 39/124) [SQL가드(JOIN·재생성 경로)]

**answer**

```text
2026년에 설정된 공모펀드는 총 124개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Plan] 근거문서 조립 — 대상 public_funds · 12,060자 · 구성: 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
8. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
9. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND (estb_dt >= 20260000 AND prvo_pbff_desc = '공모') LIMIT 30
11. [Guard] SQL 기각 — 스키마에 없는 컬럼: estb_dt(→ ext_fund_page 컬럼이다. 이 테이블에는 없다)
12. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 1.8s)
13. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
14. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT COUNT(*) FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE public_funds.sale_yn = '판매중' AND public_funds.prvo_pbff_desc = '공모' AND (ext_fund_page.estb_dt BETWEEN 20260000 AND 20269999) LIMIT 30
15. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
16. [Execute] 1행 조회 (상한 30)
17. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(*)
124
```

</details>

### 2라운드(6bad723) — HTTP 200 · 4.1s · ❌ 유지 — '124개'(클래스). 외부 JOIN 주입 가드는 발동했으나 JOIN 경로에 펀드단위 가드 미적용 [R7]

**answer**

```text
2026년에 설정된 공모펀드는 총 124개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Plan] 근거문서 조립 — 대상 public_funds · 12,166자 · 구성: 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] 외부 테이블 JOIN 주입 — estb_dt → estb_dt(유일 근사) · estb_dt 은 ext_fund_page 컬럼 → LEFT JOIN 주입 (2026-09-02 R2·S11 재검: mtco_nm 환각 3라운드 연속 1차 기각으로 재생성 예산 소진 → 거절)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(*) FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE estb_dt BETWEEN 20260000 AND 20269999 AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(*)
124
```

</details>

### 3라운드(1e0e641) — HTTP 200 · 3.7s

**answer**

```text
2026년에 설정된 공모펀드는 총 124개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Plan] 근거문서 조립 — 대상 public_funds · 12,166자 · 구성: 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] 외부 테이블 JOIN 주입 — estb_dt → estb_dt(유일 근사) · estb_dt 은 ext_fund_page 컬럼 → LEFT JOIN 주입 (2026-09-02 R2·S11 재검: mtco_nm 환각 3라운드 연속 1차 기각으로 재생성 예산 소진 → 거절)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(*) FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE estb_dt BETWEEN 20260000 AND 20269999 AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(*)
124
```

</details>

---

## X1. 미래에셋코어테크 펀드가 가장 많이 담은 종목 3개 알려줘

### 3라운드(1e0e641) — HTTP 200 · 7.2s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 31
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,683자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT h.holding_nm, h.weight_pct, e.etf_name FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no WHERE e.pd_abrv_nm LIKE '%미래에셋 코어테크%' ORDER BY h.weight_pct DESC LIMIT 3
8. [Guard] SQL 기각 — 스키마에 없는 컬럼: holding_nm(→ ext_fund_holdings 컬럼이다. 이 테이블에는 없다)
9. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.6s)
10. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT h.holding_nm, h.weight_pct, e.etf_name FROM domestic_etfs e JOIN ext_etf_holdings h ON h.etf_code = e.pd_itm_no WHERE e.pd_abrv_nm LIKE '%미래에셋 코어테크%' ORDER BY h.weight_pct DESC LIMIT 3
11. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: holding_nm(→ ext_fund_holdings 컬럼이다. 이 테이블에는 없다)
12. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## X2. KB중국본토A주 펀드가 가장 많이 보유한 종목은 뭐야?

### 3라운드(1e0e641) — HTTP 200 · 33.6s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 30
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Ground] 잔여 상품 고유명 'KB중국본토A주' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,968자 · 구성: 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT e.etf_name, eh.weight_pct, eh.holding_nm FROM ext_etf_holdings e JOIN ext_ovs_etf_holdings eh ON e.etf_code = eh.etf_ticker WHERE e.etf_name LIKE '%KB중국본토A주%' ORDER BY e.etf_name ASC, eh.weight_pct DESC LIMIT 30
9. [Guard] SQL 기각 — 허용 테이블 밖: ext_etf_holdings
10. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 3.2s)
11. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT e.etf_name, eh.weight_pct, eh.holding_nm FROM ext_etf_holdings e JOIN ext_ovs_etf_holdings eh ON e.etf_code = eh.etf_ticker WHERE e.etf_name LIKE '%KB중국본토A주%' ORDER BY e.etf_name ASC, eh.weight_pct DESC LIMIT 30
12. [Guard] 재생성 후에도 실패 — 허용 테이블 밖: ext_etf_holdings
13. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## X3. 미래에셋 코어택 펀드 순자산 알려줘

### 3라운드(1e0e641) — HTTP 200 · 2.6s

**answer**

```text
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 조건 중 일부는 수록된 데이터에 해당하는 상품 자체가 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 19
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 9,740자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
8. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", CAST(SUM(fd_nast_suma) AS INTEGER) AS fd_nast_suma, CAST(SUM(fd_nast_suma)/100000000 AS INTEGER) || '억원' AS "순자산_억원", MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어텍%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 0행 조회 (상한 30)
12. [Diagnose] 0행 원인 — 조건별 단독 조회: TRIM(or_co_xtn_itt_cd) = '00080008' → 4,536건 / REPLACE(itm_nm,' ','') LIKE '%코어텍%' → 0건 / sale_yn = '판매중' → 10,962건 / prvo_pbff_desc = '공모' → 14,716건. 값 자체가 없는 조건: REPLACE(itm_nm,' ','') LIKE '%코어텍%'.
13. [Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | fd_nast_suma | 순자산_억원 | 대표번호

```

</details>

---

## X4. 친환경 테마 공모펀드는 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 2.4s

**answer**

```text
조회 조건에 해당하는 공모펀드는 6개(클래스 23개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '친환경' → FundAttr_N119 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,N119,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,608자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND (',' || prfd_attr_cds || ',' LIKE '%,N119,%' OR ',' || prfd_attr_cds || ',' LIKE '%,N168,%' OR REPLACE(itm_nm,' ','') LIKE '%친환경%') LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
6 | 23
```

</details>

---

## X5. 2차전지 테마 공모펀드는 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 2.2s

**answer**

```text
조회 조건에 해당하는 공모펀드는 1개(클래스 12개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 19
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '2차전지' → FundAttr_N145 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,N145,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,613자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
7. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND ',' || prfd_attr_cds || ',' LIKE '%,N145,%' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
1 | 12
```

</details>

---

## X6. 개방형이면서 추가형인 공모펀드는 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 2.8s

**answer**

```text
조회 조건에 해당하는 펀드는 2,874개(클래스 8,355개)입니다 (판매중 기준, 기준일 2026-08-22).
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 23
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,401자 · 구성: 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
8. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
9. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND ',' || prfd_attr_cds || ',' LIKE '%,C101,%' AND ',' || prfd_attr_cds || ',' LIKE '%,C103,%' LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 1행 조회 (상한 30)
13. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
2874 | 8355
```

</details>

---

## X7. KOSPI200을 추종하는 국내 ETF는 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 48.7s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 28
2. [Route] 상품군 — domestic_etfs · 근거: 머리명사 ETF · 값 ['KOSPI200']
3. [Ground] KG 개체 매핑 — 'KOSPI200' → Idx_a_fa21f0fb15 (Index) [+후손 4: Idx_KOSPI200, Idx_v_865a261002, Idx_v_92f77e875b …] → domestic_etfs.cu_base_index='KOSPI200' / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs']
5. [Plan] 근거문서 조립 — 대상 domestic_etfs · 16,624자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(*) FROM domestic_etfs WHERE cu_base_index = 'KOSPI200' AND pd SALE_YN = 1 LIMIT 30
8. [Guard] SQL 기각 — 스키마에 없는 컬럼: SALE_YN(→ public_funds 컬럼이다. 이 테이블에는 없다)
9. [Guard] 재생성 후에도 실패 — 스키마에 없는 컬럼: SALE_YN(→ public_funds 컬럼이다. 이 테이블에는 없다)
10. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## X8. S&P500을 벤치마크로 쓰는 공모펀드와 S&P500 추종 국내 ETF는 각각 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 8.3s

**answer**

```text
조회 결과에 따르면, S&P500을 벤치마크로 사용하는 공모펀드는 63개입니다. 그러나 S&P500을 추종하는 국내 ETF에 대한 정보는 조회 결과에 포함되어 있지 않으므로 제공할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 49
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드/ETF · 값 ['S&P500']
3. [Ground] KG 개체 매핑 — 'ETF' → FundAttr_M113 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,M113,%' / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 public_funds · 12,588자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT '공모펀드' AS 구분, COUNT(*) AS cnt FROM public_funds WHERE prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 2
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 1행 조회 (상한 30)
10. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
구분 | cnt
공모펀드 | 63
```

</details>

---

## X9. 미래에셋자산운용이 운용하는 공모펀드와 국내 ETF는 각각 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 51.7s

**answer**

```text
미래에셋자산운용이 운용하는 공모펀드와 국내 ETF는 각각 1개, 191개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 37
2. [Route] 상품군 — domestic_etfs, public_funds · 근거: 머리명사 펀드/ETF
3. [Ground] KG 개체 매핑 — '미래에셋자산운용' → Org_00080008 (Organization) → public_funds.or_co_xtn_itt_cd='00080008' · domestic_etfs.cu_fund_mgmt_co='미래에셋' · domestic_etfs.cu_fund_mgmt_co='TIGER' · domestic_etfs.ref_fund_mgmt_co='Mirae Asset Global Investments Co Ltd' … 외 1종 / 'ETF' → FundAttr_M113 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,M113,%' / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs', 'public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 domestic_etfs, public_funds · 28,815자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT '공모펀드' AS 구분, COUNT(*) AS 개수 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN ('미래에셋', 'TIGER', '미래에셋TIGER') AND pd_sale_yn = 1 AND pd_lste_dt = 99991231 AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 30
10. [Guard] SQL 기각 — 스키마에 없는 컬럼: pd_sale_yn(→ domestic_etfs 컬럼이다. 이 테이블에는 없다), pd_lste_dt(→ domestic_etfs 컬럼이다. 이 테이블에는 없다)
11. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 3.4s)
12. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
13. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT '국내 ETF' AS 구분, COUNT(*) AS 개수 FROM domestic_etfs WHERE cu_fund_mgmt_co IN ('미래에셋', 'TIGER', '미래에셋TIGER') AND pd_sale_yn = 1 AND pd_grp_no = 'ETF' LIMIT 30
14. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
15. [Execute] 1행 조회 (상한 30)
16. [Answer] 답변 생성 완료 — 답변 규칙 7,122자 적용 (domestic_etfs, public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
구분 | 개수
국내 ETF | 191
```

</details>

---

## X10. 이름이 KB로 시작하는 공모펀드는 몇 개고 그중 KB자산운용이 운용하는 건 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 3.1s

**answer**

```text
KB로 시작하는 공모펀드는 총 625개가 있으며, 그중 KB자산운용이 운용하는 펀드의 수는 확인할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 47
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,446자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 외부 테이블 JOIN 주입 — mtco_nm → mgmt_co_nm(유일 근사) · mgmt_co_nm 은 ext_fund_page 컬럼 → LEFT JOIN 주입 (2026-09-02 R2·S11 재검: mtco_nm 환각 3라운드 연속 1차 기각으로 재생성 예산 소진 → 거절)
7. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(*) as cnt FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE prvo_pbff_desc = '공모' and (sale_yn = '판매중' or sale_yn is null) AND (REPLACE(itm_nm,' ','') LIKE 'KB%' OR mgmt_co_nm LIKE 'KB%') LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
cnt
625
```

</details>

---

## X11. 동양자산운용이 운용하는 공모펀드 알려줘

### 3라운드(1e0e641) — HTTP 200 · 9.1s

**answer**

```text
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 조건 중 일부는 수록된 데이터에 해당하는 상품 자체가 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '동양자산운용' → Org_00040007 (Organization, 정식명 우리자산운용) → public_funds.or_co_xtn_itt_cd='00040007' ℹ '동양자산운용' 은(는) 구상호 — 현재 우리자산운용(코드 00040007) 기준으로 조회한다
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,446자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 목록 펀드 묶기 — ORDER BY 없는 펀드 목록을 펀드키 GROUP BY + 순자산순 대표행으로 (2026-09-02 R3 재검: LIMIT 30 이 임의 30행 + 같은 펀드 C2·C5 별개 나열)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT DISTINCT itm_no, itm_nm, COUNT(*) AS "클래스수", MAX(fd_nast_suma) AS fd_nast_suma, CAST(fd_nast_suma/100000000 AS INTEGER) || '억원' AS "순자산_억원" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN (SELECT or_co_xtn_itt_cd FROM ext_fund_page WHERE mgmt_co_nm LIKE '%동양%' AND LENGTH(mgmt_co_nm) > 2) AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY fd_nast_suma DESC LIMIT 30
10. [Guard] SQL 기각 — 여러 테이블에 있는 컬럼을 한정하지 않았다(실행 시 ambiguous 오류): itm_no — 테이블 별칭을 붙이고 p.itm_no 처럼 모두 한정한다
11. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 5.5s)
12. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT DISTINCT p.itm_no, p.itm_nm FROM public_funds p JOIN ext_fund_page e ON e.itm_no = p.itm_no WHERE e.mgmt_co_nm LIKE '%동양%' AND p.prvo_pbff_desc = '공모' AND p.sale_yn = '판매중' LIMIT 30
13. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
14. [Execute] 0행 조회 (상한 30)
15. [Diagnose] 0행 원인 — 조건별 단독 조회: e.mgmt_co_nm LIKE '%동양%' → 0건 / p.prvo_pbff_desc = '공모' → 10,558건 / p.sale_yn = '판매중' → 8,408건. 값 자체가 없는 조건: e.mgmt_co_nm LIKE '%동양%'.
16. [Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_no | itm_nm

```

</details>

---

## X12. 슈로더가 운용하는 공모펀드는 역외펀드까지 포함하면 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 5.8s

**answer**

```text
질의를 안전하게 실행할 수 없어 답변을 제공하지 못했습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 33
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '역외펀드' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 11,467자 · 구성: 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = 10000000 AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%역외펀드%' LIMIT 30
11. [Guard] SQL 기각 — 코드 컬럼 리터럴 검증 실패: or_co_xtn_itt_cd = 10000000 (따옴표 없는 숫자 — 코드는 '10000000' 같은 문자열) — 코드는 'KG 개체 매핑' 의 값만 쓴다. 매핑이 없으면 지어내지 말고 REFUSE: 로 답한다
12. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 2.1s)
13. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
14. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
15. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE or_co_xtn_itt_cd = 10000000 AND prvo_pbff_desc = '공모' AND REPLACE(itm_nm,' ','') LIKE '%역외펀드%' LIMIT 30
16. [Guard] 재생성 후에도 실패 — 코드 컬럼 리터럴 검증 실패: or_co_xtn_itt_cd = 10000000 (따옴표 없는 숫자 — 코드는 '10000000' 같은 문자열) — 코드는 'KG 개체 매핑' 의 값만 쓴다. 매핑이 없으면 지어내지 말고 REFUSE: 로 답한다
17. [Decision] 값이 DB 에 없거나 SQL 이 안전하지 않아 종료 (조건을 완화하지 않는다)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## X13. KB자산운용 펀드의 수탁사 분포 알려줘

### 3라운드(1e0e641) — HTTP 200 · 45.7s

**answer**

```text
KB자산운용 펀드의 수탁사 분포는 다음과 같습니다.

- 주식형의 경우, 주로 00020088(42개), 00020020(15개), 00020027(8개) 등의 순으로 많은 펀드가 분포되어 있으며,
- 채권형은 00020088(23개), 00020020(11개), 00050004(11개) 등에 분산되어 있고,
- 채권혼합형은 00020088(11개), 00050004(8개) 등에 집중되어 있습니다.
- 기타 분류의 펀드들도 다수 있으나, 이들은 상대적으로 수가 적습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,050자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COALESCE(zrin_btyp_nm,'(제로인 미수록)') AS asset_class, trusc_xtn_itt_cd, COUNT(*) as class_count FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (TRIM(or_co_xtn_itt_cd) = '00040035') GROUP BY 1, 2 LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 30행 조회 (상한 30)
12. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
asset_class | trusc_xtn_itt_cd | class_count
(제로인 미수록) | 00020011 | 2
(제로인 미수록) | 00020020 | 2
(제로인 미수록) | 00020027 | 7
(제로인 미수록) | 00020054 | 7
(제로인 미수록) | 00020088 | 4
(제로인 미수록) | 00050004 | 1
MMF | 00020081 | 1
MMF | 00020088 | 4
MMF | 00050004 | 2
기타 | 00020023 | 2
기타 | 00050004 | 1
외화 MMF | 00020027 | 4
주식형 | 00020003 | 12
주식형 | 00020011 | 23
주식형 | 00020020 | 15
주식형 | 00020023 | 9
주식형 | 00020027 | 8
주식형 | 00020081 | 17
주식형 | 00020088 | 42
주식형 | 00050004 | 4
주식혼합형 | 00020020 | 2
주식혼합형 | 00020088 | 6
채권형 | 00020011 | 20
채권형 | 00020020 | 11
채권형 | 00020088 | 23
채권형 | 00050004 | 11
채권혼합형 | 00020020 | 27
채권혼합형 | 00020081 | 7
채권혼합형 | 00020088 | 11
채권혼합형 | 00050004 | 8
```

</details>

---

## X14. 삼성코리아대표 펀드의 수탁사는 어디야?

### 3라운드(1e0e641) — HTTP 200 · 3.7s

**answer**

```text
제공된 데이터에 삼성코리아대표 펀드의 수탁사에 대한 정보가 수록되어 있지 않습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '삼성코리아대표' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,765자 · 구성: 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
8. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(trusc_xtn_itt_cd) AS trusc_xtn_itt_cd, MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE REPLACE(itm_nm,' ','') LIKE '%삼성코리아대표%' AND sale_yn = '판매중' AND prvo_pbff_desc = '공모' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 2행 조회 (상한 30)
12. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | trusc_xtn_itt_cd | 대표번호
KR5114450100 | 삼성코리아대표분할매수증권투자신탁 1[주식혼합] | 1 | 1 | 00020020 | 030200209302
KR5114450011 | 삼성코리아대표증권자투자신탁 제1호[주식](A) | 9 | 9 | 00020081 | 2000102M1400
```

</details>

---

## X15. 중국에 투자하는 공모펀드와 국내 ETF는 각각 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 8.0s

**answer**

```text
중국에 투자하는 공모펀드는 63개, 국내 ETF는 확인할 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 31
2. [Route] 상품군 — domestic_etfs, public_funds · 근거: 머리명사 펀드/ETF
3. [Ground] KG 개체 매핑 — 'ETF' → FundAttr_M113 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,M113,%' / '중국' → Region_China (Region) [+후손 1: Region_HongKong] → domestic_etfs.wu_inv_rgn='중국' · domestic_etfs.ref_geo_focus='China' · domestic_etfs.ref_geo_focus='Greater China' / '국내' → (건너뜀) 국내 = 상장 시장 · 투자지역 필터로 쓰지 않는다
4. [Gate] 통과 — 대상 테이블 ['domestic_etfs', 'public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
5. [Plan] 근거문서 조립 — 대상 domestic_etfs, public_funds · 28,230자 · 구성: KG 개체 매핑 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT '중국에 투자하는 공모펀드' AS 구분, COUNT(*) FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) IN (SELECT or_co FROM domestic_etfs WHERE wu_inv_rgn = '중국') AND prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 30
10. [Guard] SQL 기각 — 스키마에 없는 컬럼: or_co(→ ext_fund_holdings 컬럼이다. 이 테이블에는 없다)
11. [Plan] 재생성 1회 — 문제를 근거문서에 붙여 다시 요청 (누적 3.0s)
12. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
13. [Plan] 재생성 SQL — 아래 문장을 실행합니다
SELECT '중국에 투자하는 공모펀드' AS 구분, COUNT(*) FROM public_funds WHERE prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 2
14. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
15. [Execute] 1행 조회 (상한 30)
16. [Answer] 답변 생성 완료 — 답변 규칙 7,122자 적용 (domestic_etfs, public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
구분 | COUNT(*)
중국에 투자하는 공모펀드 | 63
```

</details>

---

## X16. ETF에 투자하는 공모펀드는 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 65.6s

**answer**

```text
조회 조건에 해당하는 공모펀드는 0개(클래스 0개)입니다 (판매중·공모 기준, 기준일 2026-08-22).
(각 조건의 개체·값은 데이터에 실재하며 그 교집합이 0입니다)
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'ETF' → FundAttr_M113 (FundAttribute) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,M113,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,608자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 속성 태그 확정식 — 설정형태 어휘(개방형·폐쇄형·단위형·추가형)를 KG FundAttribute 토큰 canon 으로 주입, 같은 낱말의 타 컬럼 절 제거 (KG-017 han_clas_policies LIKE '%폐쇄형%' → 0행 '0개' · KG-018 직교 축 폐기)
7. [Guard] 펀드단위 집계 교체 — 펀드 개수 질의의 COUNT(*) 를 COUNT(DISTINCT 펀드키)+클래스수 병기로 (2026-09-01 FND-034 실측: 클래스 850 을 '펀드 850개' 로 답함 — 구분 누락 6번째 재발)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(DISTINCT printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no)) AS "펀드수", COUNT(*) AS "클래스수" FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND ',' || prfd_attr_cds || ',' LIKE '%,M113,%' LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Answer] 개수 답변 기계 조립 — 펀드수/클래스수 1행은 HCX 없이 옮긴다 (2026-09-02 R5 재검: 클래스 541 을 답변기가 버림 — 034 재검은 병기, 비결정)
```

</details>

<details><summary>retrieved_context</summary>

```text
펀드수 | 클래스수
0 | 0
```

</details>

---

## X17. 미래에셋차이나솔로몬 2호는 클래스가 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 5.4s

**answer**

```text
제공된 데이터에 따르면 미래에셋차이나솔로몬 2호의 클래스 개수에 대한 정보가 없습니다. 따라서 답변을 제공할 수 없습니다. 양해 부탁드립니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — 미특정 · 근거: 미특정 → 마스터 4테이블 (HCX 가 FROM 으로 판단)
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008' · domestic_etfs.cu_fund_mgmt_co='미래에셋' · domestic_etfs.cu_fund_mgmt_co='TIGER' · domestic_etfs.ref_fund_mgmt_co='Mirae Asset Global Investments Co Ltd' … 외 1종
4. [Gate] 통과 — 대상 테이블 미특정
5. [Plan] 근거문서 조립 — 대상 마스터 4테이블 · 53,392자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Route] SQL 사후 보정 — FROM public_funds → 그 상품군의 답변 규칙·이름 필터 적용 · 재생성 문서도 그 상품군으로 (2026-09-02 R7 재검: 미특정 경로는 답변 규칙이 4도메인으로 희석되고 상품명 필터 가드가 꺼진다)
7. [Ground] 잔여 상품 고유명 '차이나솔로몬' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (사후 보정 경로)
8. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
9. [Guard] 호수 경계 주입 — N호 조건을 GLOB '*[^0-9]N호*' 확정식으로 교체 (2026-09-01 FND-032 실측: HCX 가 경계식을 `'2호' IN (a OR b)` 로 옮겨 항상-거짓 0행)
10. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
11. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
12. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(*) FROM public_funds WHERE sale_yn = '판매중' AND prvo_pbff_desc = '공모' AND (REPLACE(itm_nm,' ','') LIKE '%미래에셋차이나솔로몬2%') AND (REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2호*' OR REPLACE(itm_nm,' ','') GLOB '*[^0-9.]2[([]*') LIMIT 30
13. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
14. [Execute] 1행 조회 (상한 30)
15. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(*)
0
```

</details>

---

## X18. 미래에셋코어테크증권자투자신탁의 모펀드는 뭐야?

### 3라운드(1e0e641) — HTTP 200 · 4.6s

**answer**

```text
미래에셋코어테크증권자투자신탁의 모펀드는 '**미래에셋코어테크증권모투자신탁(주식)**' 입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 25
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Ground] 잔여 상품 고유명 '코어테크증권자투자신탁' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
7. [Plan] 근거문서 조립 — 대상 public_funds · 12,517자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
8. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
9. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT mother_fund_names_raw FROM public_funds JOIN ext_fund_page ON public_funds.itm_no = ext_fund_page.itm_no WHERE TRIM(public_funds.or_co_xtn_itt_cd) = '00080008' AND REPLACE(public_funds.itm_nm,' ','') LIKE '%코어테크증권자투자신탁%' LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 20행 조회 (상한 30)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
mother_fund_names_raw
미래에셋코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
Index모투자신탁;미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
미래에셋코어테크증권모투자신탁(주식)
미래에셋차이나코어테크증권모투자신탁(주식)
```

</details>

---

## X19. 2025년에 설정된 공모펀드는 몇 개야?

### 3라운드(1e0e641) — HTTP 200 · 51.4s

**answer**

```text
2025년에 설정된 공모펀드는 총 305개입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Plan] 근거문서 조립 — 대상 public_funds · 12,166자 · 구성: 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] 외부 테이블 JOIN 주입 — estb_dt → estb_dt(유일 근사) · estb_dt 은 ext_fund_page 컬럼 → LEFT JOIN 주입 (2026-09-02 R2·S11 재검: mtco_nm 환각 3라운드 연속 1차 기각으로 재생성 예산 소진 → 거절)
8. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(*) FROM public_funds LEFT JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE estb_dt BETWEEN 20250101 AND 20251231 AND prvo_pbff_desc = '공모' AND sale_yn = '판매중' LIMIT 30
9. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
10. [Execute] 1행 조회 (상한 30)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
COUNT(*)
305
```

</details>

---

## X20. 가장 최근에 설정된 공모펀드 2개 알려줘

### 3라운드(1e0e641) — HTTP 200 · 6.3s

**answer**

```text
가장 최근에 설정된 공모펀드 2개는 다음과 같습니다.

1. KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A - 설정일: 2026년 6월 12일
2. 미래에셋국민참여형국민성장혼합자산투자신탁(사모투자재간접형) 종류 C1-e (서민형) - 설정일: 2026년 6월 12일

두 펀드 모두 동일한 날짜에 설정되었으며, 이 정보가 제공할 수 있는 최신 정보입니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Route] 설명서 항목 질의 — ext_fund_page(설정일·환매조건·설명서 보수) 조인 대상에 포함
4. [Ground] KG 개체 매핑 — 매칭 없음 (상품군 안에 해당 값 없음 → 규칙의 LIKE 조회로)
5. [Gate] 통과 — 대상 테이블 ['public_funds'] · 교차질의(복수 상품군/구성종목 조인 — ext_* 테이블 허용, 기준일 병기)
6. [Plan] 근거문서 조립 — 대상 public_funds · 12,166자 · 구성: 교차질의 조인 키 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT itm_nm, estb_dt FROM public_funds JOIN ext_fund_page ON ext_fund_page.itm_no = public_funds.itm_no WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' ORDER BY estb_dt DESC LIMIT 2
8. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
9. [Execute] 2행 조회 (상한 30)
10. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
11. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
itm_nm | estb_dt
KB K-성장과 지배구조 30 목표전환 증권 투자신탁(채권혼합) A | 20260612
미래에셋국민참여형국민성장혼합자산투자신탁(사모투자재간접형) 종류C1-e (서민형) | 20260612
```

</details>

---

## X21. 스페인에 투자하는 공모펀드 있어?

### 3라운드(1e0e641) — HTTP 200 · 2.8s

**answer**

```text
조건에 해당하는 상품이 데이터에서 확인되지 않습니다. 조건 각각에 해당하는 상품은 있으나, 모든 조건을 동시에 만족하는 상품은 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 18
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '스페인' → Country_ESP (Country) → ',' || public_funds.prfd_attr_cds || ',' LIKE '%,ESP,%'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 10,600자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] 국가 태그 확정식 — 국가어 질의의 지역·설립국·태그·속성명·이름 OR 절을 KG Country 토큰 canon 하나로 접음 (KG 1R S3·3R C: 어떤 태그를 썼든 교정 · '유형' 이면 zrin_ptn_nm) · 전: WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND ',' || prfd_attr_cds || ',' LIKE '%,ESP,%' LIMIT 30
7. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
8. [Guard] 펀드 근거컬럼 보강 — SELECT 에 위험등급명·제로인 태그 병기 (등급 방향 서술·극단값 주의 문구의 재료 — FND-019 채점 실측)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MIN(rptt_ksd_itm_no) AS 대표번호, prfd_attr_cds FROM public_funds WHERE prvo_pbff_desc = '공모' AND sale_yn = '판매중' AND (',' || prfd_attr_cds || ',' LIKE '%,ESP,%' OR REPLACE(itm_nm,' ','') LIKE '%스페인%') GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 0행 조회 (상한 30)
12. [Diagnose] 0행 원인 — 조건별 단독 조회: prvo_pbff_desc = '공모' → 14,716건 / sale_yn = '판매중' → 10,962건 / (',' || prfd_attr_cds || ',' LIKE '%,ESP,%' OR REPLACE(itm_nm,' ','') LIKE '%스페인%') → 7건. 각 조건은 존재하나 동시에 만족하는 상품이 없습니다.
13. [Decision] 조회 결과 0건 — 환각 방지 규칙에 따라 '확인할 수 없음'
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | 대표번호 | prfd_attr_cds

```

</details>

---

## X22. KB자산운용 펀드 중 국민은행이 수탁하는 공모펀드는 몇 개야? 실제 수탁사는 어디야?

### 3라운드(1e0e641) — HTTP 200 · 4.9s

**answer**

```text
제공된 데이터에는 KB자산운용 펀드 중 국민은행이 수탁하는 공모펀드의 개수에 대한 정보가 포함되어 있지 않습니다. 또한 실제 수탁사에 대한 정보 역시 '미수록'으로 표시되어 있어 확인할 수 없습니다. 따라서 이에 대해 답변을 드릴 수 없습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 47
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — 'KB자산운용' → Org_00040035 (Organization) → public_funds.or_co_xtn_itt_cd='00040035' / '국민은행' → Org_trustee_00020004 (Organization) → public_funds.trusc_xtn_itt_cd='00020004'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Plan] 근거문서 조립 — 대상 public_funds · 11,516자 · 구성: KG 개체 매핑 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
6. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
7. [Guard] 펀드 기본모수 주입 — 랭킹 SQL 에 판매중·공모 조건이 없어 보정 (2026-08-31 paired v2: 규칙 실려도 미적용이 answer 실패 1순위)
8. [Guard] LIMIT 누락 — 상한 30 로 보정 (집계 질의는 LIMIT 을 쓰지 않는다)
9. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT COUNT(*) as cnt, trusc_xtn_itt_cd as custodian FROM public_funds WHERE sale_yn = '판매중' AND (TRIM(or_co_xtn_itt_cd) = '00040035' AND prvo_pbff_desc = '공모' AND TRIM(trusc_xtn_itt_cd) = '00020004') LIMIT 30
10. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
11. [Execute] 1행 조회 (상한 30)
12. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
13. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
cnt | custodian
0 | 
```

</details>

---

## X23. 미래에셋코어테크 펀드 운용역이 누구야?

### 3라운드(1e0e641) — HTTP 200 · 0.2s

**answer**

```text
펀드 운용역(펀드매니저) 정보는 마스터·설명서 수집분에 없어 답할 수 없습니다. 운용사(운용회사 코드 → 법인명)는 안내할 수 있습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 21
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 기각 — 온톨로지 ABSENT — public_funds 에 hasFundManager 속성 없음 · 질문의 '운용역' (enums absent_properties → HCX 0회)
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## X24. 미래에셋코어테크 펀드 기준가 추이 알려줘

### 3라운드(1e0e641) — HTTP 200 · 0.3s

**answer**

```text
기준가는 기준일 단일 스냅샷(bns_bpr)만 있고 시계열(추이·변동·과거 기준가)은 수록되어 있지 않습니다. 기준일 현재 기준가와 기간 수익률(1개월~5년 누적)은 안내할 수 있습니다.
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 22
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 기각 — 온톨로지 ABSENT — public_funds 에 hasNavHistory 속성 없음 · 질문의 '기준가 추이' (enums absent_properties → HCX 0회)
5. [Decision] HCX 호출 없이 종료 (근거는 Gate 단계)
```

</details>

<details><summary>retrieved_context: (없음)</summary></details>

---

## X25. 미래에셋코어테크 펀드 기준가 알려줘

### 3라운드(1e0e641) — HTTP 200 · 8.8s

**answer**

```text
미래에셋코어테크 펀드의 기준가는 다음과 같습니다.

1. 미래에셋코어테크증권자투자신탁(주식) 종류 A: 4902.86원
2. 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류 A: 3321.17원
3. 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류 A-e: 1142.92원
4. 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류 A-e: 1211.85원
5. 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류 A: 2122.06원
6. 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류 A-e: 1399.03원
```

<details><summary>think_trace</summary>

```text
1. [Normalize] 질의 정규화 — 길이 19
2. [Route] 상품군 — public_funds · 근거: 머리명사 펀드
3. [Ground] KG 개체 매핑 — '미래에셋' → Org_00080008 (Organization, 정식명 미래에셋자산운용) → public_funds.or_co_xtn_itt_cd='00080008'
4. [Gate] 통과 — 대상 테이블 ['public_funds']
5. [Ground] 잔여 상품 고유명 '코어테크' — KG 매핑에 없는 이름이라 itm_nm 검색을 강제한다 (2026-08-31 밤 FND-016: 브랜드만 매핑되고 상품명이 소실돼 무관한 펀드 값이 답으로 나간 사고)
6. [Plan] 근거문서 조립 — 대상 public_funds · 9,918자 · 구성: KG 개체 매핑 + 🔴 상품 고유명 + 도메인 규칙 + 되묻기 규칙 + 답변불가 규칙 + 스키마
7. [Guard] TRIM 보정 — 고정폭 패딩 컬럼(bd_knd·pd_pbcm)의 무TRIM 비교를 TRIM 비교로 교체 (무TRIM IN 은 16행 vs TRIM 2,031행 실측)
8. [Guard] 종목명 공백 무시 매칭 — itm_nm LIKE 를 REPLACE(itm_nm,' ','') 비교로 교체 (2026-08-31 밤 실측: '미래에셋 코어테크' 띄어쓰기로 14행을 통째로 놓쳤다)
9. [Guard] 개별 조회 펀드 묶기 — 이름 검색 결과를 펀드키 GROUP BY 로 묶어 클래스수·최고/최저값 병기 (2026-09-02 R4 재검: 6펀드 37클래스를 1클래스로 답함 3회째 · R6 LIMIT 1 이라 클래스수 병기 불가)
10. [Plan] SQL 생성 — 아래 문장을 실행합니다
SELECT MIN(itm_no) AS 대표_itm_no, MIN(TRIM(itm_nm)) AS itm_nm, COUNT(*) AS "클래스수", SUM(CASE WHEN sale_yn = '판매중' THEN 1 ELSE 0 END) AS "판매중클래스수", MAX(bns_bpr) AS bns_bpr, MIN(rptt_ksd_itm_no) AS 대표번호 FROM public_funds WHERE TRIM(or_co_xtn_itt_cd) = '00080008' AND REPLACE(itm_nm,' ','') LIKE '%코어테크%' AND sale_yn = '판매중' GROUP BY printf('%08d', CAST(or_co_xtn_itt_cd AS INTEGER)) || '/' || COALESCE(CASE WHEN length(trim(mtco_itm_no)) >= 7 THEN trim(mtco_itm_no) ELSE substr('0000000' || trim(mtco_itm_no), -7) END, itm_no) ORDER BY MIN(length(REPLACE(itm_nm,' ',''))) ASC, 2 ASC LIMIT 30
11. [Guard] SQL 검사 통과 (SELECT 단일문 · 테이블 화이트리스트 · LIMIT · WHERE 값 사전 대조)
12. [Execute] 6행 조회 (상한 30)
13. [Guard] 면책 문구 제거 — '금융기관 문의·전문가 상담' 류 문장을 답변에서 걷어냄 (answer_rules 금지 규칙 미준수 5회 재발 — 2026-09-01 결정층行)
14. [Answer] 답변 생성 완료 — 답변 규칙 3,171자 적용 (public_funds)
```

</details>

<details><summary>retrieved_context</summary>

```text
대표_itm_no | itm_nm | 클래스수 | 판매중클래스수 | bns_bpr | 대표번호
KR5153450780 | 미래에셋코어테크증권자투자신탁(주식) 종류A | 10 | 10 | 4902.86 | 031910536840
KR5153450910 | 미래에셋코어테크청년소득공제증권자투자신탁(주식) 종류A | 4 | 4 | 3321.17 | 031910536890
KR5153451150 | 미래에셋차이나코어테크증권자투자신탁(주식)(H) 종류A-e | 5 | 5 | 1142.92 | 031910539310
KR5153451160 | 미래에셋차이나코어테크증권자투자신탁(주식)(UH) 종류A-e | 5 | 5 | 1211.85 | 031910539320
KR5153490560 | 미래에셋글로벌코어테크EMP증권자투자신탁(주식-재간접형)종류A | 13 | 13 | 2122.06 | 031910482550
KR5153490736 | 미래에셋글로벌코어테크 EMP증권자투자신탁2호(주식-재간접형) 종류A-e | 4 | 4 | 1399.03 | 031910539100
```

</details>
