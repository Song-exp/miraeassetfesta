# -*- coding: utf-8 -*-
"""공모펀드 속성코드(prfd_attr_cds) ↔ 명칭 코드북 생성 — 2차 데이터 `prfd_attr_search_text` 에서 도출

원리: prfd_attr_search_text 는 "D102 국내위탁판매 V101 국내 C101 추가 C103 개방" 처럼
      `코드 명칭` 쌍이 공백으로 이어진 문자열이다 (코드 = 대문자 1 + 숫자 3).
      명칭 뒤에 ISO3 국가코드 + 한글국명("CHN 중국")이 붙는 행이 있는데 이는 속성코드가 아니라 별도 국가 태그다.
      ⚠️ prfd_attr_cds 와 zrin_attr_nms 는 위치 대응이 아니므로(public_funds.yaml 참조) 이 텍스트가 유일한 원천.

검증: 도출된 명칭이 zrin_attr_nms(콤마 구분 명칭 집합)에 실제로 등장하는지 행 단위로 대조 → `verified_rate`.

출력:
  ontology/codebooks/fund_attr_code.csv    code,name,axis,axis_name,n_rows,n_selling,verified_rate,alt_names,status,as_of
  ontology/codebooks/fund_country_tag.csv  iso3,name_ko,n_rows,as_of
사용: python scripts/gen_fund_attr_codebook.py
"""
import csv, os, re, sqlite3, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "financial_products.db")
OUT_CODE = os.path.join(ROOT, "ontology", "codebooks", "fund_attr_code.csv")
OUT_CTRY = os.path.join(ROOT, "ontology", "codebooks", "fund_country_tag.csv")
AS_OF = "2026-08-22"

# 축 이름은 코드 첫 글자별 명칭 분포를 보고 붙인 **추정** (주최 코드북 제공 불가 확정 — 8/24 공지)
AXIS_NAME = {
    "C": "설정형태(추가/단위·개방/폐쇄)", "D": "판매채널", "E": "가입대상", "F": "세제혜택유형",
    "G": "세제특례·연금상품", "M": "펀드구조(모자/종류형/FoFs 등)", "N": "테마·컨셉", "O": "섹터",
    "P": "투자스타일·채권듀레이션", "Q": "실물자산", "R": "특수자산·전략자산", "S": "운용전략",
    "T": "TDF 빈티지", "V": "투자지역구분(국내/국외/국내외)", "W": "세부투자지역",
}
CODE = re.compile(r"^[A-Z]\d{3}$")
ISO3 = re.compile(r"^[A-Z]{3}$")


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "select prfd_attr_search_text, zrin_attr_nms, sale_yn from public_funds where prfd_attr_search_text is not null"
    ).fetchall()
    names = collections.defaultdict(collections.Counter)   # code -> name -> n
    sell = collections.Counter()
    ctry = collections.Counter()                            # (iso3, ko) -> n
    verified = collections.Counter(); seen = collections.Counter()
    for text, nms, sale in rows:
        nmset = {x.strip() for x in (nms or "").split(",") if x.strip()}
        toks = text.split(); i = 0
        while i < len(toks):
            if not CODE.match(toks[i]):
                i += 1; continue
            code = toks[i]; j = i + 1; body = []
            while j < len(toks) and not CODE.match(toks[j]):
                body.append(toks[j]); j += 1
            # 뒤쪽 "ISO3 한글국명" 쌍은 국가 태그로 분리 (여러 개 가능)
            k = len(body)
            while k >= 2 and ISO3.match(body[k - 2]):
                ctry[(body[k - 2], body[k - 1])] += 1; k -= 2
            name = " ".join(body[:k])
            names[code][name] += 1
            if sale == "판매중": sell[code] += 1
            seen[code] += 1
            if name in nmset: verified[code] += 1
            i = j
    out = []
    for code in sorted(names):
        top, n = names[code].most_common(1)[0]
        alts = [f"{k}({v})" for k, v in names[code].most_common()[1:4]]
        vr = verified[code] / max(seen[code], 1)
        status = "confirmed" if vr >= 0.95 and n >= 5 else ("confirmed_low_n" if vr >= 0.95 else "check")
        out.append(dict(code=code, name=top, axis=code[0], axis_name=AXIS_NAME.get(code[0], "(미정)"),
                        n_rows=seen[code], n_selling=sell[code], verified_rate=f"{vr:.3f}",
                        alt_names="; ".join(alts), status=status, as_of=AS_OF))
    with open(OUT_CODE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    with open(OUT_CTRY, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["iso3", "name_ko", "n_rows", "as_of"])
        for (iso, ko), n in sorted(ctry.items(), key=lambda x: -x[1]): w.writerow([iso, ko, n, AS_OF])
    st = collections.Counter(r["status"] for r in out)
    print(f"속성코드 {len(out)}종 → {dict(st)} · 축 {sorted({r['axis'] for r in out})}")
    print(f"국가 태그 {len(ctry)}종 (상위: {ctry.most_common(5)})")
    low = [r for r in out if r["status"] == "check"]
    print("검증률 낮은 코드:", [(r["code"], r["name"], r["verified_rate"], r["n_rows"]) for r in low][:15])
    multi = [(r["code"], r["name"], r["alt_names"]) for r in out if r["alt_names"]]
    print("복수 명칭 코드:", multi[:10])


if __name__ == "__main__":
    main()
