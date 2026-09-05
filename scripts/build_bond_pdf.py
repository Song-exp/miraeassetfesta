# 채권 최종 원고(28_채권_최종원고.md) → HTML → PDF.
#
# 쓰는 법  ./.venv/Scripts/python.exe scripts/build_bond_pdf.py
# 산출     docs/기술제안서/28_채권_최종원고.html · docs/기술제안서/28_채권_최종원고.pdf
#
# 마크다운은 python-markdown, 조판은 headless Chrome(print-to-pdf). 그림(figures/*.svg)은
# HTML 에 인라인으로 심어 외부 파일 의존을 없앤다. 한글 폰트는 시스템의 맑은 고딕.
import io, os, re, sys, subprocess, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
import markdown  # noqa: E402

SRC = "docs/기술제안서/28_채권_최종원고.md"
OUT_HTML = "docs/기술제안서/28_채권_최종원고.html"
OUT_PDF = "docs/기술제안서/28_채권_최종원고.pdf"
FIG_DIR = "docs/기술제안서"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

CSS = """
@page { size: A4; margin: 22mm 18mm 22mm 18mm; }
html { font-size: 10.5pt; }
body { font-family: "Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", sans-serif; color: #1a1a1a;
       line-height: 1.62; word-break: keep-all; max-width: 100%; margin: 0; }
h1 { font-size: 20pt; margin: 0 0 14pt; padding-bottom: 6pt; border-bottom: 2px solid #1a1a1a; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 14.5pt; margin: 22pt 0 8pt; color: #1a1a1a; }
h3 { font-size: 12pt; margin: 16pt 0 6pt; color: #333; }
p  { margin: 0 0 8pt; text-align: justify; }
blockquote { margin: 0 0 12pt; padding: 8pt 12pt; border-left: 3px solid #999; background: #f7f7f7; color: #444; font-size: 9.5pt; }
blockquote p { margin: 0 0 4pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 9.3pt; page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 4pt 6pt; vertical-align: top; }
th { background: #efefef; font-weight: bold; }
code { font-family: Consolas, "D2Coding", monospace; font-size: 9pt; background: #f2f2f2; padding: 0 3pt; border-radius: 2px; }
pre { background: #f5f5f5; border: 1px solid #ddd; padding: 8pt 10pt; font-size: 8.8pt; line-height: 1.45;
      overflow-x: hidden; white-space: pre-wrap; word-break: break-all; page-break-inside: avoid; margin: 6pt 0 12pt; }
pre code { background: none; padding: 0; }
figure { margin: 10pt 0 14pt; text-align: center; page-break-inside: avoid; }
figure svg { max-width: 100%; height: auto; }
figcaption { font-size: 9pt; color: #555; margin-top: 4pt; }
hr { border: 0; border-top: 1px solid #ccc; margin: 16pt 0; }
strong { color: #111; }
em { color: #333; }
.cover { text-align: center; padding-top: 120pt; page-break-after: always; }
.cover h1 { border: 0; font-size: 26pt; page-break-before: avoid; }
.cover .sub { font-size: 13pt; color: #444; margin-top: 8pt; }
.cover .meta { font-size: 10pt; color: #666; margin-top: 60pt; line-height: 1.8; }
"""


def inline_figures(html: str) -> str:
    """<img src="figures/x.svg" alt="..."> → <figure><svg…/><figcaption>alt</figcaption></figure>"""
    def repl(m):
        src, alt = m.group(1), m.group(2)
        path = os.path.join(FIG_DIR, src)
        if not os.path.exists(path):
            return f'<p style="color:#b00">[그림 없음: {src}]</p>'
        svg = io.open(path, encoding="utf-8").read()
        svg = re.sub(r"^<\?xml[^>]*\?>\s*", "", svg)
        return f"<figure>{svg}<figcaption>{alt}</figcaption></figure>"
    return re.sub(r'<p>\s*<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"[^>]*/?>\s*</p>', repl, html)


def build_html(md_text: str) -> str:
    # 조판 안내 인용문(첫 blockquote)은 PDF 에서 뺀다 — 편집자용 메모
    md_text = re.sub(r"^> \*\*조판 안내\*\*.*?(?=\n\n---)", "", md_text, count=1, flags=re.S | re.M)
    md_text = md_text.replace("# 기술 제안서 — 국내채권 도메인\n", "", 1)
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    body = inline_figures(body)
    cover = """
<div class="cover">
  <h1>기술 제안서 — 국내채권 도메인</h1>
  <div class="sub">LLM 이 SQL 을 틀리지 않게 만드는 세 층의 온톨로지</div>
  <div class="meta">
    데이터 as-of 2026-08-22 · 판정 기준일 2026-08-24<br/>
    수치 실측 2026-09-06 · 재현 절차 §6.4
  </div>
</div>"""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>기술 제안서 — 국내채권 도메인</title><style>{CSS}</style></head>
<body>{cover}{body}</body></html>"""


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    return shutil.which("chrome") or shutil.which("chromium")


def main():
    md_text = io.open(SRC, encoding="utf-8").read()
    html = build_html(md_text)
    io.open(OUT_HTML, "w", encoding="utf-8").write(html)
    print(f"HTML → {OUT_HTML} ({len(html):,}자)")

    chrome = find_chrome()
    if not chrome:
        print("Chrome 을 찾지 못해 PDF 는 건너뜀 (HTML 만 생성)")
        return 1
    url = "file:///" + os.path.abspath(OUT_HTML).replace("\\", "/")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
           "--virtual-time-budget=5000",
           f"--print-to-pdf={os.path.abspath(OUT_PDF)}", url]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if os.path.exists(OUT_PDF):
        print(f"PDF  → {OUT_PDF} ({os.path.getsize(OUT_PDF):,} bytes)")
        return 0
    print("PDF 생성 실패:", r.stderr[-800:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
