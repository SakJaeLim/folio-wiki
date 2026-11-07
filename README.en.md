# Folio Wiki

[한국어](README.md)

**Folio Wiki reopens a team decision when its source changes.** A workshop handbook says seven days and the recruitment notice says fourteen. A reviewer adopts the notice and records why. When the notice changes to ten days, the decision returns to the review queue. The original fourteen-day passage is still available in the history.

**23-second demo**　Adopt **14 days** → edit the notice to **10 days** → see **review required** → reopen the original **14-day notice**. Captions are in English and Korean.

[![Actual review workflow from the 14-day decision to a changed 10-day notice](docs/media/deadline-review.gif)](docs/media/deadline-review.mp4)

[MP4 video](docs/media/deadline-review.mp4) · [Architecture](docs/ARCHITECTURE.md) · [Validation](docs/VALIDATION.md)

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

The pilot finds passages under matching Markdown heading paths in different files. A reviewer decides which passage applies. An unrelated edit elsewhere in a cited file can also reopen a decision. Organizational accounts, document-level permissions and cloud-drive sync are outside the current implementation.

## What this repository implements

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

With synthetic public fixtures, the app reopened an adopted rule and recovered its original passage. On the tested CPU, the initial WeKnora draft and index took about nine minutes. Some Lite source lookups logged SQLite warnings. [Observed results](docs/VALIDATION.md)

An open research question is how often team members act on an obsolete decision after its source changes. Compare document search, a conventional wiki and Folio on the same source history. Measure wrong-rule applications, unnecessary reviews and time to find the correct evidence. Organizational outcomes have yet to be measured. [Prior work and evaluation plan](docs/research/README.md)

```bash
python -m unittest discover -s tests -v
```
