# PageIndex 실증과 선행연구

2026년 11월 7일. 팀 위키에서 검토자가 긴 원문의 해당 절을 열도록 하는 기능을 조사했다. 사용한 PageIndex는 VectifyAI 공개 저장소의 `2ac8694bf8fe89a3840dda9bdb88db5119b77fc4`(패키지 0.2.10, MIT)이다. 프로젝트 원본 파일은 수정하지 않았다.

## 공개 코드의 역할

| 경로 | 실제 구성 | 팀 위키에서의 역할 |
|---|---|---|
| Markdown | `md_to_tree`가 제목과 한 줄짜리 굵은 제목을 읽어 위계, 1부터 시작하는 줄 번호, 해당 절 텍스트를 만든다. 요약·문서 설명·축약은 끌 수 있다. | 편집 가능한 지침 원문을 절 단위로 열기 |
| PDF | Flash가 레이아웃 또는 PDF 북마크에서 목차를 추출한다. 섹션에 물리 쪽 범위를 붙인다. 원문에 텍스트 레이어가 필요하다. CLI에서 `--no-summary --optimize off`로 구조만 생성할 수 있다. | 긴 규정이나 매뉴얼에서 원문 페이지 열기 |
| 로컬 SDK | `LocalAPI.submit_document`는 PDF만 받는다. 로컬 저장소는 신규 제출에 UUID를 부여하고 메타데이터·트리·페이지를 저장한다. 에이전트에는 목차 조회와 페이지 읽기 도구를 따로 준다. | Markdown 폴더는 문서마다 별도 Markdown 진입점을 호출해야 한다. 날짜·유효성·담당자의 판단을 보존하는 업무는 앱이 맡는다. |
| 클라우드 | 제작사 SDK 표에서 호스팅 저장, 복잡한 문서 OCR, 폴더, MCP를 클라우드 기능으로 소개한다. | 첫 공개 폴더 시험에서 필요하지 않다. |

[Markdown 파싱](https://github.com/VectifyAI/PageIndex/blob/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4/pageindex/page_index_md.py#L32-L89) · [트리·원문 생성](https://github.com/VectifyAI/PageIndex/blob/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4/pageindex/page_index_md.py#L192-L302) · [Flash PDF](https://github.com/VectifyAI/PageIndex/blob/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4/pageindex/flash/api.py#L237-L330) · [로컬 제출](https://github.com/VectifyAI/PageIndex/blob/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4/pageindex/local_api.py#L134-L201) · [페이지 읽기 도구](https://github.com/VectifyAI/PageIndex/blob/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4/pageindex/agent_tools.py#L1011) · [제품 기능 범위](https://github.com/VectifyAI/PageIndex/blob/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4/README.md#L179-L213)

## 실행 결과

원본 CLI와 Python 함수에 같은 한국어 fixture 4개를 넣었다. 각 모드가 만든 제목·ID·줄·본문 배열이 모두 같았다. 시험 프로세스는 외부 소켓 연결을 차단했고 실제 시도는 0회였다. Windows asyncio 내부의 깨우기 소켓만 허용했다.

| 원문 | 신청 기한 절 | 원문 보존 관찰 |
|---|---|---|
| 원본 7일 | ID 0001, 4행 | 첫 제목보다 앞의 머리말은 트리에서 빠졌다. |
| 앞에 정의 절만 추가 | ID 0002, 6행 | 신청 기한 원문이 같아도 식별자가 바뀌었다. |
| 7일을 14일로 수정 | ID 0001, 4행 | 원문이 달라져도 같은 식별자와 줄을 사용했다. |
| 제목 없는 안내문 | 생성 노드 0개 | 원문 두 줄이 있어도 빈 트리가 나왔다. |

실제 Lumer 논문 8쪽을 Flash CLI로 처리했다. 레이아웃 기반 `detected` 결과에서 38개 노드의 시작·끝 쪽이 모두 1–8 안에 있었다. 4.3절은 실제 물리 5쪽을 가리켰다. 5.1절과 5.4절은 원문에 있지만 생성 목차에서 찾을 수 없었다. 그 쪽의 본문은 PDF에 남아 있다. 빈 PDF는 텍스트 레이어가 없어 OCR이 필요하다는 오류가 났다. PDF 시험에서도 외부 소켓 연결은 0회였다. PDF 목차 품질, OCR, 에이전트 질의 정답률의 전체 평가로 일반화할 수 없다.

실행 결과는 [Markdown 목차](../evidence/pageindex-md.json)와 [PDF 쪽 범위](../evidence/pageindex-pdf.json)에 있다. 두 시험 모두 고정한 원본 구현을 호출했다. 정상 CLI에는 시스템 Python의 기존 라이브러리와 F 드라이브에 별도로 설치한 `sortedcontainers==2.4.0`을 사용했다.

같은 체크아웃에서 빌드한 F 드라이브 패키지에서도 Python 3.13이 `pageindex-venv/Lib/site-packages/pageindex`의 0.2.10을 불러와 같은 “신청 기한” 노드를 반환했다. `LocalAPI._index_flash`는 요약을 켜고 모델로 문서 설명을 만든다. PDF 구조만 시험한 위의 CLI 설정과 구분해야 한다. [SDK의 Flash 설정](https://github.com/VectifyAI/PageIndex/blob/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4/pageindex/local_api.py#L264-L288)

## 논문 원문에서 확인한 설계 선택

**Lumer 등, ICAART 2026, pp. 4795–4802.** 연구진은 SEC 공시 1,200개에서 150개 질문을 만들었다. 그중 검색 아키텍처 직접 비교는 75건이다. GPT-4o 생성과 Claude 심사에서 키워드·벡터·메타데이터 검색을 쓰는 에이전트가 계층 목차 방식보다 68%의 쌍대평가에서 선택됐다(§§3.1, 3.2, 3.4, 4.3). 이 값은 정답률이 아니다. 원문 페이지와 질문의 정답을 따로 표시해 비교했다는 점은 이번 앱 평가에 적용할 수 있다. [발행 논문](https://doi.org/10.5220/0014492100004052) · [저자 공개본](https://arxiv.org/abs/2511.18177)

**Hashmi, 2026년 10월 28일 v2, §§3–6.** 통제 문서 4개와 질문 22건에서 트리의 평균 심사 점수는 0.900, 벡터와 혼합 방식은 각각 0.845였다. 별도 FinanceBench 시험은 공개 150문항 중 앞 50건에 제공된 근거 발췌를 썼다. 트리에 목표 문서를 미리 준 조건, 서로 다른 프롬프트와 답변 길이, 생성과 심사를 맡은 모델이 같다는 한계가 있다. 서로 다른 문서의 절 번호를 같은 정답으로 세는 오류 탓에 원래 검색 점수도 철회했다. 초기 버전에서 읽히는 150건·전체 공시 범위·검색 recall 주장은 최신 본문에 맞춰 해석해야 한다. [최신 논문](https://arxiv.org/abs/2604.14222v2)

**PageIndex 제작사 자료.** 공식 소개는 목차를 읽고 필요한 절을 반복해서 찾아 답하는 과정을 설명한다. 제작사가 공개한 98.7%는 Mafin 2.5의 FinanceBench 평가다. 현재 공개 Markdown CLI나 팀 지침 비교 성능과 동일한 실험이 아니다. 공식 저장소가 안내하는 PageIndex 인용 대상은 연구진의 기술 블로그다. [제작사 기술 설명](https://pageindex.ai/blog/pageindex-intro) · [제작사 평가](https://pageindex.ai/blog/Mafin2.5)

두 논문은 공개 PDF를 직접 받아 본문의 방법, 표, 결과, 해석과 한계를 확인했다. 재배포용 앱에 논문 파일을 포함하지 않는다. 로컬 보관 해시는 `adaptive-routing.pdf`의 SHA-256 `ae5477793802209c4efd2b304c8f373367c29b05e3fa9198e7e522d1bcdc6d68`, `lumer.pdf`의 SHA-256 `975027872df10559128653658bcc673cb59e6215c1b311ec6ff656530d7a4d34`이다.

## 앱에 적용할 부분

문서 원본을 읽을 때 버전의 원문 해시와 경로를 저장하고, PageIndex 결과에서 선택한 제목과 줄 또는 쪽을 해당 버전 안의 탐색 단서로 보존한다. 채택 시 당시 원문에서 인용을 다시 대조하고 보존해야 한다. 다음 버전에서는 제목 삽입·동일한 제목의 중복·문서 이동까지 고려해야 한다. 후보가 여러 개면 사람이 다시 고를 수 있게 한다. 제목 없는 자료와 추출에서 빠진 머리말은 전체 원문으로 열 수 있어야 한다.

연구 비교는 동일한 원문 전체와 동일한 조회 권한을 주고 기본 키워드 검색, WeKnora, 목차를 보조로 쓰는 방식을 나란히 둔다. 질문마다 정답을 문서 ID·버전·원문 범위로 지정한다. 측정 항목은 정확한 원문 도달률, 서로 다른 규칙을 한 규칙으로 합친 횟수, 바뀐 근거에 연결된 과거 채택을 찾아낸 비율, 처리시간이다.
