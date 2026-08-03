# TCIM Global Watch — 격주 브리핑 런북

이 문서가 **파이프라인의 유일한 원본**이다. 클라우드 스케줄 작업이 **매주** 월요일 07:00 KST에 이 저장소를 clone해서 이 파일을 읽고 실행하지만, **발행은 격주(2주에 1회)**다. 매주 깨어나되 격주로만 발행하는 이유는 1단계에 적혀 있다.

규칙을 바꾸려면 **이 파일을 고쳐 커밋**하면 된다. 스케줄 작업 프롬프트는 손대지 않는다.

---

## 0. 이 실행의 성격

사용자 장보형(전통의학과 보완통합의학 정책 연구자)을 위해 직전 발행 이후의 글로벌 동향을 수집해 한국어로 요약하고 Supabase에 발행한다. 세션은 매주 새로 시작되며 과거 기억이 없다. 이 문서가 전부다.

전 과정은 공개 자료의 개인 연구 목적 수집과 정리다.

## 인프라

| 항목 | 값 |
| --- | --- |
| Supabase 프로젝트 ID | `wlvhmuudjylaayunnkop` |
| 웹앱 | https://zzangbo.github.io/tcim/ |
| 개별 호 고정 링크 | `https://zzangbo.github.io/tcim/?issue=N` (N은 `issue_no`) |
| 저장소 | `ZZangbo/tcim` |
| 지역 코드 | GLOBAL, AFR, AMR, SEA, EUR, EMR, WPR |
| 섹션 코드 | policy, evidence, jobs, other |

테이블 구조는 `schema.sql` 참고. 비밀값은 `tcim_private_config`에 있고 service_role로만 읽힌다.

필요한 도구는 ToolSearch로 그때그때 로드한다. `mcp__Supabase__execute_sql`, `mcp__pubmed__search_articles`, `mcp__pubmed__get_article_metadata`, `mcp__Gmail__search_threads`, `mcp__Gmail__get_thread`, `mcp__Gmail__create_draft`, `WebSearch`, `WebFetch`.

---

## 1단계 — 준비

1. `select coalesce(max(issue_no),-1) as last_issue, max(period_end) as last_end from tcim_briefings` 로 직전 상태를 읽는다.
2. **날짜 계산을 손으로 하지 않는다.** clone한 저장소에서 아래를 실행하고 그 JSON을 그대로 따른다. 설치는 필요 없다(표준 라이브러리만 쓴다).

   ```bash
   cd /tmp/tcim && python3 -m tcim plan --today YYYY-MM-DD --last-end YYYY-MM-DD --last-issue N
   ```

   `should_publish`, `notify`, `reason`, `issue_no`, `period_start`, `period_end`, `week_no`, `backfill`, `next_publish` 가 나온다. briefings가 비어 있으면 `--last-end`와 `--last-issue`를 생략한다. `--today`는 KST 기준 실행일이고 수집 기간의 끝은 그 전날이다.
3. **★격주 발행 가드.** `should_publish`가 false면 **이번 회차는 발행하지 않는다.** 수집도 시작하지 말고 즉시 종료한다. 이때 `notify`도 false이므로 **PushNotification을 보내지 않는다.** 쉬는 주에 알림이 가면 소음이 된다. 세션 응답에만 `격주 주기 — 이번 주는 건너뜀 (다음 발행 M/D)`이라고 한 줄 남기고, 날짜는 `next_publish`를 쓴다.
   - 스케줄은 매주 도는데 발행만 격주인 구조다. 크론으로는 "2주에 한 번"을 표현할 수 없어서, 매주 깨어난 뒤 직전 발행일과의 간격으로 판단한다. 이 방식은 한 주 실행이 실패해도 다음 주가 자동으로 이어받는다는 이점이 있다.
   - 13일로 잡은 이유는 실행 시각이 밀리거나 앞당겨져도 격주 리듬이 한 주씩 밀리지 않게 하기 위해서다. 14일로 잡으면 몇 분 차이로 한 주를 통째로 거를 수 있다.
   - 이 규칙의 구현은 `tcim/plan.py`이고 `tests/test_plan.py`가 지킨다. **규칙을 바꾸려면 이 문서와 그 두 파일을 함께 고친다.** 한쪽만 고치면 어긋난 채로 두 주가 지나간다.
4. `reason`이 `신규 기간 없음`이면 이미 커버된 구간이다. 발행하지 말고 최종 메시지에 그대로 보고하고 끝낸다.
5. `backfill`이 true면 실행 실패로 결번이 생겨 빠진 구간을 한 호로 합치는 회차다. `stats`에 `backfill: true`를 남긴다. `issue_no`는 결번을 만들지 않고 하나만 증가한다.
6. `select id,name,type,endpoint,default_region,default_section,lang,active,fail_count,notes from tcim_sources order by id` → 수집 계획 수립. `active=true`만 대상이고, `endpoint`와 `notes`에 소스별 호출 방법이 적혀 있다.

---

## 2단계 — 수집

소스당 실패하면 1회만 재시도하고, 그래도 안 되면 기록하고 넘어간다. **차단된 피드를 curl 등으로 우회하지 않는다.**

### PubMed (핵심)

`tcim_sources` id 23(주제 교차 쿼리), id 24(주요 저널 신간), **id 39(고근거 포착)**의 `endpoint`에 저장된 쿼리를 `datetype=edat` + 수집 기간으로 실행한다. 논문 항목의 `url`은 `https://doi.org/(doi)` 형식으로 하고 DOI를 반드시 병기한다. PubMed 출처 표기를 유지한다.

세 쿼리는 역할이 다르다.

- **id 23**은 전통의학 주제와 보건체계 어휘가 **겹치는** 문헌을 잡는다. 이 브리핑의 본령이다.
- **id 24**는 통합의학 전문지 일곱 종의 신간을 훑는다. 대부분 참고 목록으로 간다.
- **id 39**는 id 23이 구조적으로 놓치는 **대형 임상근거**를 잡는다. 상위 종합지에 실린 침 대규모 RCT라도 초록에 'primary care'나 'health policy' 같은 단어가 없으면 id 23에 걸리지 않기 때문이다. A부터 D까지 네 개 하위 쿼리를 **각각 따로** 실행한다. PubMed MCP에 불리언 연산자 20개 제한이 있어 하나로 합칠 수 없다.

id 39에서 걸린 항목은 **정책 직접성이 없어도 헤드라인 후보로 올린다.** 상위 종합지 게재나 코크란 리뷰, 진료지침은 기본 점수 80 이상을 준다. 이 쿼리를 넣은 이유 자체가 '정책 어휘가 없다는 이유로 큰 근거를 흘려보내지 않기' 위해서이므로, 점수 산정에서 다시 정책성으로 깎으면 의미가 없다.

### 뉴스 (핵심)

**WebSearch로 수행한다.** Google News RSS는 이 환경에서 WebFetch가 robots로 차단되므로 시도하지 않는다.

최소 쿼리 세트:

1. `"traditional medicine" WHO`
2. `"integrative medicine" policy OR regulation`
3. `"Ministry of Ayush" OR "Global Traditional Medicine Centre"`
4. `한의약 정책` (한국어)
5. `China "traditional Chinese medicine" policy`
6. `"traditional medicine" Africa`
7. `"práticas integrativas e complementares"`
8. `"integrative medicine" professor OR "faculty position"`

유망한 결과는 WebFetch로 열어 발행일과 내용을 확인한 **뒤에만** 채택한다. 날짜를 확인하지 못한 항목은 `published_at`을 null로 두되 이번 주 발견분만 넣는다. 발행일이 기간 밖으로 확인되면 제외한다.

### WHO

- 본부 뉴스 RSS(`https://www.who.int/rss-feeds/news-english.xml`)는 **2026-08 기준 최신 항목이 5월에 멈춰 있어 신뢰할 수 없다.** 확인은 하되 WHO 뉴스는 반드시 WebSearch(`site:who.int` 포함)로 병행한다.
- SEARO `https://www.who.int/southeastasia/news`, EMRO `https://www.emro.who.int/media/news/` 간단 확인. EMRO는 페이지가 정체돼 있을 수 있다.

### 유럽 (id 40)

EMA 허브의약품위원회(HMPC) `https://www.ema.europa.eu/en/committees/committee-herbal-medicinal-products-hmpc`를 WebFetch한다. 월례 전원회의 아젠다와 회의록, 허브 모노그래프 채택 현황이 올라온다. 기간 내 신규 문서만 채택한다.

유럽은 키워드 검색만으로는 잘 잡히지 않아 기관을 직접 지정한 소스다. 유럽 공백이 계속되면 EDQM이나 각국 규제기관(독일 BfArM, 영국 MHRA)을 같은 방식으로 추가하는 것이 검색어를 늘리는 것보다 낫다.

### ★지역 전수 확인 (매 회차 필수)

**7개 지역 모두에 대해 최소 1회씩 지역 지정 검색을 수행한다.** 일반 키워드 검색 결과에 우연히 그 지역이 잡히기를 기다리지 않는다. `site:` 지정이나 지역명을 넣은 검색을 각 지역마다 한 번씩은 돌린다.

그리고 `regional_notes`에 **확인한 결과와 확인하지 못한 것을 구분해서** 적는다.

- 소식이 있으면: 그 내용을 한 줄로
- 확인했으나 없으면: `확인함, 해당 기간 소식 없음`
- 확인 자체를 못 했으면: `수집 실패 — (사유)`

지금까지 `—` 하나로 뭉뚱그려 온 탓에 **실제로 소식이 없었던 것인지 훑지 않은 것인지 구분되지 않았다.** 이 구분이 회차를 거듭하며 쌓이면 어느 지역의 어느 소스를 보강해야 하는지가 드러난다. 그냥 `—`만 남기지 말 것.

**알아둘 구조적 제약:** 이 환경의 WebSearch는 미국 로케일 결과를 돌려준다. 영어와 미국에서 색인된 자료가 구조적으로 유리하고, 비영어권 지역 뉴스는 검색어를 아무리 다듬어도 덜 잡힌다. 지역 편차를 완전히 없앨 수는 없으므로, **기관을 직접 지정하는 소스를 늘리는 방향**이 검색어를 늘리는 것보다 효과가 크다.

### 한국

- KIOM 채용 `https://kiom.re.kr/menu.es?mid=a10503020000` — 본문 미렌더 이력 있음
- NIKOM 채용 `https://nikom.or.kr/nikom/board/index.do?menu_idx=62&manage_idx=45`
- 복지부 보도자료 `https://www.mohw.go.kr/board.es?mid=a10503010200&bid=0027` — robots 차단 이력 있음

실패하면 WebSearch로 대체하고, **국내 소식이 비면 비었다고 정직하게 쓴다.**

### 미국 연방 채용

`tcim_sources` id 20의 endpoint(자체 프록시, WebFetch 가능)를 호출한다. `q=` 값을 `integrative medicine`, `complementary medicine`, `traditional medicine`으로 바꿔 2~3회 검색한다. 기간 내 신규 게시(posted)만 채택한다.

### Gmail 알림과 뉴스레터

**검색은 라벨 ID가 아니라 라벨명으로 해야 동작한다.** 라벨 ID(`label:Label_...`) 쿼리는 0건을 반환하므로 쓰지 않는다.

- `label:TCIM-Jobs newer_than:15d` (채용 알림)
- `label:TCIM-News newer_than:15d` (뉴스레터)

`newer_than` 값은 항상 수집 기간보다 하루 이틀 넉넉하게 잡는다. 백필 회차에는 기간에 맞춰 더 늘린다.

### Bluesky (보조)

`tcim_sources` id 26의 계정마다 `https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=(핸들)&limit=20`을 WebFetch한다. 실패하면 조용히 생략한다.

### 쓰지 않는 소스

한국 공공기관 채용 API(id 21)는 게이트웨이 차단으로 비활성이다. unjobs와 jobs.ac.uk 등 차단 사이트도 자동 수집하지 않는다(웹앱에 스팟 링크가 있다).

---

## 3단계 — 선별, 분류, 요약

- **중복 제거**: insert 전에 `select url from tcim_items where url in (...)`으로 기존 항목을 제외한다. 같은 사건의 다중 보도는 대표 1건만 남긴다.
- **관련성**: 전통의학과 보완통합의학에 직접 관련된 것만 채택한다. 가중치는 WHO와 정부의 정책·규제 > 건강증진, 일차의료, 지역사회의학 근거 > 채용과 펀딩 순이다. 무관한 건강 일반 뉴스는 버린다.
- **분류**: `section`, `region`(국가는 `tcim_country_region_map`으로 매핑, 국제기구와 다국가는 GLOBAL), `countries[]`(ISO2), `tags[]`(주제와 문서유형의 한국어 태그).
- **summary_ko**: 한국어 2~3문장. 사실 요약 2문장에 연구자 관점 1문장. 원문을 왜곡하거나 과장하지 않는다. 영어 원문이면 `title_ko`도 작성한다.
- **점수**: 0~100. 정책 직접성, 근거 수준(설계와 규모), 지역 다양성, 신규성 기준. 단 **id 39(고근거 포착)에서 온 항목은 정책 직접성으로 깎지 않는다.** 상위 종합지, 코크란 리뷰, 진료지침은 80 이상, 다기관 RCT는 75 이상에서 시작한다.
- **선정**: 헤드라인 3~5건(섹션 불문 최상위), 섹션별 카드 최대 8건, 선별에서 빠진 관련 항목은 `block='all'`(참고 목록). 소식이 적은 주면 적은 대로 정직하게 쓴다.

### 문체 규칙

**나열에 가운뎃점(·)을 쓰지 않는다.** 쉼표나 '와/과', '및'으로 연결한다. 사용자가 가운뎃점 남용을 부자연스러운 AI 문체로 여긴다. 다만 한·중·일, 정책·규제처럼 관례적으로 붙여 쓰는 표기와 고유명사는 그대로 둔다.

---

## 4단계 — 발행

`execute_sql`을 쓴다. 긴 한국어 문자열은 `$q$...$q$` 달러 인용을 쓰면 따옴표 이스케이프 문제가 없다.

1. **tcim_items insert**: `(source_id, title, title_ko, url, published_at, section, region, countries, tags, summary_ko, lang, score, week_no)`. `source_id`는 `tcim_sources` 매칭(없으면 null), `week_no`는 `period_end` 기준 ISO 주 `'YYYY-Www'`. `on conflict (url) do nothing`을 쓴다.
2. **tcim_briefings insert**: `issue_no, period_start, period_end, headline_md, regional_notes, implication_md, stats, published_at=now()`. `regional_notes`는 7개 지역 각 1줄 한국어 jsonb. **소식 없는 지역도 `—`로 두지 말고 `확인함, 해당 기간 소식 없음` 또는 `수집 실패 — (사유)`로 구분해 적는다**(2단계의 지역 전수 확인 참고). `implication_md`는 시사점 3~5문장. `stats`는 `{"collected":n,"selected":n,"sources_ok":[...],"sources_failed":[...]}`.
3. **tcim_briefing_items insert**: url로 `tcim_items`의 id를 조인해 `(briefing_id, item_id, block, rank)`를 연결한다. 같은 항목이 headline과 섹션 블록에 중복 연결되는 것은 정상이다.
4. **tcim_sources update**: 성공 소스는 `last_ok_at=now()`, 실패 소스는 `fail_count=fail_count+1`. `fail_count`가 3 이상이 된 소스는 `implication_md` 끝에 `소스 점검 필요: (이름)` 1줄을 추가한다. 소스 동작 방식에 대해 새로 알아낸 사실은 `notes`에 날짜와 함께 덧붙인다.
5. **검증**: `select count(*) from tcim_briefing_items where briefing_id=(이번 호 id)`로 연결 수를 확인한다.
6. 발행일이 그 달 1~7일이면(월 1회) `implication_md` 끝에 소스 헬스 요약 1문단을 덧붙인다.

---

## 5단계 — 구독자 발송 준비

발송은 Resend HTTPS API로 나간다. 설정 배경은 `DESIGN.md`, 최초 설정 절차는 `SETUP-mail.md`.

1. `select email from tcim_subscribers where status='approved' order by id` → 승인된 수신자. **0명이면 이 단계를 통째로 건너뛴다.**
2. **수신자 한 명당 한 통씩 보낸다. BCC로 묶지 않는다.** 각자 To에 자기 주소만 들어가므로 서로의 주소가 보일 일이 없고, 수신자별 성공과 실패를 정확히 알 수 있다. 본인 주소가 승인 목록에 있으면 그냥 한 명으로 친다 — 중복 계산할 자리가 없다.
3. `select key, value from tcim_private_config where key in ('resend_api_key','mail_from','mail_reply_to','auto_send','mail_provider')`로 설정을 읽는다. `resend_api_key`가 없으면 **아직 설정 전이다.** 발송하지 말고 최종 메시지에 `메일 설정 미완료 — SETUP-mail.md 참고`를 남긴다.
4. **HTML을 손으로 조립하지 않는다.** 호 데이터를 JSON으로 쓴 뒤 아래를 실행한다.

   ```bash
   cd /tmp/tcim && python3 -m tcim build --data issue.json --template email-template.html --approved N --out ./out
   ```

   `issue.json`에 넣을 것: `issue_no`, `period_start`, `period_end`, `intro`, `counts`, `subject_headlines`(제목줄용 20자 안팎 축약 2개), `recipients`(승인 수신자 주소 배열), `headlines`(각 항목에 `title_ko`, `summary_ko`, `section`, `region`). 축약과 요약은 판단이라 여기서 만들어 넣는다.

   나오는 것: `out/mail.html`, `out/mail.txt`, 그리고 stdout에 제목과 프리플라이트 결과. **`preflight.ok`가 false면 한 통도 보내지 말고 실패 사유를 알림에 적는다.** 종료 코드도 1이다.

   - 프리플라이트가 보는 것과 그 이유는 `DESIGN.md`에 있다. 배경색 선언, 흰 글자, 어두운 `bgcolor`, 맨 URL 앵커, 어긋난 `?issue=N`, 미치환 자리표시자, 수신 중단 문구 누락, 수신자 수 불일치를 잡는다.
   - 카드 좌측 색띠와 라벨 색은 `render.py`가 섹션에 맞춰 넣는다. policy `#0f6b5c`, evidence `#3554a5`, jobs `#a05a1f`.
   - **각 항목 요약은 2~3문장으로 쓴다.** 한 줄로 줄이지 않는다. DB의 `summary_ko`를 메일 문장으로 다듬어 쓰되 사실을 바꾸지 않는다.
   - **링크는 절대 맨 URL로 쓰지 않는다.** 반드시 `<a href="https://zzangbo.github.io/tcim/?issue=N">제N호 전체 보기</a>` 형태의 앵커 텍스트로 넣는다. 평문에 맨 URL을 두면 메일 클라이언트가 `google.com/url?q=...` 리다이렉트로 감싸서 본문에 흉한 긴 문자열이 그대로 보인다.
   - 외부 이미지나 웹폰트를 넣지 않는다. 스타일은 전부 인라인으로 두고 표 기반 레이아웃을 유지한다. 네이버와 다음 웹메일에서 깨지지 않아야 한다.
   - **★배경색에 의존하지 말 것.** Gmail 발송 파이프라인이 `background`와 `background-color` CSS 선언을 전부 제거한다(2026-08-03 발송본에서 확인). 살아남는 것은 `border`, `color`, `padding`, `border-radius`, `display`다. 그래서 **흰 글자를 어디에도 쓰지 않는다.** 색 배경 위 흰 글자는 배경이 사라지는 순간 흰 바탕에 흰 글자가 되어 보이지 않는다. 버튼도 채운 버튼 대신 테두리 버튼에 진한 글자로 만든다.
   - `bgcolor` 속성은 진한 색에 쓰지 않고 옅은 톤(`#f1f7f5`, `#fafbfc` 등)에만 쓴다. 살아남든 제거되든 어두운 글자가 읽히기 때문이다.
   - 버튼 아래에 `zzangbo.github.io/tcim/?issue=N` 을 눈에 보이는 텍스트 링크로 한 줄 더 둔다. 버튼이 깨져도 주소가 보이게 하기 위한 이중 안전장치다.
   - 맨 끝에 `수신을 중단하시려면 이 메일에 회신해 주세요.` 1줄. 시사점과 소스 현황은 넣지 않는다.
5. **발송.** `auto_send`가 `true`가 아니면 `dry_run`으로 대상만 확인하고 실제로 보내지 않는다.

   ```python
   from tcim.send import send_issue
   out = send_issue(rendered, recipients, api_key=..., from_address=..., reply_to=...,
                    issue_no=N, already_sent=이미_보낸_주소_집합, dry_run=(auto_send != 'true'))
   ```

   `already_sent`는 `select email from tcim_sends where issue_no=N and status='sent'`로 채운다. 재시도할 때 성공분을 두 번 보내지 않기 위해서다.

6. **결과 기록.** `send_issue`가 돌려준 `results`를 그대로 `tcim_sends`에 넣는다. `(issue_no, lower(email))`에 유니크 인덱스가 있으므로 `on conflict do update`를 쓴다.

   ```sql
   insert into tcim_sends (issue_no, email, status, provider, provider_id, error)
   values (...)
   on conflict (issue_no, lower(email)) do update
     set status=excluded.status, provider_id=excluded.provider_id,
         error=excluded.error, attempted_at=now();
   ```

   실패가 하나라도 있으면 최종 메시지에 `발송 실패 N건: (주소)`를 덧붙인다. 다음 회차나 재실행이 실패분만 다시 보낸다.

7. `last_sent_at`은 `tcim_sends`가 대신하므로 갱신하지 않는다. 수신자별 사실이 그쪽에 남는다.
8. `select count(*) from tcim_subscribers where status='pending'`. 1건 이상이면 최종 메시지 끝에 `구독 신청 N건 대기`를 덧붙인다.

**승인은 사용자가 별도로 지시할 때만 한다. 루틴이 스스로 `status`를 `approved`로 바꾸는 일은 절대 없다.**

구독 신청 접수, 승인, 환영 메일, 수신 중단의 상세 절차는 별도 문서 [`SUBSCRIBERS.md`](SUBSCRIBERS.md)에 있다. 그 문서는 **매일 08:00 KST에 도는 일일 점검 스케줄 작업**이 읽는다. 격주 발행과 주기가 다르므로 파일을 분리했다. 신청은 아무 때나 들어오는데 발행은 2주에 한 번이라, 점검까지 격주로 하면 신청자가 최대 2주를 기다리게 된다.

---

## 실패 처리

- 일부 소스가 실패해도 발행은 강행하고 `stats.sources_failed`에 기록한다.
- **Supabase 접근 자체가 불가능하면** 발행을 포기하고, 최종 메시지에 원인과 함께 `발행 실패 — 다음 주 실행이 자동으로 이번 주까지 백필함`을 명확히 알린다.
- 전체 실행은 효율적으로 한다. 수집과 발행에 집중하고 불필요한 탐색을 줄인다.

---

## 최종 메시지와 완료 알림

알림 이메일은 줄바꿈을 살리지 못하고 전체를 한 문단으로 합쳐서 보여준다. 길게 쓰면 반드시 줄글 덩어리가 된다. **아래 형식만 쓰고 그 외에는 아무것도 넣지 않는다.**

`PushNotification`의 message를 `<routine_summary>` 태그로 감싸고 내용은 정확히 이 형식으로 한다.

```
TCIM 브리핑 제N호 발행 완료 (M/D~M/D, 선별 Y건)
헤드라인: (제목1), (제목2), (제목3)
https://zzangbo.github.io/tcim/?issue=N
```

- 헤드라인 제목은 각각 20자 안팎으로 줄인 핵심 문구만 쓴다. 날짜와 기관 상세와 부연 설명은 넣지 않는다. 예: `BRICS 전통의학 선언`, `중국 중의약 5개년 계획`
- 구독자 초안을 만들었으면 `구독 메일 초안 N명분 작성 — Gmail에서 발송 필요` 1줄을 덧붙인다.
- 신규 구독 신청이 있으면 `구독 신청 N건 대기` 1줄을 덧붙인다.
- 소스 실패나 점검이 필요하면 `점검: (한 줄)`을 덧붙인다. 없으면 생략한다.
- **수집 건수 내역, 백필 여부, 소스 상세 현황, 시사점, 출처 목록은 알림에 절대 쓰지 않는다.** DB(`implication_md`, `stats`, `tcim_sources.notes`)에만 남긴다.
- 채팅 세션에 남기는 최종 응답도 위와 똑같이 짧게 쓴다. 장황한 실행 보고를 덧붙이지 않는다.

---

## 변경 이력에서 배운 것들

새로 알아낸 환경 제약은 여기 적어두고 커밋한다. 다음 실행이 같은 함정을 다시 밟지 않게 하는 것이 이 절의 목적이다.

- **2026-08-03** Gmail 검색은 라벨 ID가 아니라 라벨명으로 해야 동작한다. `TCIM-News` 라벨은 누적 0건이라 뉴스레터 필터 점검이 필요하다.
- **2026-08-03** WHO 본부 뉴스 RSS가 2026-05-31에 멈춰 있어 7월 BRICS 기사를 놓쳤다. WebSearch 병행이 필수다.
- **2026-08-03** WHO EMRO 뉴스 페이지도 2025-10-06까지만 노출된다.
- **2026-08-03** 복지부 보도자료는 robots.txt로 WebFetch가 차단된다.
- **2026-08-03** KIOM 채용게시판은 본문이 렌더되지 않는다.
- **2026-08-03** 이 클라우드 환경은 `tcim_private_config.github_token`으로 저장소에 직접 커밋하고 푸시할 수 있다. 단 GitHub REST API는 프록시에 막혀 있고 git over HTTPS만 동작한다.
- **2026-08-03** lower(email) 유니크 인덱스 때문에 수신 중단한 사람이 웹앱 폼으로 재구독할 수 없다. 재구독은 사람이 status 를 되돌려야 한다. SUBSCRIBERS.md 의 재구독 절 참고.
- **2026-08-03** 구독 신청이 최대 2주간 방치되는 문제를 없애려고 일일 점검 작업을 분리했다. tcim_subscribers 에 welcomed_at 컬럼 추가. 절차는 SUBSCRIBERS.md.
- **2026-08-03** 지역 편차 대응. EMA HMPC(id 40)를 유럽 기관 지정 소스로 추가했다. EMRO는 TCIM 주제 페이지가 정적이고 뉴스 피드가 없어 추가할 소스가 없었다. 대신 지역 전수 확인 규칙을 넣어 `—`를 없애고 확인 여부를 구분해 기록하게 했다.
- **2026-08-03** 이 환경의 WebSearch는 미국 로케일 결과를 반환한다. 지역 편차의 상당 부분이 검색어 설계가 아니라 이 제약에서 온다. 기관 지정 소스를 늘리는 편이 검색어를 늘리는 것보다 효과가 크다.
- **2026-08-03** 대형 임상근거 누락을 메우려고 id 39(고근거 포착)를 신설했다. 14일 실측 A 0건, B 1건, C 1건, D 2건. 여기서 온 항목은 정책성으로 점수를 깎지 않는다.
- **2026-08-03** 발행 주기를 매주에서 격주로 바꿨다. 크론은 매주 그대로 두고 1단계의 13일 가드로 판단한다. 쉬는 회차는 알림을 보내지 않는다.
- **2026-08-03** Gmail 발송 파이프라인이 HTML 의 `background` 와 `background-color` 선언을 전부 제거한다. 실제 발송본에서 확인했다. `border`, `color`, `padding`, `border-radius` 는 살아남는다. 메일 디자인은 배경색 없이도 읽히게 만들어야 하고 흰 글자를 쓰면 안 된다.
- **2026-08-03** Gmail 은 본문의 링크 href 를 `google.com/url?q=...` 로 감싼다. 보내는 쪽에서 끌 수 없다. 앵커 텍스트를 쓰면 본문에 긴 주소가 보이지는 않는다.
- **2026-08-03** 발송 경로를 확정했다. Resend HTTPS API(`news.jbhlab.com` 발신) + Cloudflare Email Routing(`tcim@jbhlab.com` 수신 포워딩). 둘 다 무료다. **발신과 수신을 다른 이름에 둔 이유는 SPF 레코드가 겹치지 않게 하려는 것**이고, 회신 주소가 따로 필요한 이유는 발신 도메인에 MX가 없어 거기로는 회신을 못 받기 때문이다. Cloudflare Email Service(발신)는 Workers Paid 월 $5에 포함량이 Resend 무료와 같아 탈락했다.
- **2026-08-03** `_dmarc.jbhlab.com`에 `p=reject`가 이미 걸려 있다(등록업체 기본값). **인증을 붙이기 전에 그 도메인 이름으로 보내면 스팸함이 아니라 거부된다.** 반대로 인증이 붙으면 유리한 출발선이 된다.
- **2026-08-03** BCC 묶음을 버리고 수신자당 한 통씩 보낸다. ESP를 쓰면 그쪽이 낫다 — 수신자별 성공과 실패를 정확히 알 수 있고, 한 명이 실패해도 나머지가 나간다.
- **2026-08-03** ★이 클라우드 컨테이너는 아웃바운드가 **HTTPS만** 열려 있다. `smtp.gmail.com` 25·465·587과 `smtp-relay.brevo.com` 587이 전부 타임아웃이고, `gmail.googleapis.com`·`oauth2.googleapis.com`·`api.brevo.com`·`api.resend.com` 443은 열린다. **세션 안에서 SMTP 발송은 불가능하다.** 앱 비밀번호는 SMTP 전용이라 Gmail API로 대체할 수도 없다. 발송은 GitHub Actions로 내보낸다. 자세한 것은 `DESIGN.md`.
- **2026-08-03** Gmail MCP 커넥터에 여전히 발송 도구가 없다. `create_draft`, `update_draft`, `list_drafts`, `search_threads`, `get_thread`, `get_message`, 라벨 조작이 전부다.
- **2026-08-03** 결정적인 계층을 `tcim/` 패키지로 내렸다. `plan`(날짜와 격주 가드), `render`(메일 조립), `preflight`(발송 전 검사). 표준 라이브러리만 쓰므로 clone 직후 설치 없이 돈다. 판단은 그대로 이 문서가 맡는다. 무엇을 왜 내렸는지는 `DESIGN.md`.
- **2026-08-03** 메일 템플릿 상단의 내부 주석이 발송본에 그대로 실려 나가고 있었다. 배경색 제약과 자리표시자 목록이 구독자에게 갔다. `render`가 주석을 떼고 내보낸다.
- **2026-08-03** v2 템플릿의 가시 링크에 `?issue=2`가 하드코딩돼 있었다. 제3호부터 제2호로 연결됐을 것이다. 프리플라이트가 href와 가시 텍스트를 모두 대조한다.
- **2026-08-03** 절차 문서와 스케줄 작업 프롬프트를 따로 고치면 어긋난다. SUBSCRIBERS.md 에 수신 중단 회신 확인을 넣었는데 8분 먼저 만들어진 일일 점검 작업 프롬프트에는 그 단계가 없었고, 양쪽의 '조용한 날엔 알리지 않는다' 규칙이 '중단은 반드시 알린다'와 충돌해 중단이 조용히 처리될 뻔했다. **절차를 바꾸면 그것을 실행하는 작업 프롬프트의 단계 열거와 알림 규칙도 같이 본다.**
- **2026-08-03** 수신 중단 회신 검색(`subject:TCIM`)에 브리핑 사본이 걸린다. 사용자가 다른 주소에서 자기에게 보낸 것이라 보낸 사람 대조로도 안 걸러진다. 본문에 사람이 쓴 문장이 있는지로 판별한다. SUBSCRIBERS.md 4번 참고.
- **2026-08-03** 샌드박스 브라우저는 외부망이 막혀 있다. 웹앱을 브라우저로 검증하려면 Playwright 라우트 가로채기로 Supabase 응답을 대신 넣어야 한다.
