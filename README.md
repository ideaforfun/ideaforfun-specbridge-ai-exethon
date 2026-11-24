# SpecBridge AI 🧭

**API 변경 → 시스템 영향 → 담당 조직 추천 → 개발 요청서 초안**

라이너 EXE-THON 참가를 위한 **가상 데이터 기반 MVP**입니다.

> 이 프로젝트에 포함된 API 규격, 회사 조직도, 시스템, 개발 이력은 모두 합성된 데모 데이터입니다. 실제 금융/공공 마이데이터 규격 변경을 나타내지 않습니다. API 변경 검토 및 담당 조직 추천은 자동 배정이 아닌 **사람 승인 전 제안**입니다.

## 엑스톤 심사 재현

1. 심사용 키를 환경 변수 `LINER_API_KEY`에 설정합니다. 로컬에서는 `.env.example`을 `.env`로 복사해 값을 넣을 수 있습니다.
2. `streamlit run app.py`를 실행하고 **법령 변경 검토 → 라이너보험 → 직접 내려받기 검토**를 고릅니다.
3. **Liner로 검토 브리핑 생성**을 누릅니다. `/chat/completions`의 엄격한 JSON 스키마로 부서별 질문을 생성하고, 앱이 부서·조문 ID를 검증해 카드와 요청서에 반영합니다.
4. 관계부서 검토를 등록하고 의견·보완 요청을 남깁니다. 내보낸 JSON은 구조화 브리핑과 부서 상태를 담습니다. 실행 책임·승인 책임은 확인이 필요합니다.
5. **전사 조직도**에서 네 가상 회사의 보고 체계를 보고, API 비교에서 **4개 금융사 API 시나리오**를 켜 은행의 중복 책임을 확인합니다.

검토 의견과 요청은 로컬 SQLite에 저장됩니다. `SPECBRIDGE_AUDIT_DB`로 경로를 지정할 수 있습니다. 
Liner에 보내는 법령 검토 자료는 공개 조문 요약과 합성 부서 정책으로 제한됩니다.
API 비교의 별도 검색 기능은 `/tools/search/web`를 사용합니다. 검색 결과는 확인이 필요한 공개 자료 후보입니다.

- [공개 법령 근거](https://www.law.go.kr/lsInfoP.do?lsiSeq=283503&viewCls=lsRvsDocInfoR)
- [Liner Model API](https://liner.com/developers/docs/liner-model-api-chat-completions)
- [Liner Search API](https://liner.com/developers/docs/search-api)

## 시작 코드와 이번 출품에서 만든 범위

- **시작 코드** · 가상 API 전후 비교, 규칙 기반 담당 조직 추천, 요청서 초안, Liner API 어댑터의 기본 호출
- **이번 출품 작업** · 근거 ID와 구조 검증, 두 부서의 R 충돌 판정, 영속 검토 이력, 카드·은행·증권·보험의 합성 조직도, 법령 조문 비교와 관계부서 협업, 모델 질문 카드와 요청서 JSON 통합

## 기술 구성

- Python 3.10+ / Streamlit
- 오프라인 `src/core.py`: 간소화된 JSON API 스펙 비교, 변경 심각도, 조직 후보 추천, 근거 ID, 개발 요청서 초안
- 온라인 `src/liner_client.py`: Liner Model API (`/chat/completions`)와 Liner Search API (`/tools/search/web`)
- API 호출은 사용자가 UI에서 명시적으로 실행할 때만 발생합니다.
- Liner API 키가 없어도 오프라인 화면을 사용할 수 있습니다.

## 로컬 실행

```bash
cd specbridge_codex
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 Streamlit이 알려주는 로컬 주소를 열면 가상 API V1/V2의 분석 결과가 표시됩니다.

## Liner API 연결

1. https://platform.liner.com/ 에서 API 키를 발급받습니다.
2. `.env.example` 파일을 `.env`로 복사합니다.
3. `.env`의 `LINER_API_KEY=`에 자신의 키를 넣습니다. (코드나 채팅에 키를 붙여넣지 마세요.)
4. 앱을 실행하고 왼쪽 사이드바 **Liner Model API 사용**을 켭니다.
5. **Liner Model API로 추천 근거 재검증** 또는 **Liner Search API로 공개 자료 검색** 버튼을 누릅니다.

외부 API가 호출될 때 비용이 발생할 수 있습니다. Search API 요청에는 공식 문서에 따라 `include_knowledge: false`를 명시했습니다.

API 문서:
- https://liner.com/developers/docs/liner-model-api-chat-completions
- https://liner.com/developers/docs/search-api

## 자동 테스트

```bash
python -m unittest discover -s tests -v
```

단위 테스트는 모의 HTTP 응답을 사용합니다. 별도 데모에서 실제 앱 흐름을 재현할 수 있습니다.

## Codex 사용

- Codex 데스크톱/CLI에서 이 폴더를 프로젝트로 엽니다.
- 우선 `AGENTS.md`를 읽게 하고 `CODEX_NEXT_TASK.md`의 내용을 채팅에 붙여넣습니다.
- 기능을 나누어 구현하고 테스트 후 커밋합니다.
- Codex Cloud 사용 시에는 이 폴더를 개인 GitHub 저장소에 올린 뒤 해당 저장소를 연결해야 합니다. `.env`는 절대 올리지 마세요.
- 키가 필요한 실 API 테스트는 사용자 승인하에 안전한 로컬 환경에서 실행합니다.

## 입력 JSON 형식 (MVP 전용)

`data/spec_v1.json`과 `data/spec_v2.json`을 참고하세요.

```json
{
  "version": "V2",
  "apis": [{
    "id": "GET_ACCOUNTS",
    "method": "GET",
    "path": "/accounts",
    "request": [{"name":"org_code","type":"string","required":true,"description":"기관 코드"}],
    "response": [],
    "errors": []
  }]
}
```

**주의:** 표준 OpenAPI 전체 스키마 파서가 아니며, PDF/Excel을 직접 파싱하지 않습니다. 해커톤 이후 별도의 문서 정규화 계층을 추가해야 합니다.

## 서비스 개선 우선순위

1. R&R 조직 책임의 승인·버전·유효기간·권한 관리
2. API 필드 사용 여부를 표시하는 영향 시스템 그래프
3. Liner의 JSON 응답 스키마 검증 및 평가 세트
4. PDF·Excel 업로드, 규격 파싱 검수 UI
5. 개발 티켓 연계 (반드시 수동 승인 필요)
