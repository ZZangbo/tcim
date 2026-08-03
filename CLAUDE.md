# TCIM Global Watch

전통의학과 보완통합의학의 글로벌 동향을 격주로 수집해 한국어로 요약 발행하는 파이프라인과 그 결과를 보여주는 웹앱.

## 이 저장소가 무엇의 원본인가

| 파일 | 역할 |
| --- | --- |
| `index.html` | 웹앱 전체. 단일 파일이고 빌드 과정이 없다. GitHub Pages가 main 브랜치를 그대로 서빙한다. |
| `RUNBOOK.md` | **격주 발행 파이프라인의 원본.** 스케줄 작업이 실행 시점에 이 저장소를 clone해서 이 파일을 읽고 그대로 수행한다. |
| `SUBSCRIBERS.md` | **구독자 운영 절차의 원본.** 매일 08:00 KST 일일 점검 작업이 읽는다. 신청 확인, 승인, 환영 메일, 수신 중단. |
| `email-template.html` | 구독 메일 뼈대. 배경색에 의존하지 않는 구조다. **손으로 채우지 말 것** — `tcim/render.py`가 읽어서 치환한다. |
| `tcim/` | 파이프라인의 결정적인 부분. `plan`(날짜와 격주 가드), `render`(메일 조립), `preflight`(발송 전 검사). 표준 라이브러리만 쓴다. |
| `tests/` | `PYTHONPATH=.:tests python3 -m unittest discover -s tests` |
| `DESIGN.md` | 어디까지 코드로 내렸고 왜 거기서 멈췄는지. 발송 방식과 확장 계획도 여기. |
| `schema.sql` | Supabase 스키마와 RLS 정책의 참조본. 실제 DB와 어긋나면 DB가 정답이고 이 파일을 맞춘다. |

## 3층 구조

1. **저장소(여기)** — 코드와 규칙. 이력이 남는 유일한 곳.
2. **스케줄 작업(클라우드)** — 매주 월요일 07:00 KST에 깨어나되 **발행은 격주**. 크론으로 격주를 표현할 수 없어 직전 발행일과의 간격(13일)으로 판단한다. 쉬는 주는 알림 없이 조용히 종료한다. 트리거 프롬프트는 저장소를 clone하고 `RUNBOOK.md`를 읽으라는 짧은 로더일 뿐이다. **규칙을 바꾸려면 트리거가 아니라 `RUNBOOK.md`를 고친다.**
3. **Supabase(`wlvhmuudjylaayunnkop`)** — 수집 데이터와 운영 상태. 발행 항목, 호, 자료원 상태, 구독자, 비밀값.

## 스케줄 작업 두 개

1. **격주 발행** — 매주 월요일 07:00 KST에 깨어나 13일 가드로 판단. `RUNBOOK.md`
2. **일일 구독 점검** — 매일 08:00 KST. 대기 신청과 환영 대상이 없으면 조용히 종료. `SUBSCRIBERS.md`

## 사람이 손대는 지점

딱 두 군데다. 그 외는 자동이다.

- **구독 승인** — 웹앱 구독 폼은 `status='pending'`으로만 접수한다. 승인은 사람이 지시할 때만 한다.
- **구독 메일 발송** — Gmail 커넥터에 발송 도구가 없어서 루틴은 초안까지만 만든다. 보내기는 사람이 누른다.

## 작업할 때 주의할 것

- **웹앱은 의존성이 없다.** 프레임워크를 들이거나 파일을 쪼개지 말 것. 단일 HTML이라 GitHub Pages에 그대로 올라간다.
- **`index.html`의 `KEY`는 publishable 키다.** 공개돼도 되는 값이고, 보호는 RLS가 한다. service_role 키를 여기 넣으면 안 된다.
- **RLS를 약화시키지 말 것.** `tcim_subscribers`는 익명 INSERT만 허용하고 SELECT 정책이 없다. 명단이 외부에서 조회되면 안 된다. `tcim_private_config`는 정책이 아예 없다.
- **딥링크 규약**은 `?issue=N`이고 N은 `issue_no`다. 알림과 구독 메일이 이 형식에 의존한다.
- 웹앱을 고쳤으면 `RUNBOOK.md`의 링크 규약도 어긋나지 않는지 확인한다.

## 웹앱 검증 방법

클라우드 샌드박스 브라우저는 외부망이 막혀 있어 Supabase에 직접 붙지 못한다. 실제 응답을 curl로 받아 픽스처로 저장한 뒤 Playwright 라우트 가로채기로 주입해 검증한다.

```bash
curl -s "$SB/rest/v1/tcim_briefings?select=*&order=issue_no.desc" -H "apikey: $KEY" -o fx/briefings.json
# page.route('**/wlvhmuudjylaayunnkop.supabase.co/**', ...) 로 픽스처 응답 주입
```

로컬 Mac에서 Claude Code로 작업할 때는 이런 우회가 필요 없다. `python3 -m http.server`로 띄우고 브라우저로 그냥 열면 된다.

## 배포

main에 푸시하면 GitHub Pages가 1분 안에 반영한다. 별도 파이프라인이 없다.

```bash
git add index.html && git commit -m "..." && git push
curl -s "https://zzangbo.github.io/tcim/index.html?cb=$RANDOM" | grep -q "찾는문자열" && echo 반영됨
```
