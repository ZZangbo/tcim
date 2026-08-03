# TCIM Global Watch — 주간 브리핑 런북

이 문서가 **파이프라인의 유일한 원본**이다. 매주 월요일 07:00 KST에 클라우드 스케줄 작업이 이 저장소를 clone해서 이 파일을 읽고 그대로 실행한다.

규칙을 바꾸려면 **이 파일을 고쳐 커밋**하면 된다. 스케줄 작업 프롬프트는 손대지 않는다.

---

## 0. 이 실행의 성격

사용자 장보형(전통의학과 보완통합의학 정책 연구자)을 위해 지난 한 주의 글로벌 동향을 수집해 한국어로 요약하고 Supabase에 발행한다. 세션은 매주 새로 시작되며 과거 기억이 없다. 이 문서가 전부다.

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

1. `select coalesce(max(issue_no),-1), max(period_end) from tcim_briefings` → 새 `issue_no` = max+1.
2. 수집 기간 = (직전 `period_end` 다음날) ~ 어제(KST). briefings가 비어 있으면 최근 7일.
3. **기간 시작이 어제보다 늦으면(이미 커버됨) 발행하지 말고** 최종 메시지에 "신규 기간 없음"이라고만 보고하고 끝낸다.
4. 직전 발행이 1주보다 오래됐으면 결번 구간 전체를 한 호로 백필하고 `stats`에 `backfill: true`를 남긴다.
5. `select id,name,type,endpoint,default_region,default_section,lang,active,fail_count,notes from tcim_sources order by id` → 수집 계획 수립. `active=true`만 대상이고, `endpoint`와 `notes`에 소스별 호출 방법이 적혀 있다.

---

## 2단계 — 수집

소스당 실패하면 1회만 재시도하고, 그래도 안 되면 기록하고 넘어간다. **차단된 피드를 curl 등으로 우회하지 않는다.**

### PubMed (핵심)

`tcim_sources` id 23(주간 쿼리)과 id 24(주요 저널 신간)의 `endpoint`에 저장된 쿼리를 `datetype=edat` + 수집 기간으로 실행한다. 논문 항목의 `url`은 `https://doi.org/(doi)` 형식으로 하고 DOI를 반드시 병기한다. PubMed 출처 표기를 유지한다.

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

### 한국

- KIOM 채용 `https://kiom.re.kr/menu.es?mid=a10503020000` — 본문 미렌더 이력 있음
- NIKOM 채용 `https://nikom.or.kr/nikom/board/index.do?menu_idx=62&manage_idx=45`
- 복지부 보도자료 `https://www.mohw.go.kr/board.es?mid=a10503010200&bid=0027` — robots 차단 이력 있음

실패하면 WebSearch로 대체하고, **국내 소식이 비면 비었다고 정직하게 쓴다.**

### 미국 연방 채용

`tcim_sources` id 20의 endpoint(자체 프록시, WebFetch 가능)를 호출한다. `q=` 값을 `integrative medicine`, `complementary medicine`, `traditional medicine`으로 바꿔 2~3회 검색한다. 기간 내 신규 게시(posted)만 채택한다.

### Gmail 알림과 뉴스레터

**검색은 라벨 ID가 아니라 라벨명으로 해야 동작한다.** 라벨 ID(`label:Label_...`) 쿼리는 0건을 반환하므로 쓰지 않는다.

- `label:TCIM-Jobs newer_than:8d` (채용 알림)
- `label:TCIM-News newer_than:8d` (뉴스레터)

백필 주에는 `newer_than` 값을 기간에 맞춰 늘린다.

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
- **점수**: 0~100. 정책 직접성, 근거 수준(설계와 규모), 지역 다양성, 신규성 기준.
- **선정**: 헤드라인 3~5건(섹션 불문 최상위), 섹션별 카드 최대 8건, 선별에서 빠진 관련 항목은 `block='all'`(참고 목록). 소식이 적은 주면 적은 대로 정직하게 쓴다.

### 문체 규칙

**나열에 가운뎃점(·)을 쓰지 않는다.** 쉼표나 '와/과', '및'으로 연결한다. 사용자가 가운뎃점 남용을 부자연스러운 AI 문체로 여긴다. 다만 한·중·일, 정책·규제처럼 관례적으로 붙여 쓰는 표기와 고유명사는 그대로 둔다.

---

## 4단계 — 발행

`execute_sql`을 쓴다. 긴 한국어 문자열은 `$q$...$q$` 달러 인용을 쓰면 따옴표 이스케이프 문제가 없다.

1. **tcim_items insert**: `(source_id, title, title_ko, url, published_at, section, region, countries, tags, summary_ko, lang, score, week_no)`. `source_id`는 `tcim_sources` 매칭(없으면 null), `week_no`는 `period_end` 기준 ISO 주 `'YYYY-Www'`. `on conflict (url) do nothing`을 쓴다.
2. **tcim_briefings insert**: `issue_no, period_start, period_end, headline_md, regional_notes, implication_md, stats, published_at=now()`. `regional_notes`는 7개 지역 각 1줄 한국어 jsonb이고 소식 없는 지역은 `'—'`. `implication_md`는 시사점 3~5문장. `stats`는 `{"collected":n,"selected":n,"sources_ok":[...],"sources_failed":[...]}`.
3. **tcim_briefing_items insert**: url로 `tcim_items`의 id를 조인해 `(briefing_id, item_id, block, rank)`를 연결한다. 같은 항목이 headline과 섹션 블록에 중복 연결되는 것은 정상이다.
4. **tcim_sources update**: 성공 소스는 `last_ok_at=now()`, 실패 소스는 `fail_count=fail_count+1`. `fail_count`가 3 이상이 된 소스는 `implication_md` 끝에 `소스 점검 필요: (이름)` 1줄을 추가한다. 소스 동작 방식에 대해 새로 알아낸 사실은 `notes`에 날짜와 함께 덧붙인다.
5. **검증**: `select count(*) from tcim_briefing_items where briefing_id=(이번 호 id)`로 연결 수를 확인한다.
6. 발행일이 그 달 1~7일이면(월 1회) `implication_md` 끝에 소스 헬스 요약 1문단을 덧붙인다.

---

## 5단계 — 구독자 발송 준비

**Gmail 커넥터에는 발송 도구가 없다.** `create_draft`로 초안까지만 만들고 실제 발송은 사용자가 Gmail에서 직접 누른다. 이 사실을 최종 메시지에 반드시 알린다.

1. `select email from tcim_subscribers where status='approved' order by id` → 승인된 수신자. **0명이면 초안을 만들지 말고 이 단계를 건너뛴다.**
2. `to`에는 사용자 본인(`jbh8284@gmail.com`)만 넣고, 승인된 수신자는 **전원 `bcc`**에 넣는다. 수신자끼리 주소가 보이면 안 되므로 `to`나 `cc`에 넣지 않는다. 단 **본인 주소가 승인 목록에 있으면 `bcc`에서는 뺀다.** 같은 사람에게 두 번 가지 않게 한다.
3. `subject`: `TCIM 위클리 제N호 — (헤드라인1 축약), (헤드라인2 축약) (M/D~M/D)`
4. **`htmlBody`와 `body`를 둘 다 채운다.** 본체는 `htmlBody`이고 `body`는 평문 대체본이다.
   - `htmlBody`는 저장소의 `email-template.html`을 뼈대로 쓴다. `{{ISSUE_NO}}`, `{{PERIOD}}`, `{{INTRO}}`, `{{COUNTS}}`를 채우고 카드 블록을 헤드라인 수만큼 복제한다.
   - 카드 좌측 색띠와 라벨 색은 섹션에 맞춘다. policy `#0f6b5c`, evidence `#3554a5`, jobs `#a05a1f`.
   - **각 항목 요약은 2~3문장으로 쓴다.** 한 줄로 줄이지 않는다. DB의 `summary_ko`를 메일 문장으로 다듬어 쓰되 사실을 바꾸지 않는다.
   - **링크는 절대 맨 URL로 쓰지 않는다.** 반드시 `<a href="https://zzangbo.github.io/tcim/?issue=N">제N호 전체 보기</a>` 형태의 앵커 텍스트로 넣는다. 평문에 맨 URL을 두면 메일 클라이언트가 `google.com/url?q=...` 리다이렉트로 감싸서 본문에 흉한 긴 문자열이 그대로 보인다.
   - 외부 이미지나 웹폰트를 넣지 않는다. 스타일은 전부 인라인으로 두고 표 기반 레이아웃을 유지한다. 네이버와 다음 웹메일에서 깨지지 않아야 한다.
   - 맨 끝에 `수신을 중단하시려면 이 메일에 회신해 주세요.` 1줄. 시사점과 소스 현황은 넣지 않는다.
5. 실제 발송 여부를 알 수 없으므로 `last_sent_at`은 갱신하지 않는다.
6. `select count(*) from tcim_subscribers where status='pending'`. 1건 이상이면 최종 메시지 끝에 `구독 신청 N건 대기`를 덧붙인다.

**승인은 사용자가 별도로 지시할 때만 한다. 루틴이 스스로 `status`를 `approved`로 바꾸는 일은 절대 없다.**

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
TCIM 위클리 제N호 발행 완료 (M/D~M/D, 선별 Y건)
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
- **2026-08-03** 샌드박스 브라우저는 외부망이 막혀 있다. 웹앱을 브라우저로 검증하려면 Playwright 라우트 가로채기로 Supabase 응답을 대신 넣어야 한다.
