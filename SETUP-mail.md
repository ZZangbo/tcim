# 메일 발송 설정 (사람이 한 번만 하는 일)

대시보드에서 해야 하는 일만 모았다. 끝나면 이 문서는 다시 볼 일이 없다.

구조는 이렇게 갈린다. **발신과 수신을 다른 이름에 두는 것이 핵심**이고, 그래야 SPF 레코드가 서로 충돌하지 않는다.

| 이름 | 역할 | 누가 |
| --- | --- | --- |
| `news.jbhlab.com` | 발신 전용. DKIM 과 SPF | Resend |
| `jbhlab.com` (아펙스) | 수신 전용. MX 와 SPF | Cloudflare Email Routing |
| `tcim@jbhlab.com` | 회신과 수신 중단이 들어오는 주소 | → `jbh8284@gmail.com` 으로 포워딩 |

**★검증이 끝나기 전에는 한 통도 보내지 말 것.** `_dmarc.jbhlab.com` 에 `p=reject` 가 걸려 있어서, 인증이 붙기 전에 보내면 스팸함이 아니라 **수신 거부**된다. 도메인 첫인상도 나빠진다.

---

## 1. Cloudflare Email Routing — 수신 (먼저 한다)

Resend 도메인 검증에 시간이 걸리므로 이걸 먼저 걸어두면 대기가 겹치지 않는다.

1. Cloudflare 대시보드 → `jbhlab.com` → **Email** → **Email Routing** → 시작
2. **Destination addresses** 에 `jbh8284@gmail.com` 추가 → Gmail 로 오는 확인 메일의 링크 클릭
3. **Routing rules** → Custom address 로 `tcim@jbhlab.com` 을 만들고 목적지를 위 주소로
4. Cloudflare 가 MX 세 개와 SPF TXT 하나를 **아펙스에** 자동으로 넣는다. 그대로 두면 된다
5. 확인: 아무 계정에서 `tcim@jbhlab.com` 으로 한 통 보내 Gmail 에 들어오는지 본다

현재 `jbhlab.com` 에는 MX 도 SPF 도 없다. 그래서 이 단계에서 깨뜨릴 기존 설정이 없다.

---

## 2. Resend — 발신

1. `resend.com` 가입
2. **Domains → Add Domain** 에 `news.jbhlab.com` 입력. 아펙스(`jbhlab.com`)를 넣지 말 것
3. Resend 가 DNS 레코드 몇 개를 보여준다. DKIM 용 TXT, SPF 용 TXT, 반송 처리용 MX 가 보통 포함된다. **화면에 보이는 값을 그대로** Cloudflare 에 넣는다. 여기 적힌 예시를 옮겨 적지 말고 화면 값을 쓴다
4. **★Cloudflare 에 넣을 때 프록시를 끈다(회색 구름, DNS only).** CNAME 은 기본이 주황색 구름인데, 그 상태면 Cloudflare 가 값을 가로채서 검증이 영영 통과하지 않는다. 증상은 "레코드는 넣었는데 Resend 가 계속 미검증이라고 한다" 로 나타난다. 이 설정에서 가장 흔한 실패다
5. Resend 에서 **Verify** 를 누르고 초록불을 확인한다. 보통 몇 분, DNS 전파에 따라 더 걸릴 수 있다
6. **API Keys → Create API Key.** 권한은 발송(Sending access)만 주면 된다

---

## 3. 넘겨줄 것

API 키는 Supabase 에 직접 넣는 편이 낫다. 대화 기록에 남지 않는다.

```sql
insert into tcim_private_config (key, value)
values ('resend_api_key', 're_여기에키')
on conflict (key) do update set value = excluded.value;
```

넣었다는 것과 **도메인 검증 초록불을 봤다는 것** 두 가지만 알려주면 된다.

---

## 4. 그다음은 자동이다

1. 테스트 발송 한 통을 `jbh8284@gmail.com`, `jarofclay@hanmail.net`, `clayjar@naver.com` 세 곳으로 보낸다. Gmail, 다음, 네이버를 한 번에 본다
2. 각 메일에서 원문 보기를 열어 **SPF, DKIM, DMARC 가 전부 PASS** 인지 확인한다
3. 받은편지함에 들어갔는지 스팸함에 갔는지 확인한다. 지금까지 알 수 없던 것이 이 시점부터 보인다
4. Resend 무료 플랜이 푸터에 브랜딩을 넣는지 확인한다. 넣으면 Brevo 로 갈아탈지 판단한다. `tcim_private_config.mail_provider` 한 줄이다
5. 전부 통과하면 `auto_send` 를 `true` 로 바꾼다. 그때부터 발행과 동시에 나간다

**발행일(8/17)과 분리해서 이번 주에 끝내는 것이 좋다.** 발행 당일에 인프라를 처음 시험하면 문제가 생겼을 때 물러설 곳이 없다.

---

## 알아둘 한도와 되돌리기

| 항목 | 값 |
| --- | --- |
| Resend 무료 | 월 3,000통, 하루 100통, 도메인 1개 |
| Cloudflare Email Routing | 무료, 용량 제한 없음 |
| 하루 100통의 의미 | 수신자 한 명당 한 통을 보내므로 **구독자 100명까지** 하루에 다 나간다 |
| 넘어서면 | Brevo 무료(하루 300통)로 `mail_provider` 변경 |

`auto_send` 를 `false` 로 되돌리면 언제든 초안 전용으로 돌아간다. 코드를 고칠 필요가 없다. **되돌릴 수 있다는 것이 자동 발송을 켜도 되는 조건이다.**
