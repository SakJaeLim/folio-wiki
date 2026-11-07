# 팀 위키 선행연구와 소스 검토

2026년 11월 7일. 팀 위키를 처음 만드는 방법, 서로 다른 지침을 표시하는 방법, 원문 변경 뒤 기존 결정을 재검토하는 방법에 맞춰 문헌을 골랐다. 논문 네 편의 원본 PDF 57쪽에서 방법과 평가, 한계, 설계 사례를 확인했다. 지표는 논문 저자의 실험값이다. 이번 독립 실행은 Tencent 연구 구현의 원문 보관 함수 한 개다.

## 새 위키를 처음 만드는 두 방식

**STORM**은 주제와 비슷한 기존 글에서 취재 관점을 얻는다. 관점마다 질문을 만들고 검색 결과로 대화를 이어간 뒤, 초안 목차를 고치고 절별 자료로 글을 쓴다. 과업 정의, FreshWiki 데이터 선정, 방법, 자동 평가, 편집자 평가, 한계 및 부록 A–E의 의사코드·인용 오류·샘플 글을 검토했다. 사람이 평가한 20개 글 쌍에서 ‘구성이 좋다’는 평가는 기존 outline-driven RAG의 45%에서 STORM의 70%로 늘었다. 검증 가능성의 같은 기준을 통과한 비율은 둘 다 67.5%였다. 영어 글쓰기 평가이고, 팀 지침 변경이나 담당자 채택은 평가 대상이 아니다. [NAACL 논문, 표 6](https://aclanthology.org/2024.naacl-long.347/)

MIT 코드에서 `STORMWikiRunner`는 대화·검색 자료, 목차, 기사·인용을 차례로 저장한다. `generate_section`은 절과 소제목으로 자료를 다시 찾고, `generate_article`은 생성한 절들을 문서에 합친다. 팀 위키에서는 업무별 질문을 목차에 반영하는 부분을 참고할 수 있다. 팀이 사용하는 근거의 범위는 연결한 폴더로 한정하는 편이 취지에 맞는다. STORM 서버나 LLM은 이 조사에서 실행하지 않았다. [실행 경로](https://github.com/stanford-oval/storm/blob/fb951af7744dab086e34962e9bc6fe878e145f83/knowledge_storm/storm_wiki/engine.py#L211-L276) [절 생성](https://github.com/stanford-oval/storm/blob/fb951af7744dab086e34962e9bc6fe878e145f83/knowledge_storm/storm_wiki/modules/article_generation.py#L33-L127)

**Tencent WeChat 연구팀의 WeAgentAI/LLM-Wiki**는 입력 단락과 기존 페이지를 대조해 Markdown 페이지, 링크, 출처 아카이브를 만든다. 질문 시 에이전트가 페이지를 검색·열람하고 링크를 따라간다. Error Book은 반복되는 오류를 다음 생성 프롬프트의 제약으로 바꾸고 기존 페이지를 수정한다. 논문 1–7절과 한계, 부록 A–H에서 자료 선정, 사람 평가, 알고리즘, 페이지 형식, 오류 목록, 비용과 사례를 확인했다. 세 QA 데이터셋별 앞쪽 500문항과 문항에 딸린 문단만 사용했고, 에이전트에 더 큰 조회 예산을 허용했다. 저자가 보고한 LightRAG 대비 F1 개선은 2.0–8.1점이다. 자주 바뀌는 원문의 관리와 오래된 사실 처리는 후속 과제로 명시했다. [arXiv v2, pp. 5–9](https://arxiv.org/abs/2605.25480v2)

MIT 구현의 `WikiAgent.retrieve`는 도구 호출 수를 제한하고, 읽은 페이지가 비면 검색 결과를 다시 열기도 한다. `llm_verify_source_grounding`은 일부 페이지만 샘플링해 발췌와 대조한다. 충돌 처리에서는 링크된 페이지 쌍을 뽑아 각각 처음 2,000자만 모델에 제시하고 모델이 제안한 문장을 기존 본문에서 찾아 교체한다. 조직에서 발행일, 적용 부서, 예외 규정까지 결정할 권한은 이 함수에 정의되어 있지 않다. [에이전트](https://github.com/WeAgentAI/LLM-Wiki/blob/79a5a2d5fb9e07c7e5d21fe704b4eca0c27452ef/llm_wiki_bench/wiki_agent.py#L110-L224) [근거 점검과 충돌 수정](https://github.com/WeAgentAI/LLM-Wiki/blob/79a5a2d5fb9e07c7e5d21fe704b4eca0c27452ef/llm_wiki_bench/bench_ingest.py#L3262-L3574)

**직접 실행한 사례.** 공식 소스에서 `_save_article_original`을 import해 같은 제목과 경로로 7일 원문, 14일 수정본을 차례로 전달했다. 둘은 동일한 아카이브 파일명을 반환했고 파일 안에는 최초 7일만 남았다. 다른 제목으로 14일을 전달한 대조군에는 14일이 저장됐다. 이 함수는 일반 단건·배치 입력 코드에서 호출된다. 전체 검색 결과나 위키 엔진의 재작성 여부는 이 실험으로 판정하지 않았다. [원본 함수](https://github.com/WeAgentAI/LLM-Wiki/blob/79a5a2d5fb9e07c7e5d21fe704b4eca0c27452ef/llm_wiki_bench/bench_ingest.py#L5514-L5549) [관측값](../evidence/wiki-archive.json)

## 서로 다른 주장과 변경 이력

**Wikidata** 설계자는 값이 다른 주장을 함께 보존하고 각 주장에 적용 시점·방법 같은 한정자와 출처를 단다고 설명했다. 편집 과정에서 선호·일반·비권장 순위를 정한다. 이 자료는 초기 운영 경험을 다룬 설계 논문이다. 2014년 당시의 통계와 계획은 현재 기능을 판단하는 근거로 쓰지 않았다. 논문의 설계 원칙, 역사, 속성·값, 한정자, 출처·순위, 접근 방법과 조직 운영의 한계까지 검토했다. [CACM 원문, pp. 78–85](https://iccl.inf.tu-dresden.de/w/images/8/89/Wikidata-CACM-2014.pdf)

Wikibase의 `Statement`가 핵심 값과 한정자·출처·순위를 들고 있고, `StatementList.getBestStatements`는 선호값이 있으면 이를 반환하고 없으면 일반값을 반환한다. `AffectedPagesFinder`는 변경된 속성, 언어 표기, 한정자·출처 등 무엇이 달라졌는지 구분한다. 사용 추적의 대상은 클라이언트 쪽 페이지 렌더링이다. 사람이 채택한 문장의 근거 버전이 바뀌어 결정을 재검토시키는 과업과는 다른 동작이다. 저장소와 데이터 모델 패키지에서 GPL 라이선스 파일을 확인했고, 이번 작업에서는 구현 아이디어를 읽었다. [Statement](https://github.com/wikimedia/mediawiki-extensions-Wikibase/blob/a39399e67a12c735ea4e97dc03d112a766e1f9b4/lib/packages/wikibase/data-model/src/Statement/Statement.php#L63-L187) [순위별 반환](https://github.com/wikimedia/mediawiki-extensions-Wikibase/blob/a39399e67a12c735ea4e97dc03d112a766e1f9b4/lib/packages/wikibase/data-model/src/Statement/StatementList.php#L183-L213) [영향 범위](https://github.com/wikimedia/mediawiki-extensions-Wikibase/blob/a39399e67a12c735ea4e97dc03d112a766e1f9b4/client/includes/Changes/AffectedPagesFinder.php#L55-L176) [사용 추적 문서](https://github.com/wikimedia/mediawiki-extensions-Wikibase/blob/a39399e67a12c735ea4e97dc03d112a766e1f9b4/docs/topics/usagetracking.md#L9-L67)

**변경된 근거만 다시 계산하는 방법.** Motik 등의 IJCAI 2015 논문은 RDF 명시 사실을 삭제할 때 이 사실에서 파생된 결론에 다른 증명이 남아 있는지 역방향으로 확인한다. 방법과 등치 처리, 정리 1, 알고리즘 1–7, RDFox 평가와 결론을 읽었다. 특정 대규모 형식 데이터에서 작은 변경에는 증분 처리가 빨랐지만, 관계가 조밀한 일부 자료에서는 전체 재계산이 더 빨랐다. 자연어 지침에서 ‘다른 문서가 같은 결론을 지지하는가’는 형식 추론만으로 보장하기 어렵다. 우리 실험에는 동일한 결과를 전체 재검사로도 산출해 부분 재검사가 놓친 항목을 찾는 비교 방식이 적절하다. [IJCAI 논문, pp. 1–7](https://www.cs.ox.ac.uk/people/ian.horrocks/Publications/download/2015/MNPH15c.pdf)

**출처 표준.** W3C PROV-O의 Entity, Activity, Agent와 wasRevisionOf, wasQuotedFrom, wasAssociatedWith를 사용하면 문서 개정본, 원문을 인용한 설명, 채택 활동과 담당자를 연결할 수 있다. 채택 사유와 적용 기한은 제품의 업무 규칙으로 정의해야 한다. 이 표준은 필요한 속성과 예제를 열람했다. [W3C PROV-O](https://www.w3.org/TR/2013/REC-prov-o-20130430/)

## A안에 적용할 수 있는 기준

- **초안과 결정.** 읽을 수 있는 초안, 글의 원문 일치, 조직의 채택을 각각 평가한다. 한 문서에 인용이 있다는 사실로 팀의 채택 여부를 대신할 수 없다.
- **원문 주소.** 같은 문서의 연속 버전마다 바이트 해시와 인용 위치를 기록한다. 결정에 포함된 두 원문 모두 버전에 고정한다. 새로 발견한 등가 근거는 별도 후보로 남긴다.
- **선별.** 서로 다른 값은 충돌 후보가 될 수 있다. 적용 부서·시점·조건이 다르면 함께 유효할 수 있다. ‘신규 7일, 갱신 14일’은 오탐을 확인하는 대조군이다.
- **논문형 평가.** 원문 미변경 재동기화, 값 수정, 근거 하나 삭제, 근거 전부 삭제, 문구만 변경, 결정 이후 제3의 충돌 문서 추가를 포함한다. 수정 이전에 확정한 근거를 다시 열 수 있는지, 현재 페이지에 오래된 채택이 그대로 보이는지, 사람이 읽어야 할 쌍을 얼마나 줄이는지를 따로 잰다. 규칙 방식, LLM 단독, 검색과 인용, 검토 절차가 있는 방식을 같은 자료로 비교한다. 사람 기준 답과 알고리즘 규칙은 따로 작성한다.
- **범위.** 검토 절차, 지식그래프, 출처 기록은 모두 선행 사례가 있다. 무엇을 더 잘하는지는 실제 수정·삭제·충돌 시험과 사용자 평가로 입증해야 한다.

## 열람 기록

| 자료 | 범위 | PDF SHA-256 |
|---|---|---|
| LLM-Wiki, arXiv v2, 15쪽 | 본문 1–7, 한계, 부록 A–H. QA 수치·예산·케이스·샘플 스키마 대조 | 5752b92a793be1f80aa463dcc3fb123b6524df28c223c53bbf1043cc0855806b |
| STORM, NAACL 2024, 27쪽 | 본문 1–8, 한계·윤리, 부록 A–E, 루브릭·긴 예시 글. 참고문헌에 인용된 별도 연구는 이 표에서 제외 | 5815b45d03d79f47844aeb90fe5bdbbf5e8d574bf6f457eb84aab23a5c335262 |
| Wikidata, CACM 2014, 8쪽 | 전체 본문의 설계·출처·순위·활용·운영 전망. 설명 사례 보고, 성능 벤치마크 없음 | c513319fcb731d42da5d4daf67745bfdaa359733cd402aae7bac19a706f95836 |
| Motik 등, IJCAI 2015, 7쪽 | 본문 1–5, 알고리즘·정리·실험표·반례. 정리 증명 전문은 저자가 별도 기술 보고서로 안내 | 474b83fc8cc8b34114b6bf61d0845f8cb3fa598523837330fcec39abf2b4e305 |

고정 커밋에서 읽은 코드 범위는 LLM-Wiki의 `bench_ingest.py`, `llm_client.py`, `bench_error_book.py`, `wiki_agent.py`, `wiki_retriever.py`와 설정·라이선스, STORM의 `engine.py` 및 `knowledge_curation.py`, `outline_generation.py`, `article_generation.py`, 라이선스, Wikibase의 `Statement.php`, `StatementList.php`, `AffectedPagesFinder.php`, `UsageUpdater.php`, `docs/topics/usagetracking.md`와 라이선스의 해당 경로다. 세 제품 전체를 기능 시험한 결과로 확대하지 않는다.
