-- TCIM Global Watch — Supabase 스키마 참조본
-- 프로젝트: wlvhmuudjylaayunnkop
--
-- 이 파일은 참조본이다. 실제 DB와 어긋나면 DB가 정답이고 이 파일을 맞춘다.
-- 웹앱은 publishable(anon) 키로 붙으므로 보호는 전적으로 RLS가 한다.

-- ─────────────────────────────────────────────────────────────
-- 자료원 레지스트리
-- endpoint 와 notes 에 소스별 호출 방법과 알려진 제약이 적혀 있다.
-- ─────────────────────────────────────────────────────────────
create table if not exists public.tcim_sources (
  id              bigint generated always as identity primary key,
  name            text not null,
  type            text not null,              -- rss | page | board | api | query | social | manual
  endpoint        text not null,              -- URL 또는 검색 쿼리 본문
  default_region  text,                       -- GLOBAL|AFR|AMR|SEA|EUR|EMR|WPR
  default_section text,                       -- policy|evidence|jobs|other
  lang            text default 'en',
  active          boolean default true,
  fail_count      integer default 0,          -- 3 이상이면 브리핑에 '소스 점검 필요' 표시
  last_ok_at      timestamptz,
  notes           text                        -- 실행에서 알아낸 사실을 날짜와 함께 누적
);

-- ─────────────────────────────────────────────────────────────
-- 수집 항목. url 이 유니크 키이자 중복 제거의 기준.
-- 논문은 url 을 https://doi.org/(doi) 형식으로 통일한다.
-- ─────────────────────────────────────────────────────────────
create table if not exists public.tcim_items (
  id           bigint generated always as identity primary key,
  source_id    bigint references public.tcim_sources(id),
  title        text not null,
  title_ko     text,                          -- 영어 원문이면 한국어 제목
  url          text not null unique,
  published_at date,                          -- 확인 불가 시 null
  section      text not null,
  region       text not null,
  countries    text[] default '{}',           -- ISO2
  tags         text[] default '{}',           -- 한국어 주제/문서유형 태그
  summary_ko   text,                          -- 사실 2문장 + 연구자 관점 1문장
  lang         text,
  score        integer,                       -- 0~100
  week_no      text,                          -- period_end 기준 ISO 주 'YYYY-Www'
  created_at   timestamptz default now(),
  fts          tsvector
);

-- ─────────────────────────────────────────────────────────────
-- 발행 호
-- ─────────────────────────────────────────────────────────────
create table if not exists public.tcim_briefings (
  id             bigint generated always as identity primary key,
  issue_no       integer not null,            -- 웹앱 딥링크 ?issue=N 의 N
  period_start   date not null,
  period_end     date not null,
  headline_md    text,
  regional_notes jsonb,                       -- 7개 지역 각 1줄, 소식 없으면 '—'
  implication_md text,
  stats          jsonb,                       -- {collected, selected, sources_ok[], sources_failed[]}
  published_at   timestamptz
);

-- 호와 항목의 연결. 같은 항목이 headline 과 섹션 블록에 중복 연결되는 것은 정상.
create table if not exists public.tcim_briefing_items (
  briefing_id bigint not null references public.tcim_briefings(id) on delete cascade,
  item_id     bigint not null references public.tcim_items(id) on delete cascade,
  block       text not null,                  -- headline|policy|evidence|jobs|all
  rank        integer
);

-- 국가 → WHO 지역 매핑
create table if not exists public.tcim_country_region_map (
  iso2       text not null primary key,
  name_en    text not null,
  name_ko    text,
  who_region text not null
);

-- ─────────────────────────────────────────────────────────────
-- 비공개 설정. RLS 켜져 있고 정책이 하나도 없다 = 외부에서 절대 못 읽는다.
-- service_role(MCP)로만 접근된다. github_token, usajobs_key 등.
-- ─────────────────────────────────────────────────────────────
create table if not exists public.tcim_private_config (
  key        text not null primary key,
  value      text not null,
  updated_at timestamptz default now()
);

-- ─────────────────────────────────────────────────────────────
-- 구독자. 웹앱에서 익명 INSERT 만 가능하고 SELECT 정책이 없다.
-- 신청은 무조건 pending 으로만 들어가고, 승인은 사람이 지시할 때만 한다.
-- ─────────────────────────────────────────────────────────────
create table if not exists public.tcim_subscribers (
  id           bigint generated always as identity primary key,
  email        text not null,
  status       text not null default 'pending',
  note         text,
  source       text default 'web',
  created_at   timestamptz not null default now(),
  approved_at  timestamptz,
  last_sent_at timestamptz,
  welcomed_at  timestamptz,          -- 환영 메일 초안을 만든 시각. 중복 생성 방지용
  constraint tcim_subscribers_status_chk check (status in ('pending','approved','rejected','unsubscribed')),
  constraint tcim_subscribers_email_chk  check (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' and length(email) <= 254),
  constraint tcim_subscribers_note_chk   check (note is null or length(note) <= 200)
);
create unique index if not exists tcim_subscribers_email_uniq
  on public.tcim_subscribers (lower(email));

-- ─────────────────────────────────────────────────────────────
-- RLS
-- ─────────────────────────────────────────────────────────────
alter table public.tcim_sources           enable row level security;
alter table public.tcim_items             enable row level security;
alter table public.tcim_briefings         enable row level security;
alter table public.tcim_briefing_items    enable row level security;
alter table public.tcim_country_region_map enable row level security;
alter table public.tcim_private_config    enable row level security;
alter table public.tcim_subscribers       enable row level security;

-- 웹앱이 읽어야 하는 것들 = 공개 읽기
create policy tcim_sources_read        on public.tcim_sources           for select using (true);
create policy tcim_items_read          on public.tcim_items             for select using (true);
create policy tcim_briefings_read      on public.tcim_briefings         for select using (true);
create policy tcim_briefing_items_read on public.tcim_briefing_items    for select using (true);
create policy tcim_crm_read            on public.tcim_country_region_map for select using (true);

-- 구독 신청: INSERT 만, 그것도 pending 으로만. 명단 조회 경로는 열지 않는다.
create policy tcim_subscribers_anon_insert on public.tcim_subscribers
  for insert to anon, authenticated
  with check (status = 'pending' and source = 'web');

-- tcim_private_config 는 정책을 만들지 않는다. 그것이 보호 방식이다.

-- ─────────────────────────────────────────────────────────────
-- 검증용 쿼리 — 정책을 손댔으면 아래가 기대대로 나오는지 확인할 것
-- ─────────────────────────────────────────────────────────────
-- 1) 익명 신청은 201
--    curl -X POST "$SB/rest/v1/tcim_subscribers" -H "apikey: $ANON" \
--         -H "Content-Type: application/json" -H "Prefer: return=minimal" \
--         -d '{"email":"a@b.co","source":"web"}'
-- 2) status 위조는 401  →  {"email":"c@d.co","status":"approved","source":"web"}
-- 3) 명단 조회는 빈 배열  →  curl "$SB/rest/v1/tcim_subscribers?select=*" -H "apikey: $ANON"

-- ─────────────────────────────────────────────────────────────
-- 메일 원고와 발송 기록 RPC (2026-11-09). 세션은 원고만 넣고 GitHub Actions 가 보낸다.
-- 둘 다 service_role 전용이다. 원고에는 수신자를 넣지 않는다.
-- ─────────────────────────────────────────────────────────────
create table if not exists public.tcim_mail_jobs (
  issue_no   integer not null,
  revision   integer not null default 1,
  payload    jsonb not null,          -- period_start, period_end, intro, counts, subject_headlines[], headlines[]
  created_at timestamptz not null default now(),
  primary key (issue_no, revision)
);
alter table public.tcim_mail_jobs enable row level security;  -- 정책 없음

-- PostgREST 는 lower(email) 식 인덱스를 on_conflict 대상으로 못 쓴다. 그래서 RPC 로 기록한다.
create or replace function public.tcim_record_sends(p_issue integer, p_revision integer, p_results jsonb)
returns integer language sql set search_path = public as $$
  with ins as (
    insert into tcim_sends (issue_no, revision, email, status, provider, provider_id, error)
    select p_issue, p_revision, r->>'email', r->>'status', coalesce(r->>'provider','resend'),
           r->>'provider_id', r->>'error'
    from jsonb_array_elements(p_results) r
    where r->>'status' in ('sent','failed')
    on conflict (issue_no, revision, lower(email)) do update
      set status = excluded.status, provider_id = excluded.provider_id,
          error = excluded.error, attempted_at = now()
      where tcim_sends.status <> 'sent'
    returning 1
  )
  select count(*)::int from ins;
$$;
revoke all on function public.tcim_record_sends(integer, integer, jsonb) from public, anon, authenticated;
grant execute on function public.tcim_record_sends(integer, integer, jsonb) to service_role;
