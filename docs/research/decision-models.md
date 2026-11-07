# 팀 위키 지침 검토에 쓰는 의사결정 모델

2026년 11월 7일. 이 실험은 두 지침의 적용 대상과 허용 행동이 달라지는지 살피는 과정이다. 어느 지침을 게시할지는 담당자가 결정한다. 아래 모델 성능 수치는 각각 다른 데이터에서 측정했다.

## 확인 결과

| 대상 | 작동 원리 및 접근 | 이번 실행 |
|---|---|---|
| TypeSafe Jev | 서버가 원문과 질문을 받아 호출자가 정한 후보 중 하나와 확률 분포를 반환한다. 공식 Python SDK와 별도로 tumf의 MIT CLI가 있다. 원격 모델의 내부 가중치·학습 알고리즘은 이 SDK에서 확인할 수 없다. | 설치된 CLI 0.6.2와 공식 인증을 확인했다. 공개 합성 지침 한 쌍을 jev-1.14.0에 보내 응답을 받았다. |
| Microsoft Decision-1 | Microsoft가 Qwen3.5-9B를 후학습해 단일 패스 선택지 채점을 제공한다. Foundry의 전용 decision API는 배포명을 받고 answers를 반환한다. Microsoft PyRIT의 LiteLLM 어댑터도 typed 판단을 호출한다. | 공식 모델 카드, 배포 문서, Microsoft 측 클라이언트 코드를 검토했다. 실서비스 호출·배포와 체크포인트 실행은 하지 않았다. |
| Kakao Kanana-2-v-decide-3b-2611 | 3.67B 파라미터. 상태·질문과 후보를 따로 인코딩하고, 정규화된 임베딩 내적과 softmax로 채점한다. 후보 벡터는 캐시한다. 기본 서버는 127.0.0.1에서 System One 형식 요청을 받는다. | 11월 6일 공개된 모델 카드, 라이선스, 모델·요청·서버 코드를 받았다. 공식 build_pairs와 answer_from_logits를 가상 logits로 실행해 반환 형식을 확인했다. 가중치는 내려받지 않았으며 한국어 문서 추론은 미측정이다. |

[TypeSafe 소개](https://docs.typesafe.ai/introduction) / [공식 SDK의 응답 계약](https://github.com/typesafe-ai/typesafe-sdk-python/blob/f36e68549ceca3191e5791e5f99ea1baa1a258b5/src/typesafe_sdk/_schemas/models.py#L47-L85) / [tumf CLI 전송·오류 경로](https://github.com/tumf/jev-cli/blob/980cb98f5f529ba310ce4c7481a55e034b0a0829/src/jev_cli/__init__.py#L221-L303) / [MS 모델 카드](https://ai.azure.com/catalog/models/Microsoft-Decision-1?publisher=microsoft) / [MS 배포·호출 방법](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-microsoft-decision) / [MS PyRIT 호출 경로](https://github.com/microsoft/PyRIT/blob/25417ff73f8e2ff2566c4074514feaa3d3a646e2/pyrit/prompt_target/litellm_decision_target.py#L123-L168) / [Kakao 인코딩 및 채점 코드](https://huggingface.co/kakaocorp/kanana-2-v-decide-3b-2611/blob/1489062def4145ae3a0a9261fbac4f4d88a8c6d1/modeling_kanana_v_decide.py#L121-L197)

## 같은 한국어 입력으로 확인한 범위

`jev auth status`에서 자격 증명이 등록됐고 `jev auth test --provider official`은 유효한 키와 모델명 jev-1.14.0을 반환했다. 공식 엔드포인트 재지정 환경변수는 없었다. 재현 입력은 `live-request.json`, 실제 원 응답은 `live-choice.json`에 있다. `jev run --provider official live-request.json`은 같은 질문을 다시 보내는 명령이다. 최초 실제 호출은 `jev choice`였고 모델 이름을 생략해 서버가 반환한 버전을 기록했다.

신입사원 신청 기한이 7일과 14일인 예시에서 conflict 확률 0.95, compatible 0.05, insufficient 0.00, confidence 0.92를 반환했다. 둘 다 7일 안에 신청하면 양쪽을 충족한다. 차이는 8~14일의 허용 여부에 있다. 후속 평가의 질문은 “두 지침의 적용 범위가 겹치고 실제 허용 행동이 달라 담당자 검토가 필요한가?”가 적절하다. 후보 집합이나 문장 순서를 바꾸면 값이 달라질 수 있다.

제품에서 보관할 값은 두 문서의 버전과 인용 범위, 입력 순서, 질문과 후보 정의, 모델 버전, 판정 원본이다. 누락·오류·타임아웃을 일치로 처리하면 검토가 조용히 생략된다. `jev-cli` exit 1은 응답/비재시도 API 오류, 2는 입력/설정 오류, 3은 인증/인가, 4는 재시도 가능한 실패다. 정상 응답에서도 후보 키, 확률의 유한성·범위, 모델명을 검사한다. 재시도할 때 원문이 바뀌었다면 현재 버전으로 다시 평가한다.

## 논문에서 프로젝트로 가져올 시험

다운로드한 PDF 3종에서 방법, 결과표, 비교군, 한계와 평가 부록을 확인했다. PDF와 추출 텍스트를 F 드라이브 연구 폴더에 보관했다. 모든 부록·모든 선행논문을 전수 검독했다는 의미로 사용하지 않는다.

1. Zhang 외, *Same Scores, Different Decisions*. ContractNLI에서 계약·대상 문장을 고정하고 보이는 가설 수, 요청 답변 수와 순서를 바꿨다. §4.2 및 표 3~4에서 추가 93건 중 Jev가 84건에서 같은 판단을 반복했지만 이 가운데 17건은 계속 틀렸다. 비교 대상 Sonnet은 76건에서 같은 판단을 보였고 이 중 6건이 계속 틀렸다. 작은 paired 표본과 영어 계약이라는 범위가 있다. 우리 시험은 A/B 원문의 순서를 바꾸고, 한 번이라도 틀린 쌍과 매번 틀린 쌍을 따로 센다. [논문 원문](https://arxiv.org/html/2609.27678v2)
2. Deußer 외, *Evaluating and Benchmarking the System One Model Jev*. jev-1.13.0을 37개 데이터셋에 총 346,009회 요청했다. 10월 29일 개정본 §4.1, §4.3 및 §6에서 독일 약관 AGB-DE의 양성 4.9% 상황에 고정 임계값 F1=0.204, AUROC=0.784를 보고했다. 결과는 단일 템플릿·버전에 의존하며 반복 분산을 재지 않았다. §5에서는 여러 단계가 필요한 작업에서 무효 행동을 반복하는 경우도 관측했다. 우리의 희소 충돌을 놓치는 비용은 일반 분류 정확도로 가려질 수 있다. 별도 보정 데이터에서 보류 기준을 정하고 운영 데이터에서 충돌 recall, precision, 보류율, 인정된 후보당 검토 시간을 기록한다. [논문 원문](https://arxiv.org/html/2609.37647v2)
3. *Typed Decision Models: An Early Evidence Audit and Evaluation Checklist*. §6 표 6은 선택지 이름 교환, 요청 순서 변경, 모델 버전 기록, 보정과 시험의 분리, 캐시 전후 지연을 다룬다. §8 한계에는 초기 28편이 짧은 기간과 일부 호스팅 모델에 집중된 사실이 있다. 별도 공개 데이터로 우리 도메인을 검증해야 한다. [논문 원문](https://arxiv.org/html/2609.32160v1)

## 8쌍의 문서 순서 시험 결과

2026년 11월 7일, 공개 합성 원문 8쌍을 제시 순서만 바꿔 총 16회 호출했다. `jev run --provider official -`와 모델명 `jev-1.14.0`을 고정했다. 두 원문, 질문 한 문장과 세 가지 선택지 설명을 보냈다. 사례 ID, 기대 라벨과 이유는 모델에 보내지 않았다. 홀수·짝수 사례마다 A→B와 B→A 중 먼저 호출하는 순서를 바꿨다. 각 순서는 한 번만 실행했다.

| 기대 라벨 | 유효 응답 | 기대와 일치 | 관측 |
|---|---:|---:|---|
| 검토 필요 | 8 | 8 | 기한 차이, 허용과 금지, 본문 속 유도 문구, 기산일 차이 |
| 함께 적용 가능 | 6 | 6 | 같은 뜻 재서술, 다른 적용 대상, 겹치지 않는 시행 기간 |
| 문맥 부족 | 2 | 0 | 두 순서 모두 검토 필요 판정 |

16개 응답 모두 모델과 JSON 형식이 유효했고 14개가 사전에 작성한 라벨과 일치했다. 원문 쌍 단위로는 7/8이다. 순서 때문에 최종 라벨이 바뀐 쌍은 0/8이었다. 다만 문맥 부족 사례의 검토 확률은 0.57에서 0.44로 바뀌었다. B→A에서는 검토 0.44와 문맥 부족 0.42가 근접했다. 담당자 화면에는 두 문장의 근거와 판정 유보를 함께 제공할 필요가 있다.

선택된 상위 라벨이 일정해도 점수가 일정하거나 라벨이 맞는 것은 아니다. 이 수치는 같은 작성자가 만든 합성 사례·기대 라벨에 대한 기술 통계다. 16개 중 절반은 같은 문서 쌍의 역순 재사용이며, 별도 검증셋, 동일 순서 재반복, 다른 모델 실측, 실제 규정이 없었다. 임계값이나 실서비스 정확도를 정할 근거가 되기에는 작다. 전체 응답 사용량은 입력 8,230 토큰과 출력 656 토큰이었다.

`jev-pair-pilot-20261107/protocol.json`에는 고정 질문·후보·CLI 버전·원문 해시가 있다. 같은 폴더의 `01-AB.json`부터 `08-BA.json`까지는 실제 요청, 모델 반환값·분포·confidence·사용량, 시각과 소요 시간을 담는다. `summary.json`에는 기대 라벨과 순서별 관측이 있다. `run_paired_pilot.py`는 공개 입력으로 이 시험을 실행한 스크립트다.

## 세 모델 비교 설계

`pilot-cases.json`에 정답과 이유가 있는 공개 합성 8쌍을 작성했다. 사람 2명이 독립 판단하고 합의한 더 큰 보류 집합이 별도로 필요하다. 문서 쌍을 A→B와 B→A로 제출하고 옵션 순서를 바꿔 응답 수준의 안정성을 본다. 문서 계열별로 train/dev/test를 나눠 개정본이 나란히 여러 분할에 들어가는 문제를 줄인다. 기본 비교군은 마감·수치·부정 표현을 대조하는 규칙이다. 누락, 오류, 한 종류의 지침만 남은 삭제 사례를 포함한다. 실행되지 않은 모델은 성능 표에 공란으로 둔다.

Microsoft는 Foundry 배포명과 인증이 필요하다. Kakao 서버는 텍스트뿐 아니라 이미지를 받으며 한 번에 한 요청을 처리한다. 기본값이 긴 입력의 앞뒤를 남겨 중간을 자를 수 있으므로 해당 문단과 버전만 보내고, 필요하면 strict 입력 검사를 쓴다. 카카오가 자체 15,909문항 한국어 벤치마크에서 공개한 72.50은 이 팀 위키의 지침 판단 점수가 아니다. 자체 공개 표에는 Jev와 Microsoft가 비교군으로 들어 있지 않다. [Kakao 모델 카드](https://huggingface.co/kakaocorp/kanana-2-v-decide-3b-2611/blob/1489062def4145ae3a0a9261fbac4f4d88a8c6d1/README.md)

카카오 가중치는 버전별 Kanana Open License 적용 대상이다. §3에는 배포 시 약관·NOTICE·수정 표시와 Powered by Kanana 표시가 있고 §4는 제3자에게 모델을 API·클라우드, SI·온프렘 또는 온디바이스 방식으로 제공하는 특정 활동에 별도 상용 라이선스를 요구한다. §4.2는 해당 조건 밖에서 자체 서비스 개발·운영이 가능하다고 명시한다. 제품 저장소에는 가중치와 모델 코드를 포함하지 않고 옵션 연동 가능성과 조건을 기록하는 구성이 단순하다. [라이선스 원문](https://huggingface.co/kakaocorp/kanana-2-v-decide-3b-2611/blob/1489062def4145ae3a0a9261fbac4f4d88a8c6d1/LICENSE#L32)
