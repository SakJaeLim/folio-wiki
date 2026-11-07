# Folio Wiki

[한국어](README.md)

Folio Wiki turns a public Markdown folder into a WeKnora draft and lets a reviewer decide what the team should follow when sources disagree. Each decision keeps the reviewer’s name, rationale and the exact passages from both source versions.

In the included workshop example, one guide asks participants to apply seven days in advance and another requires fourteen. Choose the second guide and record a reason. When its deadline changes to ten days, the old decision leaves the current handbook and returns to the review queue. The fourteen-day text remains available from the decision history.

![Reviewing the two source passages](docs/images/decision.png)

Start a WeKnora v0.9.0 API with chat and embedding models. The repository includes a Linux/WSL build script for WeKnora Lite using SQLite and Ollama. Then run the review app with Python 3.10 or later.

```bash
python run.py --folder examples/public-handbook --weknora-url http://127.0.0.1:8794
```

[Open the local review desk](http://127.0.0.1:8848/). Change a file in the chosen folder to trigger a new review. To reproduce the example, use a disposable copy of the folder and replace the notice with the file under `examples/revision`.

The initial implementation compares sections with matching heading paths across files. PageIndex 0.2.10 optionally adds navigation within an archived Markdown version. With `--enable-jev`, a reviewer can submit two public passages to TypeSafe Jev for an advisory classification. Microsoft Decision-1 and Kakao Kanana are research comparators. The UI and sample documents are in Korean.

[Architecture](docs/ARCHITECTURE.md) · [Research and code comparisons](docs/research/README.md) · [Validation](docs/VALIDATION.md)
