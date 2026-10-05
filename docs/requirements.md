# Interview Tutor - Hobby Project Requirements

Status: Small implementation authorized by the user's direct coding requests. Updated on 4 October 2026 for a simple Start action, OpenAI-only startup, hidden interview length, and automatic bounded Brave context research.

## 1. Idea and scope

A local single-user app that turns a selected page or study topic into a short interview and a revision PDF. Keep the Python file structure and avoid a large architecture.

The latest requested scope extends the coding tutor to general study subjects: public Wikipedia/coding pages and topics such as supervised or unsupervised machine learning. Python coding solutions remain supported where relevant; theory topics do not require code. The user explicitly requested these changes. Questions are generated as one fixed plan to keep calls inexpensive.

Automatic code execution and repair remain deferred. All code is untested. No deployment, publication, or pushing without an explicit request.

## 2. Workflow

1. Enter a complete public page URL, a topic, or both. Pasted text can replace an unreadable page.
2. Choose beginner/intermediate/advanced and optional company/tier, then click Start. Validate input before loading the OpenAI key or constructing its model client. OpenAI is the direct model path; there is no provider selector, runtime demo model, research toggle, or separate spending checkbox. Research runs automatically only when the model requests it and configuration permits it.
3. See one question at a time and submit one answer per question. Cover prerequisites, concept knowledge, practical scenarios, and justified reasoning.
4. Finish when you want marks and a PDF; completion can also be automatic. Planned and remaining totals are not announced. Finishing before completion produces partial coverage.
5. Start a new interview when ready. There is no predefined problem picker or persistent history.

Company/tier is a preparation preference. Scores describe demonstrated answers in this session, not real company hiring standards or overall job readiness.

## 3. Requirements

Existing identifiers retain their related subjects. The new source and bounded-interview features have new IDs. Earlier coding-only scope and saved-code grading are replaced by the user's requested general interview.

| ID | Requirement |
| --- | --- |
| SCOPE-001 | One user and one topic/page per interview, running locally. |
| SCOPE-002 | Support general learning topics and coding problems; Python remains the language for reference code. |
| SCOPE-004 | No predefined problem bank. |
| SCOPE-005 | One simple screen for URL/topic/paste, practice level, optional company, answers, marks, and PDF. Keep model prices/provider details in README; omit introductory/model-price captions and provider/research/approval controls from the main input page. No question-count picker or completion percentage. |
| SCOPE-008 | Straightforward Python implementation with an explicit program-controlled interview loop. |
| FR-001 | Understand source material/topic and explain its key assumptions and concepts. |
| FR-002 | Identify missing correctness-critical assumptions. Include relevant clarification tasks within the question limit rather than adding unlimited turns. |
| FR-005 | Generate relevant questions suited to the selected level across the four assessment categories. Questions are fixed for the interview rather than generated after every answer. |
| FR-007 | Retired as an open-ended hint/solution chat requirement; revision explanations and reference solutions are provided at Finish. |
| FR-008 | Allow early finish at any time, preserve answers, and prevent further turns afterward. |
| FR-011 | For coding problems explain brute force and a useful improvement, or why a single approach is already optimal. Do not force algorithms into noncoding subjects. |
| FR-013 | Explain relevant time/space complexity and the assumptions behind correctness/optimality claims for coding approaches. |
| FR-025 | Explanations/dry runs must match the included reference code. They do not count as verified execution. |
| FR-026 | Produce the compact educational PDF below. |
| FR-030 | Label code untested and missing/unfinished material clearly. Never invent test results. |
| FR-033 | Store source, question plan, answers, status, and cost in memory for the current interview. |
| FR-037 | Assess recorded learner answers out of 10: preparation demonstrated 3, concept knowledge 3, scenario application 2, reasoning/clarity 2. Include reasons, exact quotes from learner answers, and two improvements. Compute totals in Python; unknown criteria are unassessed and prevent an overall score. Do not credit source/question/reference text as answer evidence. |
| FR-038 | Keep the previously agreed interview bounds internally. Ask one question at a time without planned totals or remaining-count displays in app-generated UI/chat/PDF labels; instruct model-generated prose to omit planned totals too. Reject malformed/duplicate plans, stop at completion, and finalize once. Collect answers without per-turn model calls; completion or Finish triggers the final review. |
| FR-039 | Read only the user-selected public HTTP/S HTML/text page, with verified TLS, checked/pinned public addresses, redirects, response-size/time limits, and no credentials or host/private service access. No link browsing. Support topic-only and explicit pasted fallback; never invent successfully retrieved page text. Clearly mark truncated excerpts. |
| FR-040 | For unfamiliar, emerging or time-sensitive topics with insufficient supplied material, the model may request a focused Brave query. If permitted by configuration and affordable, automatically execute one bounded search and replan using its snippets. Set `max_search_calls=0` to disable research; there is no UI toggle. Do not search stable topics unnecessarily. Retain source links; search text is untrusted reference material, never learner grading evidence. If search fails or context is insufficient, state the limitation and request pasted material. |

### PDF contents

- Source URL/title or topic, retained source material, and recorded answers without a planned total.
- Additional context-source links when used, labeled as unverified search snippets rather than opened pages.
- Scorecard, reasons/evidence, and two improvements when available.
- Topic summary, assumptions, key concepts, feedback, and common mistakes.
- Coding-only reference solutions, intuition, dry runs, correctness/complexity, and comparison when appropriate.
- Three further-practice prompts with explanation sketches, explicitly outside the interactive interview.
- Recorded question/answer transcript and a concise revision checklist.
- Untested-code and AI-feedback limitations; partial interview/unavailable sections identified.

Use readable headings, code, tables, and page numbers. Render the sample and check clipping/overflow.

## 4. Safeguards and budgets

| ID | Requirement |
| --- | --- |
| SEC-006 | Load named OPENAI_API_KEY and BRAVE_API_KEY entries from `api_key.txt` only at runtime when starting an interview. Validate input before OpenAI key/model construction. Keep provider keys separate; never put either in interview data, logs, source code, search context, or PDF. Support environment variables too. |
| SEC-007 | Ignore the key before committing; report tracked status without disclosing it. No secrets in examples. |
| BUD-002 | Keep the existing configurable inexpensive OpenAI model. Verify pricing against official documentation before changing it. |
| BUD-003 | Clicking Start runs the configured inexpensive OpenAI model within existing session budgets. The user's explicit request replaces the former UI spending opt-in; no separate approval checkbox, provider selector, or runtime demo model is required. Document providers/prices in README. No automatic more-expensive model upgrades. |
| BUD-005 | Bound page download, source/input/context size, question count, answers, output size, calls, retries, and estimated cost. Include grading/explanation generation in the run budget. |
| BUD-006 | Display model-call count, known token usage, and estimated cost. A local estimate is not an exact billing cap. |
| FR-041 | Show sanitized model failure categories with useful next steps: authentication, quota/rate limit, connection/timeout, model access, invalid request/schema, refusal, incomplete output, or invalid response. Never show raw provider bodies or errors. Retain reported token usage even when returned content cannot be validated. |
| NFR-004 | Use deterministic mocked models/pages for routine checks; clearly separate mocks from live verification. |

The normal flow uses one plan call and one final review call. Research adds one Brave request and one replanning call. Existing $0.05 total estimated spending and 12-model-call safety limits remain; the conservative $0.005/search estimate is included. Search is capped at three results and 4,000 retained context characters, with a 1 MB response cap and 8-second network timeout. Reserve replanning/final-note allowance before search; count failed attempts and do not retry automatically. Account credits and precise billing are not assumed.

The input allowance is 40,000 bytes for source/research/schema/answers, extracted page text is capped at 4,000 characters, answers at 1,000 characters, plan output at 1,800 tokens, and final notes at 3,500 tokens. Preserve accepted answers if context or budget prevents grading; export a partial report without another call. Never silently truncate an answer.

## 5. Acceptance checks

- **AC-001:** Start is enabled without an approval checkbox. A topic, public URL, or pasted material starts an interview with selected settings. Blank input fails before OpenAI key loading or model initialization; there is no predefined-question dropdown, provider/search toggle, or introductory/model-price caption block. Configuration can disable research.
- **AC-003:** Mock interviews demonstrate coverage of all four categories and selected levels. OpenAI relevance/quality is verified separately.
- **AC-004:** Early finish closes the interview and labels partial coverage. No answers means no grade or final paid call.
- **AC-013:** Sample PDF has readable source/score/notes/transcript, three later-practice prompts, matching code/explanations where present, and no clipped content.
- **AC-011:** API, malformed-plan/report, context, and budget failures preserve available material and do not trigger automatic retries.
- **AC-017:** Complete mocked UI and harness flows work without credentials or paid calls; live limitations are explicit.
- **AC-019:** Score bounds, computed totals, matching app/PDF marks, null/unassessed criteria, and learner-only evidence are checked with mocks.
- **AC-020:** Previously agreed internal question bounds remain enforced; extra answers after completion are rejected; finalization/downloads are idempotent. App-generated UI/chat/PDF labels expose no planned totals or remaining-count progress display. Model prompts forbid announcing planned totals; live adherence remains unverified.
- **AC-021:** Mocked source tests verify public-only connections/redirects, TLS/IP pinning, bounded retrieval, extraction, and topic/paste fallbacks without network requests.
- **AC-022:** Mock tool requests verify conditional search, bounded attempts, context/provenance in replanning/reporting, combined cost checks, sanitized failures, no repeated-search loop, and provider-key separation using synthetic credentials only.
- **AC-023:** Mock provider and response failures produce safe actionable notices, preserve reported usage, never create marks from failed output, and never trigger automatic retries.

## 6. Assumptions and exclusions

English, local use, no persistence. Not every URL is readable: login/bot protection/JavaScript/PDFs may require pasted text. Excerpts may omit relevant details; users should review the retained source. The network timeout is not a strict whole-fetch deadline: OS DNS and slow headers can exceed it. The model decides when fresh context is needed; that judgment and search snippets are not independent fact verification. Research occurs before planning; adaptive follow-up chat and research during answers remain deferred.

Authentication, billing, autonomous link browsing, databases, multi-agent application frameworks, sandbox execution, automatic repair, and deployment are excluded. The explicitly requested bounded Brave context tool is allowed. If execution is added later, use a real isolated environment with fixed external tests and resource limits; never run generated code directly on the host.

The remaining architecture/design/test/implementation planning documents stay deferred under the user's simplified hobby-project coding request. Keep source, README, requirements, automated tests, sample PDF, and honest verification notes consistent with the current implementation.
