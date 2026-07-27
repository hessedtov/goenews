#!/usr/bin/env python3
"""경기교육 주요 뉴스 — 하루치 수집·분류.

    python collect.py                 오늘자 발행본 생성
    python collect.py --date 2026-07-28
    python collect.py --dry            저장하지 않고 결과만 출력
"""
from __future__ import annotations

import argparse, html, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import feedparser, requests, yaml

ROOT = Path(__file__).parent
DATA = ROOT / 'docs' / 'data'
KST = timezone(timedelta(hours=9))
UA = {'User-Agent': 'Mozilla/5.0 (compatible; GyeonggiEduNews/1.0)'}

HEADLINE = '주요언론 헤드라인'
S_DOE = '경기도교육청'
S_LOCAL = '교육지원청 및 학교'
S_ODD = '경기교육 이런일이'
S_FIELD = '교육계'
S_OPINION = '사설 및 칼럼'
ORDER = [HEADLINE, S_DOE, S_LOCAL, S_ODD, S_FIELD, S_OPINION]


# ── 유틸 ────────────────────────────────────────────────────
def cfg():
    return yaml.safe_load((ROOT / 'sources.yml').read_text(encoding='utf-8'))


def clean(t: str) -> str:
    t = html.unescape(re.sub(r'<[^>]+>', '', t or ''))
    return re.sub(r'\s+', ' ', t).strip()


def fetch(url: str, timeout=20):
    """RSS 한 개를 읽어 항목 목록으로. 실패해도 전체가 멈추지 않게 빈 목록 반환."""
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        r.raise_for_status()
        return feedparser.parse(r.content).entries
    except Exception as e:                                   # noqa: BLE001
        print(f'  ! 실패 {url} — {e}', file=sys.stderr)
        return []


def parse_when(entry) -> datetime | None:
    for key in ('published_parsed', 'updated_parsed'):
        if getattr(entry, key, None):
            return datetime(*getattr(entry, key)[:6], tzinfo=timezone.utc).astimezone(KST)
    return None


def press_of(entry, url: str, fallback: str | None, domains: dict) -> str:
    src = getattr(entry, 'source', None)
    if src is not None and getattr(src, 'title', None):
        name = clean(src.title)
        if name:
            return re.sub(r'\s*\(.*\)$', '', name)
    host = urlparse(url).netloc.replace('www.', '')
    for dom, name in domains.items():
        if host.endswith(dom):
            return name
    return fallback or host


# ── 제목 유사도로 같은 사안 묶기 ─────────────────────────────
def shingles(title: str) -> set[str]:
    s = re.sub(r'[^가-힣A-Za-z0-9]', '', title)
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def similar(a: str, b: str) -> float:
    x, y = shingles(a), shingles(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def cluster(items: list[dict], threshold: float, priority: list[str]) -> list[dict]:
    """같은 사안을 묶어 대표 1건 + related[]로 접는다."""
    groups: list[list[dict]] = []
    for it in items:
        for g in groups:
            if similar(it['title'], g[0]['title']) >= threshold:
                g.append(it)
                break
        else:
            groups.append([it])

    rank = {p: i for i, p in enumerate(priority)}
    out = []
    for g in groups:
        g.sort(key=lambda x: (rank.get(x['press'], 99), x['title']))
        lead = dict(g[0])
        others, seen = [], {lead['press']}
        for o in g[1:]:
            if o['press'] not in seen:
                others.append(o['press'])
                seen.add(o['press'])
        lead['related'] = others
        out.append(lead)
    return out


# ── 분류 ────────────────────────────────────────────────────
class Classifier:
    def __init__(self, rules: dict, local_presses: set[str], planned: dict):
        self.r = rules
        self.local = local_presses
        self.planned = planned                       # 기획지면 이름 → 언론사
        self.tag_re = re.compile(r'^\[([^\]]{1,16})\]')

    SCHOOL = re.compile(r'[가-힣]{2,6}(초등학교|중학교|고등학교|유치원|초교|여고|여중|[초중고](?![등가-힣]))')

    def is_edu(self, t: str) -> bool:
        return any(w in t for w in self.r['교육어']) or bool(self.SCHOOL.search(t))

    def is_gyeonggi(self, t: str) -> bool:
        return (any(w in t for w in self.r['경기지역'])
                or '교육지원청' in t or '도교육청' in t)

    def section(self, it: dict) -> str | None:
        t = it['title']

        # 1) 기획 지면 — 지면 브랜드명이 제목 앞에 붙는 신문이 있다
        for brand, press in self.planned.items():
            if t.startswith(f'[{brand}]') and it['press'] == press:
                return f'[기획기사] {brand}'

        # 2) 사설·칼럼 — 오피니언 피드 출신이거나 대괄호 태그가 붙은 글
        m = self.tag_re.match(t)
        if it.get('from_opinion') or (m and any(
                tag in m.group(1) for tag in self.r['칼럼태그'])):
            return S_OPINION if self.is_edu(t) else None

        if not self.is_edu(t):
            return None

        doe = any(w in t for w in
                  ('경기도교육청', '경기교육청', '도교육청', '경기교육감',
                   '경기도교육감', '안민석', '경기교육 대전환', '경기교육'))
        gy = self.is_gyeonggi(t) or doe

        # 3) 비판·문제제기 (경기 사안일 때만)
        if gy and any(w in t for w in self.r['문제제기']):
            return S_ODD

        # 4) 지원청 소식은 본청보다 먼저 걸러낸다
        if '교육지원청' in t:
            return S_LOCAL

        # 5) 본청 정책 — 도교육청·교육감이 주어인 기사
        if doe:
            return S_DOE

        # 6) 지역지가 쓴 경기 지역 학교 소식
        if gy and (it['press'] in self.local or self.SCHOOL.search(t)):
            return S_LOCAL

        # 7) 그 밖의 경기 교육 사안
        if gy:
            return S_DOE

        # 6) 전국 단위 교육 이슈
        return S_FIELD

# ── 1면 헤드라인 (9개 종합지) ────────────────────────────────
def headlines(day, conf) -> list[dict]:
    """조간 1면 머릿기사를 추정한다.

    1면 지면 정보를 공개 API로 주는 신문사가 없어서, 각 사 종합 피드에서
    발행일 새벽(기본 00~08시)에 올라온 첫 기사를 후보로 세운다.
    overrides/<날짜>.json 에 손으로 적어두면 그쪽이 우선한다.
    """
    lo, hi = conf.get('헤드라인_시간대', [0, 8])
    start = day.replace(hour=lo, minute=0, second=0, microsecond=0)
    end = day.replace(hour=hi, minute=0, second=0, microsecond=0)
    skip = re.compile(r'^\[?(사설|칼럼|사진|포토|영상|부고|인사|오늘의)')

    def pick(name_v):
        name, v = name_v
        if not v.get('주요'):
            return None
        best = None
        for e in fetch(v['주요']):
            t, link, when = clean(getattr(e, 'title', '')), getattr(e, 'link', ''), parse_when(e)
            if not (t and link and when) or skip.match(t):
                continue
            if start <= when <= end and (best is None or when < best[0]):
                best = (when, {'press': f'{name}(서울)', 'title': t,
                               'url': link, 'approx': True})
        return best[1] if best else None

    with ThreadPoolExecutor(max_workers=9) as pool:
        got = list(pool.map(pick, conf['종합지'].items()))
    items = [g for g in got if g]

    ov = ROOT / 'overrides' / f"{day:%Y-%m-%d}.json"
    if ov.exists():
        manual = json.loads(ov.read_text(encoding='utf-8'))
        by_press = {i['press']: i for i in items}
        for m in manual:
            m.setdefault('press', '')
            m['approx'] = False
            by_press[m['press']] = m
        items = list(by_press.values())

    order = list(conf['종합지'])
    items.sort(key=lambda i: order.index(i['press'].replace('(서울)', ''))
               if i['press'].replace('(서울)', '') in order else 99)
    return items


# ── 수집 ────────────────────────────────────────────────────
def collect(day: datetime, conf: dict) -> dict:
    pub = conf['발행']
    rules = conf['분류']
    local_cfg, nat_cfg = conf['지역지'], conf['종합지']

    back = pub['주말_소급일수'] if day.weekday() == 0 else pub['평일_소급일수']
    lo = (day - timedelta(days=back)).replace(hour=0, minute=0, second=0, microsecond=0)
    hi = day.replace(hour=23, minute=59)

    domains = {v['도메인']: k for k, v in local_cfg.items()}
    domains |= {v['도메인']: k for k, v in nat_cfg.items()}
    local_presses = set(local_cfg)
    planned = {b: name for name, v in local_cfg.items() for b in v.get('기획지면', [])}

    jobs = []                                    # (url, 언론사, 오피니언여부)
    for name, v in local_cfg.items():
        for kind, url in v.get('피드', {}).items():
            jobs.append((url, name, kind == '오피니언'))
    for name, v in nat_cfg.items():
        if v.get('오피니언'):
            jobs.append((v['오피니언'], name, True))
    tmpl = conf['구글뉴스']['틀']
    for queries in conf['구글뉴스']['질의'].values():
        for q in queries:
            jobs.append((tmpl.format(q=quote(q)), None, False))
    for name, url in (conf.get('보도자료') or {}).items():
        jobs.append((url, name, False))

    print(f'· 피드 {len(jobs)}개 수집 ({lo:%m/%d} ~ {hi:%m/%d})')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda j: (j, fetch(j[0])), jobs))

    seen, pool_items = set(), []
    for (url, press_hint, is_op), entries in results:
        for e in entries:
            title = clean(getattr(e, 'title', ''))
            link = getattr(e, 'link', '')
            when = parse_when(e)
            if not title or not link or not when:
                continue
            if not (lo <= when <= hi):
                continue
            key = re.sub(r'[^가-힣A-Za-z0-9]', '', title)[:40]
            if key in seen:
                continue
            seen.add(key)
            pool_items.append({
                'title': title,
                'url': link,
                'date': when.strftime('%Y-%m-%d'),
                'press': press_of(e, link, press_hint, domains),
                'from_opinion': is_op,
                'related': [],
            })
    print(f'· 원본 {len(pool_items)}건 확보')

    clf = Classifier(rules, local_presses, planned)
    buckets: dict[str, list[dict]] = {}
    for it in pool_items:
        sec = clf.section(it)
        if sec:
            buckets.setdefault(sec, []).append(it)

    sections = []
    caps = rules['최대건수']
    hl = headlines(day, conf)
    if hl:
        sections.append({'name': HEADLINE, 'note': None, 'items': hl})
    for name in ORDER[1:] + sorted(k for k in buckets if k.startswith('[기획')):
        items = buckets.get(name)
        if not items:
            continue
        items = cluster(items, rules['묶음_유사도'], rules['대표우선순위'])
        items.sort(key=lambda x: (-len(x['related']), x['date']), reverse=False)
        cap = caps.get(name)
        if cap:
            items = items[:cap]
        for it in items:
            it.pop('from_opinion', None)
            it.pop('plan_brand', None)
        note = None
        if name.startswith('[기획'):
            brand = name.replace('[기획기사] ', '')
            press = planned.get(brand, '')
            note = f'{press} {"월화수목금"[day.weekday()] if day.weekday() < 5 else ""}요판 교육전문 섹션'
        sections.append({'name': name, 'note': note, 'items': items})

    return {'issue': day.strftime('%Y-%m-%d'),
            'built_at': datetime.now(KST).isoformat(timespec='seconds'),
            'sections': sections}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    day = (datetime.strptime(a.date, '%Y-%m-%d').replace(tzinfo=KST)
           if a.date else datetime.now(KST))
    issue = collect(day, cfg())

    total = sum(len(s['items']) for s in issue['sections'])
    for s in issue['sections']:
        print(f"  {s['name']:22s} {len(s['items']):3d}건")
    print(f'· 합계 {total}건')

    if total < 10:
        print('! 수집량이 비정상적으로 적습니다. python discover.py 로 피드를 점검하세요.',
              file=sys.stderr)

    if a.dry:
        print(json.dumps(issue, ensure_ascii=False, indent=1)[:3000])
        return

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / f"{issue['issue']}.json").write_text(
        json.dumps(issue, ensure_ascii=False, indent=1), encoding='utf-8')

    index, flat = [], []
    for f in sorted(DATA.glob('20*.json'), reverse=True):
        one = json.loads(f.read_text(encoding='utf-8'))
        index.append({'issue': one['issue'],
                      'n': sum(len(s['items']) for s in one['sections'])})
        for sec in one['sections']:
            for it in sec['items']:
                flat.append([one['issue'], sec['name'], it['title'],
                             it.get('press', ''), it.get('date', ''), it.get('url', '')])
    (DATA / 'index.json').write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    (DATA / 'search.json').write_text(json.dumps(flat, ensure_ascii=False), encoding='utf-8')
    print(f"· 저장 docs/data/{issue['issue']}.json  (누적 {len(index)}일 / {len(flat)}건)")


if __name__ == '__main__':
    main()
