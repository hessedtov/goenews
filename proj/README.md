# 경기교육 주요 뉴스 — 자동 수집

매일 아침 7시 10분에 스스로 돌아가서, 전날치 경기교육 관련 기사를 모아
기존 발행물과 같은 형식의 지면(HTML·PDF)과 검색 가능한 아카이브를 만듭니다.
PC를 켜 둘 필요는 없습니다.

---

## 처음 한 번만 하는 일

**1. 저장소 만들기**
GitHub에서 새 저장소를 만들고 이 폴더 전체를 올립니다.

**2. Pages 켜기**
저장소 → Settings → Pages → Source를 **GitHub Actions**로 바꿉니다.

**3. Actions에 쓰기 권한 주기**
Settings → Actions → General → Workflow permissions →
**Read and write permissions** 선택 후 저장.

**4. 첫 실행**
Actions 탭 → «경기교육 뉴스 수집» → **Run workflow**.
2~3분 뒤 `https://<계정>.github.io/<저장소>/` 에서 결과를 볼 수 있습니다.

이후로는 손댈 일이 없습니다. 월~금 아침마다 알아서 갱신됩니다.

---

## 어디서 기사를 가져오는가

| 담당 섹션 | 출처 | 비고 |
|---|---|---|
| 교육지원청 및 학교, 기획지면 | 경기권 지역지 6종 RSS | 통신사에 안 나오는 소식이라 여기가 핵심 |
| 교육계, 경기도교육청 | 구글 뉴스 RSS 키워드 검색 | 키 없이 무료, 통신사·방송사가 여기로 들어옴 |
| 사설 및 칼럼 | 중앙 9개지 + 지역지 오피니언 RSS | |
| 주요언론 헤드라인 | 중앙 9개지 종합 RSS (추정) | 아래 설명 참고 |

네이버 검색 API는 쓰지 않습니다. 유료로 바뀌기도 했고, 위 조합으로
같은 범위를 키 없이 덮을 수 있습니다. 발급받을 계정도, 만료될 키도 없습니다.

---

## 1면 헤드라인만 완전 자동이 아닙니다

신문 1면 지면 구성을 공개 데이터로 주는 신문사가 없습니다. 그래서 각 사
종합 피드에서 **그날 새벽에 올라온 첫 기사**를 후보로 세우고, 지면에
「추정」 표시를 붙입니다. 실제 1면 머릿기사와 대체로 겹치지만 항상은 아닙니다.

특정 날짜만 바로잡고 싶으면 `overrides/2026-07-28.json` 형식으로 적어 두면
그날은 그 내용이 우선합니다 (자세한 형식은 `overrides/README.md`).

---

## 분류가 어긋날 때

기사를 어느 섹션에 넣을지는 `sources.yml`의 **분류** 항목이 결정합니다.
원본 14일치 595건을 정답지로 채점해 둔 상태의 성적은 이렇습니다.

```
교육계              89.0%
사설 및 칼럼         88.7%
경기도교육청          85.1%
교육지원청 및 학교     82.6%
경기교육 이런일이      61.9%   ← 논조로 가르는 섹션이라 원래 어렵습니다
전체                82.5%
```

키워드를 고친 뒤 `python score.py` 를 돌리면 좋아졌는지 나빠졌는지 즉시
확인할 수 있습니다. `python score.py --miss` 는 틀린 항목을 그대로 보여줍니다.

---

## 수집량이 갑자기 줄었다면

신문사가 홈페이지를 개편하면 RSS 주소가 조용히 죽습니다. 이때만 손이 갑니다.

```bash
python discover.py          # 어느 피드가 죽었는지
python discover.py --fix    # 그 신문사의 현재 피드 목록을 찾아 제안
```

Actions 탭에서 «Run workflow → check_only ✔» 로 실행해도 같은 점검을 합니다.
결과를 보고 `sources.yml`의 해당 줄만 고치면 됩니다.

---

## 손으로 돌려보기

```bash
pip install -r requirements.txt
python collect.py --dry              # 저장하지 않고 결과만 확인
python collect.py --date 2026-07-28  # 특정 날짜
python render.py                     # 지면 HTML + PDF 생성
```

## 파일 구조

```
sources.yml          출처·키워드·분류 규칙   ← 고칠 일이 있으면 대부분 여기
collect.py           수집 → 분류 → 같은 사안 묶기 → JSON 저장
render.py            JSON → 인쇄용 HTML + PDF
discover.py          피드 생사 점검
score.py             분류 규칙 채점
overrides/           1면 헤드라인 수동 교정
tuning/archive.json  채점용 정답지 (2026-07-07 ~ 07-27, 595건)
docs/                GitHub Pages 공개 폴더
  index.html           아카이브 열람·검색
  data/                날짜별 JSON
  issue/               날짜별 지면 HTML·PDF
```
