#!/usr/bin/env python3
"""저장된 하루치 JSON을 인쇄용 HTML과 PDF로 만든다.

    python render.py                오늘자
    python render.py --date 2026-07-28
    python render.py --no-pdf       HTML만
"""
from __future__ import annotations

import argparse, html, json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / 'docs' / 'data'
OUT = ROOT / 'docs' / 'issue'
KST = timezone(timedelta(hours=9))
WEEK = '월화수목금토일'

CSS = """
@page { size: A4; margin: 16mm 15mm 14mm; }
* { box-sizing: border-box; }
body { margin:0; font-family:'Nanum Gothic','Malgun Gothic','Apple SD Gothic Neo',sans-serif;
       font-size:10.5pt; line-height:1.5; color:#111; }
.masthead { display:flex; align-items:baseline; gap:10px; border-bottom:2.5pt solid #0e4da4;
            padding-bottom:5px; margin-bottom:4px; }
.masthead .day { font-size:10pt; font-weight:700; }
.masthead h1 { margin:0 auto 0 0; font-size:19pt; font-weight:800; letter-spacing:-.5pt;
               color:#0e4da4; }
.masthead .hint { font-size:8pt; color:#777; }
.banner { margin:8px 0 14px; padding:9px 12px; background:#0e4da4; color:#fff;
          border-radius:2px; font-size:13pt; font-weight:800; letter-spacing:-.4pt; }
.banner span { font-weight:400; font-size:9.5pt; opacity:.85; margin-left:8px; }

h2.sec { margin:15px 0 3px; font-size:11.5pt; font-weight:800; text-align:center; }
h2.sec::before, h2.sec::after { content:'■'; color:#0e4da4; font-size:8pt; vertical-align:2pt; margin:0 5px; }
.note { text-align:center; font-size:8.5pt; color:#777; margin:0 0 3px; }
.rule { border-top:1pt dotted #b9cfe9; margin:3px 0 1px; }

.row { display:flex; gap:9px; align-items:baseline; padding:2.6px 0;
       border-bottom:.4pt solid #e8e6e0; page-break-inside:avoid; }
.row .t { flex:1; font-size:10pt; }
.row .t a { color:#111; text-decoration:none; border-bottom:.4pt solid #c9d6e8; }
.row .src { flex:none; font-size:8.5pt; color:#666; white-space:nowrap; }
.rel { font-size:8pt; color:#888; padding:0 0 3px 10px; page-break-inside:avoid; }
.hl { display:flex; gap:9px; padding:2.6px 0; border-bottom:.4pt solid #e8e6e0; }
.hl .p { flex:none; width:62pt; font-size:9.5pt; font-weight:700; color:#0e4da4; }
.hl .t { flex:1; font-size:9.8pt; color:#333; }
.approx { font-size:7.5pt; color:#a8321f; margin-left:4px; }
footer { margin-top:16px; padding-top:6px; border-top:1pt solid #ccc;
         font-size:7.5pt; color:#888; display:flex; }
footer span:last-child { margin-left:auto; }
"""


def esc(s):
    return html.escape(s or '')


def build(issue: dict) -> str:
    d = datetime.strptime(issue['issue'], '%Y-%m-%d')
    parts = [f'<!doctype html><meta charset="utf-8">'
             f'<title>경기교육 주요 뉴스 {issue["issue"]}</title><style>{CSS}</style>',
             '<div class="masthead">'
             f'<span class="day">{d:%Y-%m-%d}({WEEK[d.weekday()]})</span>'
             '<h1>경기교육 주요 뉴스</h1>'
             '<span class="hint">☞ 제목을 누르면 해당기사로 연결됩니다.</span></div>',
             '<div class="banner">경기교육 대전환<span>크게 제대로!</span></div>']

    for s in issue['sections']:
        parts.append(f'<h2 class="sec">{esc(s["name"])}</h2>')
        if s.get('note'):
            parts.append(f'<p class="note">({esc(s["note"])})</p>')
        parts.append('<div class="rule"></div>')

        for it in s['items']:
            title = (f'<a href="{esc(it["url"])}">{esc(it["title"])}</a>'
                     if it.get('url') else esc(it['title']))
            if s['name'] == '주요언론 헤드라인':
                mark = '<span class="approx">추정</span>' if it.get('approx') else ''
                parts.append(f'<div class="hl"><span class="p">{esc(it["press"])}</span>'
                             f'<span class="t">{title}{mark}</span></div>')
            else:
                src = f'{esc(it.get("date","").replace("-","."))}. {esc(it.get("press",""))}'
                parts.append(f'<div class="row"><span class="t">{title}</span>'
                             f'<span class="src">{src}</span></div>')
                if it.get('related'):
                    parts.append('<div class="rel">＊ 관련기사를 다룬 언론사 : '
                                 f'{esc(", ".join(it["related"]))}</div>')

    total = sum(len(s['items']) for s in issue['sections'])
    parts.append(f'<footer><span>기사 {total}건 · 자동 수집</span>'
                 f'<span>생성 {esc(issue.get("built_at", ""))[:16].replace("T", " ")}</span></footer>')
    return '\n'.join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--no-pdf', action='store_true')
    a = ap.parse_args()

    day = a.date or datetime.now(KST).strftime('%Y-%m-%d')
    src = DATA / f'{day}.json'
    if not src.exists():
        raise SystemExit(f'{src} 가 없습니다. 먼저 python collect.py 를 돌리세요.')

    issue = json.loads(src.read_text(encoding='utf-8'))
    OUT.mkdir(parents=True, exist_ok=True)
    page = OUT / f'{day}.html'
    page.write_text(build(issue), encoding='utf-8')
    print(f'· HTML  docs/issue/{day}.html')

    if a.no_pdf:
        return
    try:
        from weasyprint import HTML
        HTML(string=page.read_text(encoding='utf-8')).write_pdf(OUT / f'{day}.pdf')
        print(f'· PDF   docs/issue/{day}.pdf')
    except Exception as e:                                   # noqa: BLE001
        print(f'! PDF 생성 실패 ({e}). HTML은 정상입니다.')


if __name__ == '__main__':
    main()
