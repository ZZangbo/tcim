"""테스트용 호 데이터. 제2호 실제 내용을 줄여서 쓴다."""

import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def template() -> str:
    return (REPO / "email-template.html").read_text(encoding="utf-8")


def issue_data(issue_no: int = 3) -> dict:
    return {
        "issue_no": issue_no,
        "period_start": "2026-08-03",
        "period_end": "2026-08-16",
        "intro": "전통의학과 보완통합의학의 지난 2주 글로벌 동향입니다.",
        "counts": "수집 62건 중 선별 18건",
        "subject_headlines": ["BRICS 전통의학 선언", "중국 중의약 5개년 계획"],
        "recipients": ["a@example.com", "b@example.com", "c@example.com", "d@example.com"],
        "headlines": [
            {
                "title_ko": "BRICS, 전통의학 전담 선언문 채택하고 전문가 워킹그룹 신설",
                "section": "policy",
                "region": "GLOBAL",
                "summary_ko": (
                    "제16차 BRICS 보건장관회의가 보건장관 선언문에 전통의학과 보완통합의학 "
                    "전담 절을 처음으로 포함했습니다. 다국가 공동연구와 임상시험 등록, 품질과 "
                    "약물감시 표준 협력을 담았습니다. 9월 뉴델리 정상회의의 후속 이행이 "
                    "실효성을 가를 첫 시험대가 됩니다."
                ),
            },
            {
                "title_ko": "중국, 2026~2030년 중의약 서비스체계 강화 5개년 계획 발표",
                "section": "policy",
                "region": "WPR",
                "summary_ko": (
                    "국가중의약관리국과 국가발전개혁위원회가 국무원 승인을 거쳐 제15차 "
                    "5개년 계획기의 중의약 발전계획을 발표했습니다. 2030년까지 전 국민을 "
                    "포괄하는 서비스체계 구축을 목표로 합니다. 목표가 공급 지표에 몰려 있어 "
                    "성과 지표를 어떻게 병기하는지가 관찰 포인트입니다."
                ),
            },
            {
                "title_ko": "범아프리카의회, 전통의약과 토착지식 보호 모델법 제정 결의",
                "section": "policy",
                "region": "AFR",
                "summary_ko": (
                    "범아프리카의회 보건노동사회위원회가 대륙 차원의 모델법 개발 결의를 "
                    "채택했습니다. 전통시술자 인증 기준과 토착지식의 법적 보호를 담을 "
                    "예정입니다. 구속력이 없어 실제 효과는 각국 입법 전환율에 달려 있습니다."
                ),
            },
            {
                "title_ko": "국가 치매관리에의 동아시아 전통의학 통합: 한·중·일 비교정책 분석",
                "section": "evidence",
                "region": "WPR",
                "summary_ko": (
                    "Integrative Medicine Research에 3국의 국가 치매관리 정책 비교분석 "
                    "논문이 실렸습니다. 세 나라는 전통의학의 제도적 지위와 공적 급여 편입 "
                    "정도가 서로 다릅니다. 국내 치매국가책임제 논의를 국제 비교틀에 올려놓을 "
                    "수 있는 참고문헌입니다."
                ),
            },
        ],
    }


def research_items() -> list[dict]:
    """'이번 호 주요 연구' 절용. 제9호 실제 항목을 줄여서 쓴다."""
    return [
        {
            "title_ko": "중국 DRG/DIP 개혁하 중의 우세병종 성과기반 지불의 공공가치 평가",
            "journal": "Front Public Health",
            "year": 2026,
            "url": "https://doi.org/10.3389/fpubh.2026.1902781",
            "summary_ko": (
                "타이위안 중의 우세병종 입원 7,985건을 분석한 다기관 준실험연구입니다. "
                "성과기반 지불은 입원당 본인부담 300위안 감소와 환자중심 공공가치지수 상승과 "
                "연관됐습니다. 보험기금 지출과 삶의 질에서는 유의한 차이가 없었습니다."
            ),
        },
        {
            "title_ko": "요통 진료지침 권고 중재의 비용효과성: 체계적 문헌고찰",
            "journal": "PLoS Med",
            "year": 2026,
            "url": "https://doi.org/10.1371/journal.pmed.1005273",
            "summary_ko": (
                "진료지침 권고 요통 중재의 경제성 평가 20편을 분석한 체계적 고찰입니다. "
                "요가, 침, 인지치료, 자가관리 지원이 일반 진료보다 효과가 크고 비용이 적어 "
                "비용절감적일 수 있다고 보고했습니다. 근거는 모두 고소득국가에서 나왔습니다."
            ),
        },
        {
            "title_ko": "국가 필수의약품 목록의 허브의약품 선정 근거기준 개발(태국)",
            "journal": "BMC Complement Med Ther",
            "year": 2026,
            "url": "https://doi.org/10.1186/s12906-026-05494-0",
            "summary_ko": (
                "태국 국가필수의약품목록의 허브의약품 선정에 쓸 근거 평가 기준을 만든 "
                "혼합방법 연구입니다. WHO와 EMA 기준을 참고해 효능 6개 측면과 안전성 7개 "
                "구성요소를 세 단계로 판정하게 했습니다. 첩약 급여 품목 선정의 비교 자료가 됩니다."
            ),
        },
    ]
