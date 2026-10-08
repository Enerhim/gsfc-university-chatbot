# ORBIT — GSFC University assistant

A local, conversational university assistant with React, React Three Fiber, Three.js, FastAPI, SQLite FTS5, vector embeddings, and Ollama Qwen3 8B.

## Start

Run `./start.sh` from this directory, then open http://127.0.0.1:8001. Ollama must be running. The configured models are `qwen3:8b` and `nomic-embed-text`. `ORBIT_PORT` can override the default port.

The Qwen3 model was downloaded from Ollama's official registry. Its model-file SHA256 is `a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`. It uses the official Qwen3 tool-calling template, not the pre-existing custom-persona model on this machine.

For a fresh installation:

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
ollama pull qwen3:8b
ollama pull nomic-embed-text
cd frontend
npm ci
npm run build
cd ..
./start.sh
```

## Conversation behavior

The frontend sends the last five exchanges to the backend. Follow-up questions are rewritten into standalone search queries using that context. Context helps resolve references; previous assistant replies are never accepted as evidence. A new topic replaces the previous search topic. Session history survives refresh in the same browser session; New conversation clears the current chat. The source scope is always the user’s mail plus public university sources.

Every answer runs retrieval. Hybrid retrieval combines SQLite FTS5 keyword search and cosine similarity over local Nomic embeddings with reciprocal-rank fusion. Directory pages are prioritized for contact questions, and schedules for event-date questions. Qwen can also call the read-only `search_university` tool. It cannot execute SQL, arbitrary URLs, shell commands, or send email.

Qwen produces concise, synthesized claims with source IDs. The server rejects nonexistent citations and runs a separate support-and-relevance audit against the cited passages. A rejected answer gets at most one repair and recheck; otherwise the system abstains. This reduces hallucinations but does not mathematically guarantee correct answers. Model verification can still make mistakes, and archived documents can be outdated.

The initial quote-only response mode was replaced with conversational synthesis following user feedback. The requested 110-question benchmark was canceled. Focused live conversation checks are in `evaluation/conversation-check.json`, and grounding/privacy regression tests are in `tests/`.

## Privacy and operating scope

This is a **single-user local app**, bound to loopback. It is not a multi-user deployment. Do not expose it to a network without adding authentication, user-specific access controls, and deployment hardening.

All app queries include public sources and this user's university mailbox; there is no scope switch. The model selector lists installed Ollama completion models, excludes embedding-only models, and retains the selection locally. Every selected model still uses server retrieval and claim verification; models without native tool support use the same server-managed evidence pipeline. The database, raw MIME exports, extracted attachments, OCR assets, and logs are under the private `data/` directory, excluded from Git. The backend checks Host and write-request Origin headers. Model inference and embeddings run locally. Browser fonts currently load from Google Fonts; no chat data is sent there.

## Sources and refresh

The crawler follows explicitly allowed public domains in `config.json`, respects robots rules, records discovered links and failures, and extracts HTML, PDF, and DOCX. Dynamic shells, unsupported files, oversized files, failed requests, and scans are reported as gaps rather than invented content. Source documents and emails are always data, never agent instructions.

```sh
.venv/bin/python -m backend.crawl
.venv/bin/python -m backend.mail
.venv/bin/python -m backend.ocr
.venv/bin/python -m backend.embed
```

`crawl` resumes from saved discovery state. `crawl --refresh` refetches indexed public sources. The UI's Refresh web action refreshes public pages and saved mail exports, then recomputes missing embeddings. It does **not** access the Codex Gmail connector itself. New emails require a connector export in a Codex task or a local MBOX import:

```sh
.venv/bin/python -m backend.mail --mbox /absolute/path/university-mail.mbox
```

The local MBOX import currently indexes text bodies. Attachment ingestion is handled by the connector-export pipeline. Browser-dependent public pages can be imported from a rendered public scrape. External links are recorded with provenance; a linked domain is not automatically treated as university-owned. alphaXiv returned ambiguous or incorrect person matches in the initial checks, so those results were excluded. Official faculty biographies remain the research-profile authority.

The Coverage screen and `data/sync-manifest.json` describe the actual import state. Full mailbox and attachment coverage must not be inferred from the document counter. Spam/Trash and inaccessible Google Drive/Classroom documents are not automatically included. Every answer checks the **indexed** evidence; it does not re-download the entire university website or mailbox on every message.

## Checks

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m backend.smoke
cd frontend && npm run build
```

Smoke checks call local Ollama. They cover startup contact, contact follow-up, topic change, faculty research follow-up, Ananta's full date range, and an unsupported future event price. The backend returns checked-at timestamps and the retrieval/verification trace. Important decisions should still be checked against the original cited source.
