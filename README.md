# Interview Tutor

A small Python hobby app for interview practice. Enter a public page URL, topic, or pasted material, answer questions, and download revision notes with feedback and marks. It supports coding problems and conceptual topics such as supervised or unsupervised learning. Generated code is educational text and is never executed.

Built with **Streamlit, OpenAI, Pydantic, and ReportLab**, with optional **Brave Search** for fresh context. Sessions stay in memory; no database is needed.

## Run on Windows

Use Python 3.12 from this project folder. Create a virtual environment and install the application dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create your local key file from the [empty template](api_key.example.txt) if you do not already have one:

```powershell
if (-not (Test-Path -LiteralPath api_key.txt)) {
    Copy-Item -LiteralPath api_key.example.txt -Destination api_key.txt
}
```

Fill in `OPENAI_API_KEY` locally. Fill in `BRAVE_API_KEY` to enable fresh-context research, or set `max_search_calls=0` in `tutor/config.py`. Runtime environment variables also work. The app does not load `.env` files automatically. Keep real keys out of screenshots and Git; `api_key.txt` is ignored.

Run the application:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open `http://127.0.0.1:8501`. Enter a full HTTP/S URL, a topic, or both; choose a practice level and optional company/tier, then start. Answer one question at a time. The planned total and remaining questions are hidden. Click **Finish & prepare PDF** whenever you want marks and notes; the harness can also complete automatically. Its internal stopping limit remains enforced.

Clicking **Start interview** uses the inexpensive configured OpenAI model for topic-specific questions and reviews. The app validates your input before loading the OpenAI key or constructing the model client. There is no model/provider selector, demo interview, search toggle, or separate spending checkbox. Company context is a preference, not a claim about actual hiring standards.

If a URL requires login, blocks fetching, or relies on JavaScript, use **Paste source text instead**. Pasted material replaces page fetching. The reader loads one public HTML/text page with checked redirects, public IP pinning and verified HTTPS; it does not browse links. Downloads are capped at 1 MB; retained page text is capped at 4,000 characters and longer sources are labeled excerpts. The 8-second network timeout is not a strict overall deadline: DNS and slow headers can take longer.

## Fresh context with Brave Search

For an unfamiliar, emerging, or time-sensitive topic, the model can return a focused research query instead of a question plan. The harness automatically checks the configured search and spending limits, executes one bounded Brave search, and passes the snippets back for planning. Stable familiar topics need no search. Set `max_search_calls=0` in `tutor/config.py` to disable research. Result links appear in the app and PDF. Linked pages are not automatically opened; snippets are untrusted reference material, not verified facts or evidence for learner marks. Missing keys, failed search, or insufficient context produce a clear limitation and pasted-material fallback.

The supported local `api_key.txt` format is:

```text
OPENAI_API_KEY=your-openai-key
BRAVE_API_KEY=your-brave-key
```

These are placeholders. Environment variables with the same names also work. Each client receives only its selected key at runtime. Neither key is placed in model/search context or reports. The key file and environment files are ignored by Git. Starting an interview sends source material and, at final review, answers to OpenAI; only a focused topic query goes to Brave when research is requested.

## Marks and PDF

| Criterion | Maximum |
| --- | --- |
| Preparation demonstrated | 3 |
| Concept knowledge | 3 |
| Scenario application | 2 |
| Reasoning and clarity | 2 |
| Total, computed in Python | 10 |

Each assessed criterion has a reason and an exact quote from one of your answers, plus two improvements overall. Missing evidence is **Not assessed**, not automatically zero; partial reviews have no overall score. Marks reflect this session's answers, not hiring readiness or executed-code results.

The PDF contains source material and research links, marks, key concepts, feedback, the transcript, and further-practice prompts. Coding problems can also include brute-force/improved reference solutions, dry runs and complexity; general topics do not require code. All code is labeled untested. App-generated labels show recorded answer counts and omit planned totals. The model is also instructed to omit planned totals; adherence in live prose remains unverified.

## Files and harness concepts

The [architecture and design presentation](docs/presentations/architecture-design.pdf) describes the implemented system, including its boundaries, data flow, contracts, state machine, scoring, budgets, and verification limits. Its [editable Beamer source](docs/presentations/architecture-design.tex) includes speaker notes. It is a code-based design review, not a proposal for additional infrastructure.

To rebuild the 24-slide presentation, install a LaTeX distribution with Beamer, TikZ, and Latin Modern, then run these two passes from the project root:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=docs/presentations docs/presentations/architecture-design.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=docs/presentations docs/presentations/architecture-design.tex
```

```text
app.py                 # Streamlit input, interview, marks, download
tutor/config.py        # Inexpensive model, prices, limits
tutor/sources.py       # Public page, topic or pasted material
tutor/search.py        # Bounded Brave snippets and source links
tutor/secrets.py       # Separate runtime provider keys
tutor/schemas.py       # Research request, question plan and notes
tutor/harness.py       # Plan -> optional search -> answers -> review
tutor/openai_model.py  # Structured OpenAI responses
tutor/pdf_export.py    # Same notes -> PDF
tests/                 # Deterministic models, pages, search and UI checks
docs/requirements.md   # Current small scope
docs/sample-notes.pdf  # One illustrative mock PDF
docs/presentations/    # Beamer source and architecture/design deck
docs/interview-guide.md # Detailed project interview preparation
docs/interview-guide.pdf # Printable interview guide
```

The [project interview guide](docs/interview-guide.pdf), with an [editable Markdown copy](docs/interview-guide.md), explains the architecture, code paths, technology choices and alternatives. It includes 50 interview questions with harder follow-ups, eight source excerpts, eight coding exercises, debugging scenarios, and an honest account of implemented features and limitations. The guide and presentation describe the harness snapshot before the GitHub workflow was added.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance and [GitHub upload instructions](docs/github-upload.md) for creating your first commit and connecting a remote. The repository includes a [GitHub Actions workflow](.github/workflows/tests.yml) for Windows/Python 3.12 tests on pushes and pull requests. It requires no provider API secrets. Hosted CI results are available only after upload and execution.

Pydantic validates responses, Streamlit avoids a separate frontend, and ReportLab renders PDFs locally. No new dependencies or agent framework are needed. The model can request a tool; the harness owns permission, budget, tool execution, bounded feedback, and stopping. Collecting answers makes no per-turn model calls; completing the interview or clicking Finish triggers the final review. Downloads reuse that review. The question set is fixed after planning. Accepted answers are never silently truncated; failed stages preserve a partial export without automatic retries. Sessions remain in memory only. PDF downloads are generated in memory; the app needs no output or temporary folder. The small `tests/` suite is for development and does not run with the app.

## Model and cost

The default stays `gpt-4.1-mini`: $0.40/million input tokens and $1.60/million output tokens, checked on 4 October 2026 against [official OpenAI documentation](https://developers.openai.com/api/docs/models/gpt-4.1-mini). The adapter uses [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs). No automatic upgrade occurs.

Brave Search is listed at $5/1,000 requests ($0.005 each), checked on the same date against [official pricing](https://api-dashboard.search.brave.com/documentation/pricing). The local estimate ignores monthly credits; account access/credit eligibility are unverified. See [authentication](https://api-dashboard.search.brave.com/documentation/guides/authentication) and the [Web Search reference](https://api-dashboard.search.brave.com/api-reference/web/search).

Normally a plan and final review use two model calls. Research adds a search and a replanning call. Example without research: 2,000 input/1,000 output tokens for planning ($0.0024), then 6,000 input/3,000 output for grading/notes ($0.0072): about **$0.0096**. With research: 2,000 input/150 output for the context request ($0.00104), Brave ($0.005), 4,000 input/1,000 output for the grounded plan ($0.0032), and 8,000 input/3,000 output for grading/notes ($0.008): about **$0.01724**. This includes PDF explanation generation; rendering is local. No retries are assumed.

Defaults: $0.05 total estimated budget including research; 12 model-call safety limit; one search attempt; three results; 4,000 search-context characters; 1,000 characters per answer; 40,000 bytes of prompt/schema allowance; 1,800 plan and 3,500 report output tokens. Failed attempts count and uncertain usage retains a conservative reservation. The harness reserves replanning and final-review allowance before search. Local estimates and price changes mean this is not an exact billing cap.

## Checks and limitations

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use synthetic keys, mocked providers/pages, and headless UI flows. They check key separation, restricted fetching, conditional research, budget enforcement, failures, hidden planned totals, learner-only evidence, and app/PDF score consistency. They never execute solution code. Live model/Brave account access, question quality, grading accuracy, search relevance and every website's compatibility remain unverified. Authentication, persistent history, autonomous link browsing, sandbox execution and repair remain deferred.

Model failures now show a safe category and next step: authentication, quota/credits, rate limit, connection/timeout, model permissions, invalid request/schema, refusal, incomplete output, or invalid response. The adapter checks response status and records reported usage before validating JSON, so truncated or malformed output can still have accurate token accounting. Raw error bodies, generated failure content, and credentials are not displayed. Failed output never produces marks, and failures do not trigger automatic retries. These categories follow the [official OpenAI error documentation](https://developers.openai.com/api/docs/guides/error-codes).

Use a categorized warning to check local configuration or provider access. `max_cost_usd` is the app's local estimated budget; OpenAI account credits and project limits are separate. When usage is unavailable, the displayed estimate retains a conservative reservation and is not proof of a charge.

If an old session is open after updating, click **New session** when prompted. The retained sample PDF is a historical mock example. Current verification and sample details are recorded below.

Verified locally on 5 October 2026: **68 tests passed** and `pip check` reported no broken requirements. The suite covers input/UI behavior, bounded research, budgets, scoring evidence, failure handling, and report consistency. A real SDK with a mock HTTP transport checks incomplete responses without sockets. The retained three-page [sample PDF](docs/sample-notes.pdf) and a four-page stress fixture were previously rendered and visually inspected; sample sources and marks are illustrative mocks. Live OpenAI/Brave access, response quality, and hosted CI remain unverified.
