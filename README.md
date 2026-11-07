# Folio Wiki

[English](README.en.md)

공개 폴더에 있는 두 지침이 서로 다를 때, 팀이 어느 내용을 채택했는지 근거와 함께 남기는 로컬 위키입니다. WeKnora가 폴더의 자료를 읽어 초안을 쓰고, 담당자는 원문을 대조해 팀에 적용할 안내를 결정합니다.

![두 원문과 담당자가 채택한 14일 기준](docs/images/decision.png)

예제의 워크숍 안내에는 **7일 전**, 모집 공지에는 **14일 전**까지 신청하라고 적혀 있습니다. 담당자가 모집 공지를 선택하면 당시 두 문서와 채택 이유를 저장합니다. 나중에 공지가 **10일 전**으로 바뀌면 예전 결정을 다시 검토하게 됩니다. 기록에서는 채택 당시의 14일 원문을 계속 열 수 있습니다. 모두 이 프로젝트를 위해 쓴 공개 합성 자료입니다.

이 저장소에서 구현한 부분은 폴더 변경 감지, 원문 버전 보관, 지침 비교, 담당자의 채택·보류·철회, 과거 결정 복원입니다. WeKnora는 API로 연결해 초안을 작성합니다. [원문 변경 뒤 화면](docs/images/review-again.png)과 [실제로 생성한 한국어 초안](docs/images/wiki-draft.png)을 볼 수 있습니다.

## 실행

Python 3.10 이상과 WeKnora v0.9.0 API를 사용합니다. 앱의 기본 기능은 Python 표준 라이브러리로 동작합니다.

```bash
python run.py --folder examples/public-handbook --weknora-url http://127.0.0.1:8794
```

[검토 화면 열기](http://127.0.0.1:8848/). **팀 위키**에서 엔진의 초안을 보고, **지침 검토**에서 원문 하나를 골라 이름과 이유를 입력하세요. 지정한 폴더를 4초마다 읽습니다. 다른 자료를 시험하려면 공개 Markdown 폴더 경로를 `--folder`에 넣으세요.

**엔진 준비.** Ollama에 대화 모델과 임베딩 모델을 준비합니다. 이 예제의 기본 모델은 `qwen2.5:3b`와 `nomic-embed-text`입니다. Linux 또는 Windows의 WSL에서 Git, Go, C/C++ 컴파일러, SQLite 개발 헤더가 있는 환경으로 아래 스크립트를 실행하세요. 스크립트는 WeKnora v0.9.0 소스를 고정 커밋에서 빌드하고, SQLite 기반 Lite 서버를 로컬 8794번 포트에 실행합니다. 엔진과 캐시를 저장할 여유 공간이 있는 드라이브를 사용하세요. 이미 실행 중인 WeKnora에 연결할 때는 서버 측에 모델을 등록하고 `FOLIO_CHAT_MODEL_ID`, `FOLIO_EMBED_MODEL_ID`로 등록 ID를 지정할 수 있습니다.

```bash
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
bash scripts/weknora-lite.sh
```

`OLLAMA_BASE_URL`로 엔진에서 접근할 수 있는 Ollama 주소를 지정합니다. 앱은 최초 실행 시 전용 로컬 계정을 만들므로 이 경로는 등록이 허용된 시험용 엔진에 적합합니다. 앱은 폴더마다 별도 저장 공간을 만듭니다. `--state`로 저장 위치를 지정할 수 있습니다. 원문, 결정과 엔진 계정은 이곳에 보관됩니다.

**원문 변경을 재현하려면** 예제 폴더를 다른 위치로 복사해 앱에 연결하고 14일 기준을 채택한 뒤, 복사본의 `02-모집공지.md`를 `examples/revision/02-모집공지.md`로 교체하세요. 지침 화면에 재검토 상태가 표시되고 팀 위키의 현재 안내에서 이전 기준이 내려갑니다.

## 선택 기능

- **PageIndex**를 설치한 Python으로 앱을 시작하면 원문 보기에서 제목별 목차와 해당 줄을 열 수 있습니다. 시험 버전은 0.2.10입니다. 짧은 Markdown의 목차 생성에는 모델을 호출하지 않습니다. [원본과 고정 커밋](https://github.com/VectifyAI/PageIndex/tree/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4)
- **TypeSafe Jev**는 담당자가 버튼을 누를 때 공개 인용문 두 개를 공식 API로 보냅니다. `jev-cli`를 설치해 인증한 뒤 `python run.py --enable-jev`로 켤 수 있습니다. 반환한 확률은 화면에 의견으로 표시하고 채택은 담당자가 기록합니다. [jev-cli](https://github.com/tumf/jev-cli)
- **Microsoft Decision-1과 Kakao Kanana**의 제공 방식, 구현과 평가 조건은 연구 문서에 정리했습니다. 이 앱에서 실제 호출하는 의사결정 모델은 Jev입니다. [의사결정 모델 비교](docs/research/decision-models.md)

## 현재 범위

서로 다른 파일에서 **제목 경로가 같은 Markdown 절**의 문구가 다를 때 검토 후보를 띄웁니다. 같은 뜻의 다른 제목이나 적용 대상이 다른 규정은 사람이 확인해야 합니다. 엔진 초안의 문장과 담당자가 채택한 안내를 화면에 각각 표시합니다. 문서를 수정하면 해당 파일을 인용한 결정은 다시 열립니다.

담당자 이름은 로컬 기록용 입력값입니다. 실제 조직의 계정 인증, 외부 드라이브 동기화, 문서별 접근 권한은 후속 개발 대상입니다.

[구성도와 데이터 흐름](docs/ARCHITECTURE.md) · [논문과 오픈소스 조사](docs/research/README.md) · [실행 검증](docs/VALIDATION.md)

```bash
python -m unittest discover -s tests -v
```
