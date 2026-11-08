# Folio Wiki

[한국어](README.md)

**Folio Wiki reopens a team decision when its source changes.** A workshop handbook says seven days and the recruitment notice says fourteen. A reviewer adopts the notice and records why. When the notice changes to ten days, the decision returns to the review queue. The original fourteen-day passage is still available in the history.

| Run the demo | Original Folio features |
|---|---|
| Python 3.10+ and `python run.py --demo` · [Setup](#try-it) | Versioned source passages, side-by-side comparison, recorded decisions, review after edits and historical evidence recovery · [Implementation](#what-this-repository-implements) |

**23-second demo**　Adopt **14 days** → edit the notice to **10 days** → see **review required** → reopen the original **14-day notice**. Captions are in English and Korean.

[![Actual review workflow from the 14-day decision to a changed 10-day notice](docs/media/deadline-review.gif)](docs/media/deadline-review.mp4)

[Download MP4](https://github.com/SakJaeLim/folio-wiki/raw/refs/heads/main/docs/media/deadline-review.mp4) · [Architecture](docs/ARCHITECTURE.md) · [Validation](docs/VALIDATION.md)

## Review an official notice from its URL

Can a Korean startup grant pay for an office desk? The notice lists purchases of equipment and supplies. Its FAQ distinguishes office furniture from materials used to build a prototype.

Start the app below, open **공고 가져오기** (Import notice) and paste the [Bizinfo notice URL](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000119859). Folio lists six official files and shows the equipment rule on PDF page 2 alongside the FAQ on page 15. Each page link opens the archived original. Click **이 연결 확인** after reviewing the passages. The team wiki records the confirmation. Import the URL again to check for changes.

This adapter supports Bizinfo detail pages. PDF extraction requires `pdftotext` on PATH. HWPX uses Python's standard library. The inventory identifies unsupported or reference-only files. Candidate discovery uses explicit restrictions and shared terms in labelled rules. [Replay and limitations](docs/research/notice-url.md) · [App screenshot](docs/media/notice-url-review.png)

## Try it

Install Git and Python 3.10 or later. The workshop demo uses the Python standard library.

```bash
git clone https://github.com/SakJaeLim/folio-wiki.git
cd folio-wiki
python run.py --demo
```

1. [Open the local review desk](http://127.0.0.1:8848/). Select the **14-day** notice, enter a reviewer name and reason, then click **결정 기록** to save the decision.
2. Keep the server running. In another terminal in the same repository, run `python run.py --revise-demo`. This replaces the demo copy of the notice with its 10-day revision.
3. The item shows **재검토 필요** (review required). In **결정 기록** (history), open **결정 당시 원문** to read the 14-day passage used at the time.

The UI and sample documents are in Korean. Local demo files and history persist under `.state/`. On Windows, use `py -3` if the `python` command is unavailable. On macOS or Linux, use `python3` if needed.

## Where it helps

| Situation | What reviewers can check |
|---|---|
| A training team maintains a workshop handbook and a recruitment notice | The deadline adopted for this cohort, who chose it and why |
| An incoming project lead inherits an old procedure and a revised announcement | Both passages the previous lead saw and the version that changed |
| A team republishes guidance after a source edit | Which decision needs another review and the evidence behind the previous one |

When passages disagree under matching headings, choose the source and the sentence your team will use. You can also adopt the entire section. Existing decisions keep their original section scope. Changes to the selected wording or a referenced Markdown link destination reopen the decision. For a selected sentence, Folio also checks the following policy text for explicit changes to voting, application or submission permissions and for waivers of the selected requirement. The review shows the exact clause and its archived source version. The reviewer decides what applies. Missing or ambiguous passages also require review. [Public election-guide replay, controls and detection boundaries (Korean)](docs/research/exception-review.md)

## What this repository implements

Register an official notice and its companion files in `folio-sources.json` to track separate attachments and FAQs. Folio checks the publication URL, program, year, approved attachment URL and Markdown digest. A Korean startup notice replay links the equipment rule to FAQ page 15 while ignoring the same restriction in the prior year's FAQ and a different program. [Registration example and replay (Korean)](docs/research/notice-files.md)

Decisions can also track an explicit exemption in another section of the same file. Select the program section and enter the audience as named in the notice to narrow the review. A Korean ministry notice expanded one export program's exemption while retaining the existing exemption for another recipient. [Official editions, six replay results and instructions (Korean)](docs/research/cross-section-review.md)

| Component | Responsibility |
|---|---|
| **Original Folio Wiki code** | Watch a folder, preserve file hashes and line ranges, compare passages, record adoption/hold/withdrawal, reopen affected decisions and restore their historical sources |
| [WeKnora](https://github.com/Tencent/WeKnora/tree/v0.9.0) | Generate wiki drafts from folder versions through its API |
| [PageIndex](https://github.com/VectifyAI/PageIndex/tree/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4) | Optional navigation to headings and lines in an archived Markdown version |
| [jev-cli](https://github.com/tumf/jev-cli) | Optional advisory classification of two public passages, sent to TypeSafe when the reviewer clicks the button |

## Generate drafts from your folder

For generated wiki pages, use WeKnora v0.9.0 and Ollama. On a glibc-based Linux system or Windows WSL, install Git, Go, a C/C++ compiler and SQLite development headers. Start Ollama, then run these commands. Allow disk space and time for the first model download and engine build.

```bash
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
bash scripts/weknora-lite.sh
```

In another terminal, replace the path below with a folder of **public UTF-8 Markdown documents**.

```bash
python run.py --folder "/path/to/public-markdown" --weknora-url http://127.0.0.1:8794
```

[Open the team wiki](http://127.0.0.1:8848/). Folio checks the folder every four seconds. Each folder version gets its own WeKnora knowledge base and draft. The engine must allow registration of the local test account. Set `OLLAMA_BASE_URL` for another Ollama address and `FOLIO_CHAT_MODEL_ID` / `FOLIO_EMBED_MODEL_ID` for models already registered on an existing engine. For a source outline, use a Python environment with PageIndex 0.2.10. To enable Jev, authenticate the CLI and start the app with `--enable-jev`.

## Validation and research

Replaying four public guide revisions reduced reopened decisions from 17 to 3. On two Korean agencies’ corrections, both ordinary document comparison and Folio found all three affected decisions. [Pilot results and official notices (Korean)](docs/research/revision-pilot.md)

With synthetic public fixtures, the app reopened an adopted rule and recovered its original passage. On the tested CPU, the initial WeKnora draft and index took about nine minutes. Some Lite source lookups logged SQLite warnings. [Observed results](docs/VALIDATION.md)

An open research question is how often team members act on an obsolete decision after its source changes. Compare document search, a conventional wiki and Folio on the same source history. Measure wrong-rule applications, unnecessary reviews and time to find the correct evidence. Organizational outcomes have yet to be measured. [Prior work and evaluation plan](docs/research/README.md)

```bash
python -m unittest discover -s tests -v
```
