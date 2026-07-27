#!/usr/bin/env python3
"""sources.yml 에 적힌 피드가 살아 있는지 확인한다.

    python discover.py            전체 점검
    python discover.py --fix      죽은 지역지 피드의 대체 주소를 찾아 제안

신문사가 CMS를 바꾸면 피드 주소가 조용히 죽습니다. 수집량이 갑자기 줄면
이걸 먼저 돌려 보세요. 어느 줄을 고쳐야 하는지 그대로 알려줍니다.
"""
from __future__ import annotations

import re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import feedparser, requests, yaml

ROOT = Path(__file__).parent
UA = {'User-Agent': 'Mozilla/5.0 (compatible; GyeonggiEduNews/1.0)'}
OK, BAD, WARN = '\033[32m정상\033[0m', '\033[31m실패\033[0m', '\033[33m비었음\033[0m'


def probe(url: str) -> tuple[str, int, str]:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        entries = feedparser.parse(r.content).entries
        if not entries:
            return WARN, 0, '응답은 왔지만 기사가 없습니다'
        newest = getattr(entries[0], 'published', '') or getattr(entries[0], 'updated', '')
        return OK, len(entries), f'최신 {newest[:31]}'
    except Exception as e:                                   # noqa: BLE001
        return BAD, 0, str(e)[:70]


def rss_index(domain: str) -> dict[str, str]:
    """NDSoft 계열 신문은 /rssIndex.html 에 피드 목록을 공개한다."""
    for scheme in ('https://www.', 'http://www.'):
        try:
            r = requests.get(scheme + domain + '/rssIndex.html', headers=UA, timeout=15)
            if r.ok:
                found = re.findall(r'(https?://[^"\'<>\s]+/rss/[A-Za-z0-9]+\.xml)', r.text)
                return {u.rsplit('/', 1)[-1][:-4]: u for u in sorted(set(found))}
        except Exception:                                    # noqa: BLE001
            continue
    return {}


def main():
    conf = yaml.safe_load((ROOT / 'sources.yml').read_text(encoding='utf-8'))
    fix = '--fix' in sys.argv

    jobs = []
    for name, v in conf['지역지'].items():
        for kind, url in v.get('피드', {}).items():
            jobs.append((f'{name}·{kind}', url, v['도메인']))
    for name, v in conf['종합지'].items():
        for kind in ('주요', '오피니언'):
            if v.get(kind):
                jobs.append((f'{name}·{kind}', v[kind], v['도메인']))
    tmpl = conf['구글뉴스']['틀']
    jobs.append(('구글뉴스·표본', tmpl.format(q='경기도교육청'), 'news.google.com'))
    for name, url in (conf.get('보도자료') or {}).items():
        jobs.append((f'{name}·보도자료', url, ''))

    print(f'피드 {len(jobs)}개 점검\n' + '─' * 76)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda j: (j, probe(j[1])), jobs))

    broken = []
    for (label, url, domain), (status, n, note) in results:
        print(f'{status}  {label:20s} {n:3d}건  {note}')
        if status != OK:
            broken.append((label, url, domain))

    print('─' * 76)
    print(f'정상 {len(results) - len(broken)} / 전체 {len(results)}')

    if not broken:
        print('\n손볼 곳이 없습니다.')
        return

    print('\n고쳐야 할 줄:')
    for label, url, _ in broken:
        print(f'  {label}  →  {url}')

    if fix:
        print('\n대체 주소를 찾는 중...')
        for label, _, domain in broken:
            if not domain or 'google' in domain:
                continue
            feeds = rss_index(domain)
            if feeds:
                print(f'\n  [{label}] {domain} 에서 찾은 피드:')
                for k, u in list(feeds.items())[:24]:
                    print(f'      {k:12s} {u}')
            else:
                print(f'\n  [{label}] {domain} — rssIndex.html 을 못 찾았습니다. '
                      f'사이트 하단 "RSS" 링크를 직접 확인하세요.')
    else:
        print('\n대체 주소를 찾으려면:  python discover.py --fix')


if __name__ == '__main__':
    main()
