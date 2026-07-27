#!/usr/bin/env python3
"""sources.yml 의 분류 규칙을 원본 14일치에 대고 채점한다.

    python score.py            섹션별 정확도
    python score.py --miss     틀린 것만 자세히

키워드를 고친 뒤 이걸 돌려 보면 좋아졌는지 나빠졌는지 바로 나옵니다.
정답지(tuning/archive.json)는 2026년 7월 7~27일 발행본 595건입니다.
"""
from __future__ import annotations

import collections, json, sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from collect import Classifier, HEADLINE, S_OPINION      # noqa: E402

ROOT = Path(__file__).parent


def main():
    detail = '--miss' in sys.argv
    conf = yaml.safe_load((ROOT / 'sources.yml').read_text(encoding='utf-8'))
    clf = Classifier(conf['분류'], set(conf['지역지']),
                     {b: n for n, v in conf['지역지'].items()
                      for b in v.get('기획지면', [])})

    truth = []
    for iss in json.loads((ROOT / 'tuning' / 'archive.json').read_text(encoding='utf-8')):
        for s in iss['sections']:
            if s['name'] == HEADLINE:
                continue
            for it in s['items']:
                truth.append((s['name'], it['title'], it.get('press') or ''))

    ok = 0
    per = collections.defaultdict(lambda: [0, 0])
    miss = collections.defaultdict(list)
    for real, title, press in truth:
        got = clf.section({'title': title, 'press': press,
                           'from_opinion': real == S_OPINION})
        per[real][1] += 1
        if got == real:
            ok += 1
            per[real][0] += 1
        else:
            miss[real].append((title, got))

    print(f'정확도 {ok}/{len(truth)} = {ok / len(truth) * 100:.1f}%\n')
    for k, (a, b) in sorted(per.items(), key=lambda x: -x[1][1]):
        if b >= 5:
            bar = '█' * round(a / b * 24)
            print(f'  {k:24s} {a:3d}/{b:3d}  {a / b * 100:5.1f}%  {bar}')

    if detail:
        for k, rows in miss.items():
            if not rows:
                continue
            print(f'\n[{k}] 놓친 {len(rows)}건')
            for t, g in rows:
                print(f'   → {g or "버려짐":14s} | {t[:64]}')
    else:
        print('\n틀린 항목을 보려면:  python score.py --miss')


if __name__ == '__main__':
    main()
