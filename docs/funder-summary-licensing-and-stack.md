# Licensing and stack decisions across the SFU AI assistant projects

Summary for PSFS, who part-funded the work. Prepared 2026-10-30 from a
read-only scan of the project repositories listed in the appendix. It is a
working summary, not legal advice: every third-party licence named here
should be confirmed against the upstream project before it is relied on.

## 1. Headline findings

- **Only two of ten repositories carry a licence file.** Knowledge Engine
  (MIT, copyright Humanaxiom 2026) and the Summit MCP server (MIT, but its
  README says "© SFU" while the LICENSE file names an individual). The
  other eight are "all rights reserved" by default, so nothing in them can
  legally be reused, even by SFU, until a licence and a copyright holder
  are chosen.
- **Knowledge Engine is the first project with a licence consolidation
  process**: a per-image licence register, full licence texts, one SPDX
  SBOM per shipped image, a generated third-party notice file, GPL source
  offers, and a bundle step that refuses to ship an image with no reviewed
  licence row. The earlier projects have none of this.
- **Three projects depend on PyMuPDF, which is AGPL-3.0 or commercial.**
  That is the single biggest software-licence exposure if any of them is
  distributed or offered as a network service. Each one uses it only for
  plain-text PDF extraction, which pypdf, pdfplumber or Docling do under
  permissive licences.
- **Neo4j Community (GPL-3.0) is the graph store everywhere.** That is
  fine for internal use. Two older projects open a named database, which
  only Neo4j Enterprise (commercial) allows, and the official image ships a
  commercial plugin that Knowledge Engine now strips before redistribution.
- **Model weights drifted from Llama licences toward Apache-2.0.** The
  2025 projects ran Llama 3.1 and 3.2 (custom Meta licence with attribution
  and use-policy clauses). The 2026 Knowledge Engine ruling standardised on
  Qwen 3.5, gpt-oss 20B and 120B, and nomic-embed-text, all Apache-2.0.
- **No project records or enforces content rights per item.** Summit items
  carry author copyright and an "educational, non-commercial" permission
  statement in their metadata. Every pipeline that read Summit dropped or
  ignored those fields; one generated fine-tuning datasets from Summit text
  with no rights check, and one committed an author-copyrighted Summit PDF
  to a public repository.
- **Europeana was never used, and Arca BC was never actually accessed.**
  The "Arca" repositories ingest local PDF-plus-JSON folders; their only
  Arca sample record is a fabricated placeholder. The comparison in §4 is
  therefore between how the three platforms license content, not between
  three integrations that were built.

## 2. Project snapshot

| Project (last commit) | Purpose | Code licence | Chat model(s) | Embeddings | PDF / OCR | Serving | Stores |
|---|---|---|---|---|---|---|---|
| mcp_summit (2025-06) | MCP server + web UI over SFU Summit | MIT (holder unclear) | gpt-4o-mini (OpenAI API), llama3.2 | none | none (metadata only) | Ollama, OpenAI | SQLite cache, PDFs on disk |
| summit_data (2025-06) | Batch processor for a Summit export | none | none | all-MiniLM-L6-v2 (384) | pdfplumber, PyPDF2; no OCR | n/a | MongoDB (SSPL), Neo4j named DB |
| research_assistant (2025-11) | Air-gapped Windows research assistant | none | llama3.2:1b | all-mpnet-base-v2 (768) | PyMuPDF (AGPL); Tesseract imported, never called | Ollama | FAISS, Whoosh, Neo4j named DB, Redis |
| arcabc (2026-01) | Multi-agent Graph-RAG "Arca/BCELN edition" | none | llama3.1 | nomic-embed-text (768) | PyMuPDF (AGPL); no OCR | Ollama in Docker | Neo4j Community |
| arcabc_core (2026-01) | FastAPI hybrid Graph-RAG service | none | llama3.1 | all-MiniLM-L6-v2 (384) | pypdf; no OCR | Ollama in Docker | Neo4j Community |
| aria-openclaw-research-assistant (2026-05) | Summit research chat, Neo4j-only RAG | none | llama3.2 / gpt-oss:20b / deepseek-r1:14b (inconsistent) | nomic-embed-text (768) or MiniLM (384) | PyMuPDF (AGPL); no OCR | Ollama on GB10 host | Neo4j, MS SQL Server |
| aria-macstudio (2026-05) | Shared Mac Studio dev box | none | qwen3-coder, llama3.3 | unspecified | none | Ollama as LaunchDaemon | Neo4j, Redis (unpinned) |
| aria-gb10 (2026-06) | GB10 + DGX Spark ingestion/RAG | none (docs claim MIT) | Llama-3.1-8B-Instruct on vLLM; glm-4.7-flash on Ollama | nomic-embed-text (768) | pypdf, python-docx; no OCR | vLLM (NGC container) + Ollama | Neo4j Community, Redis 7 |
| student-assistant (2026-10) | SFU course/program advising graph RAG | none | llama3.1 (Ollama) or gpt-4o-mini (Azure); judge gemma4:31b / qwen3.6:35b-mlx | all-MiniLM-L6-v2 (384) CPU; Azure text-embedding-3-small option | none (HTML only) | Ollama native on host | Neo4j Community (digest-pinned) |
| Knowledge-engine (2026-10) | Policy/knowledge engine platform, offline bundle | MIT | compose+rewrite qwen3.5; audit gpt-oss:120b; fallback gpt-oss:20b | nomic-embed-text (768) | planned: CPU-first Tesseract / Docling / unstructured | Ollama now, vLLM later, behind a gateway allowlist | Postgres, Neo4j (own image), Valkey, Phoenix |

campus-ai (teamworxAI) could not be attached to this session, so it is not
covered. The non-Knowledge-engine repositories each have a single squashed
commit, so "why" is taken from their docs, not from history.

## 3. Software licensing consolidation

### 3.1 Code licences

| Repository | LICENSE | Copyright holder stated | Gap |
|---|---|---|---|
| Knowledge-engine | MIT | Humanaxiom, 2026 | none for the code; see 3.4 for open items |
| mcp_summit | MIT | an individual in LICENSE; "SFU" in README | holder must be settled |
| all eight others | none | none | choose licence and holder before any reuse or release |

Who owns the code (SFU, Humanaxiom, the individual authors, or PSFS under
the funding agreement) is a question for the funding agreement, not for the
repositories. Two aria-gb10 planning documents propose a dual
"open source plus paid enterprise licence" model; that is incompatible with
leaving the repository unlicensed, and nothing in them checks it against
the GPL and model licences the stack carries.

### 3.2 Third-party software, grouped by obligation

| Category | Components seen | Where | What it means |
|---|---|---|---|
| Permissive (MIT, BSD, Apache-2.0) | FastAPI, Streamlit, Flask, pydantic, httpx, sentence-transformers, transformers, torch, neo4j driver, LangChain/LangGraph, Ollama (MIT), vLLM (Apache-2.0), Ray, APOC core, Valkey (BSD-3), PostgreSQL licence, nginx | all projects | attribution in notices only |
| Weak copyleft | psycopg and psycopg-c (LGPL-3.0); tqdm and certifi (MPL-2.0); text-unidecode (Artistic/GPL dual) | Knowledge-engine; most Python stacks | keep the package replaceable and ship its licence text; Knowledge Engine records the exact sdist URLs and hashes |
| Strong copyleft | Neo4j Community server (GPL-3.0); Neo4j Graph Data Science plugin (GPL-3.0 in Community); Debian and Alpine GPL packages inside every base image | every project; GDS only in research_assistant's example compose | separate process, so no effect on app code. Redistributing images (an offline bundle) triggers the written source offer; Knowledge Engine built that (Q58, Q69) |
| Network copyleft | PyMuPDF (AGPL-3.0 or Artifex commercial) | arcabc, research_assistant, aria-openclaw | if the service is offered over a network the whole application source must be offered under AGPL, or a commercial licence bought. Replace with pypdf, pdfplumber or Docling |
| Source-available, not open source | Arize Phoenix (Elastic-2.0); Redis 7.4+ (RSALv2/SSPL) and 8.x; MongoDB server (SSPL) | Phoenix in Knowledge-engine (documented exception Q43); Redis in aria-gb10 (7-alpine), aria-macstudio and research_assistant (unpinned); MongoDB in summit_data and optional in research_assistant | internal on-premises use is allowed; offering them as a hosted service is not. Knowledge Engine chose Valkey over Redis for this reason |
| Commercial or proprietary | Neo4j Enterprise features (named databases, clustering); the fleet-management plugin shipped inside the official neo4j image; Microsoft SQL Server and ODBC driver; NVIDIA NGC vLLM container and CUDA EULA; nvidia-* CUDA wheels pulled by torch on Linux; OpenAI and Azure OpenAI APIs; Docker Desktop | research_assistant and summit_data (named DB); aria-openclaw and aria-gb10 (SQL Server); aria-gb10 (NGC); student-assistant (CUDA wheels, Azure); mcp_summit (OpenAI); Mac Studio and Windows hosts (Docker Desktop) | each needs an entitlement. Docker Desktop is free only below 250 employees and USD 10M revenue, which a university normally exceeds. Knowledge Engine removed the commercial jar from its neo4j image (Q67) |

### 3.3 Model weights

| Licence | Models | Used by |
|---|---|---|
| Llama Community Licence (custom: attribution "Built with Llama", acceptable-use policy, 700M MAU clause) | llama3.1, llama3.2 (1B, 3B), llama3.3, Llama-3.1-8B-Instruct, Llama-3.3-70B | mcp_summit, research_assistant, arcabc, arcabc_core, student-assistant default, aria-macstudio, aria-gb10 |
| Gemma Terms of Use (custom) | gemma4:31b judge | student-assistant evaluation |
| NVIDIA Open Model Licence | nemotron3:33b, Nemotron 70B/340B (listed, not deployed) | student-assistant evaluation, aria-gb10 scripts |
| Apache-2.0 | Qwen 3.5, qwen3-coder, qwen3.6, gpt-oss 20B and 120B, nomic-embed-text, all-MiniLM-L6-v2, all-mpnet-base-v2 | Knowledge-engine (all roles), aria-openclaw, aria-macstudio, every embedding path |
| MIT | deepseek-r1:14b, glm-4.7-flash (verify) | aria-openclaw script, aria-gb10 configs |
| Commercial API | gpt-4o-mini, text-embedding-3-small | mcp_summit, student-assistant Azure option |

Knowledge Engine's model ruling (ADR-KE-014) also fixed two habits the
earlier projects lacked: model names are configuration, never code (a test
scans for hard-coded names), and because Ollama tags move, every recorded
run stores the `/api/tags` digests of what was actually tested.

### 3.4 What Knowledge Engine put in place, and what is still open

In place: `NOTICE.md` with one reviewed licence row per pinned image
digest (the bundle refuses to build without it); full licence texts under
`licenses/`; SPDX 2.3 SBOM per bundled image; generated
`THIRD_PARTY_NOTICES.md`; psycopg built from source against Debian's libpq
so no LGPL libraries of unknown provenance are vendored (Q64); GPL source
archive and written offer built now rather than deferred to legal advice
(Q58, Q69); first-party neo4j image without the commercial plugin (Q67);
Phoenix recorded as the one source-available exception (Q43).

Open, and relevant to PSFS: who asks SFU legal/IP, and whether distribution
outside SFU is planned (noted under Q58 but not ruled); the source of the
three PostgreSQL-project packages in the postgres image (Q71); and the
copyright holder for every repository in §3.1.

## 4. Content licensing: Europeana vs SFU Summit vs Arca BC

| | Europeana | SFU Summit | Arca BC |
|---|---|---|---|
| What it is | EU aggregator of cultural heritage metadata and links to objects | SFU Library's research repository (Islandora 2 on Drupal, Fedora storage) | BC ELN's shared Islandora repository for BC post-secondary institutions |
| Machine access | REST APIs with a per-application key; IIIF and SPARQL without a key; read APIs free and unmetered | OAI-PMH at `/oai/request` (Dublin Core, MODS); an undocumented Drupal JSON surface (`node_export`, `/node/{id}?_format=json`, `citation_pdf_url`) | OAI-PMH at `/oai2` (Islandora 7) or `/oai/request`; `mdRecord` format includes `edm:preview` media links |
| Metadata licence | CC0 1.0 for all metadata, stated in the terms of use | not stated anywhere found; ask summit@sfu.ca | not stated site-wide; per institution |
| Object rights | per item, machine-readable in `edm:rights` (Creative Commons or rightsstatements.org); use must follow that statement | per item, in `field_sfu_rights`, `field_sfu_rights_holder`, `field_sfu_permissions`, `lac_rights`; typically "copyright held by the author(s)" plus pre-authorised educational, non-commercial reproduction | per item; creator holds copyright, Creative Commons where applied, otherwise Canadian copyright and fair dealing |
| Written API terms | yes: keys confidential and per application; rights statements bind reuse of files | none found | none found |
| What the projects did | nothing: no repository references Europeana | mcp_summit cached about 2,260 items (PDF plus JSON) locally; summit_data, research_assistant, aria-openclaw and aria-gb10 ingested the same export or the live JSON surface; none used OAI-PMH, none set a User-Agent or rate limit beyond retries, and none surfaced rights in answers | no live access; arcabc and arcabc_core ingest local PDF+JSON manifests; the only Arca sample is a placeholder and the "Arca" sample PDF is really a Summit thesis |

Reading of the comparison:

- **Europeana is the model to copy.** Metadata is CC0, so indexes, graphs
  and embeddings built from it carry no obligation; object rights travel
  with the record, so a pipeline can filter, cite and refuse per item.
- **Summit has the same per-item rights data, but no project used it.**
  The rights fields exist in every Summit record the projects downloaded.
  summit_data defined the fields and never filled them; research_assistant
  stored `lac_rights` and never displayed it; aria-openclaw does not capture
  rights; aria-gb10 exports fine-tuning datasets from Summit text without a
  check. Summit's pre-authorised permission is for educational,
  non-commercial reproduction, which does not obviously cover model
  training or a commercial "enterprise" tier.
- **Arca BC's rights model was never exercised.** Any future Arca work
  should start from its OAI-PMH feed and the per-institution statements,
  and should talk to the Arca Administrative Centre at BC ELN first.
- **SFU course outlines and calendar data** (student-assistant, aria-gb10)
  come from public SFU endpoints with no stated terms. The exports contain
  instructor emails and phone numbers, and embedded syllabi carry their own
  copyright and CC BY-NC statements. No robots or terms review was done.

Recommended minimum for the next group: one provenance record per item
(source URL, retrieved time, rights statement URI, rights holder, embargo
flag), carried through chunks, citations and exports; a hard refusal on
fine-tuning or redistribution exports unless the rights statement permits
it; a data-sharing agreement with SFU Library for Summit (the 2025 research
assistant's own docs already deferred external feeds "once data sharing
agreements are in place"); and no harvested PDFs, zips or `.env` files in
git.

## 5. Model choices: inference, OCR, embeddings

### 5.1 Inference

- **2025:** small Llama models on Ollama (llama3.2:1b with temperature 0.1
  as an anti-hallucination measure; llama3.1 with JSON mode at temperature
  0), plus gpt-4o-mini where a cloud key was acceptable.
- **2026 experiments:** gpt-oss:20b, deepseek-r1:14b, glm-4.7-flash,
  nemotron3:33b, Llama-3.1-8B on vLLM, Llama-3.3-70B as a code default.
  Several repositories configure different models in code, `.env` and docs,
  so a fresh install often fails with "model not found".
- **Knowledge Engine ruling (2026-10-20):** one model per role, in
  configuration only. Compose and rewrite use qwen3.5; audit uses
  gpt-oss:120b; fallback gpt-oss:20b; 120 s chat timeout, 60 s embed.
  A recorded run against the GB10 host measured a 33 s cold load for
  qwen3.5 and 18 s for gpt-oss:120b, inside the timeouts. Reasoning models
  can return empty content under a low token cap, so the tests assert
  non-empty content and report `finish_reason`.
- **Evaluation:** student-assistant is the only project with a gold set
  (100 cases, draft) and a RAGAS judge; no run has yet produced a valid
  baseline, and both attempts failed on judge output limits. Claims such as
  "zero hallucination", "90–98% accuracy" and "production ready" in the
  2025 and early-2026 docs have no evaluation behind them and should not
  be repeated to funders.

### 5.2 Embeddings and retrieval

- Progression: all-MiniLM-L6-v2 (384-d, CPU, fast, weak on scientific text)
  → all-mpnet-base-v2 (768-d, "stronger") → nomic-embed-text (768-d via
  Ollama), which Knowledge Engine adopted. Azure text-embedding-3-small
  (512-d) is an option in student-assistant.
- Vector store converged on Neo4j's native vector index (cosine), replacing
  FAISS + Whoosh (2025) and Chroma (early 2026); the recorded reason is
  fewer moving parts and one Cypher layer for semantic and graph retrieval.
  One critique notes the Neo4j index tops out around 10M vectors.
- No project has a trained reranker. Ranking is reciprocal-rank fusion,
  MMR, or a keyword-overlap blend. Hybrid retrieval with an exact-code
  lookup was kept in student-assistant because pure vector or full-text
  recall was about 0.3.
- Recurring defects: the embedding dimension must match the index (384 vs
  768) and switching requires dropping and recreating it; nomic's
  `search_query:` / `search_document:` prefixes are never added; embeddings
  are not invalidated when the indexed text changes.

### 5.3 PDF parsing and OCR

- Every pipeline extracts the PDF text layer only. No OCR runs anywhere:
  Tesseract is imported in one project and never called. Scanned theses and
  archival material therefore produce empty text silently; the Summit batch
  run reported 63.6% PDF extraction success.
- Knowledge Engine's ruling (Q8): CPU-only path by default (Tesseract,
  Docling or unstructured layout), GPU layout and vision models opt-in per
  stage; supported inputs PDF (text and OCR), DOCX/DOC/RTF, XLSX/CSV, HTML,
  Markdown.
- Licence note: Docling (MIT), Tesseract (Apache-2.0), pypdf (BSD) and
  pdfplumber (MIT) cover the same needs as PyMuPDF without AGPL.

## 6. Serving and platform decisions

### 6.1 Ollama vs vLLM

| | Ollama | vLLM |
|---|---|---|
| Used by | every project | aria-gb10 only (Llama-3.1-8B, BF16, 8k context, DGX Spark) |
| Strengths seen | one-command model pulls, many models resident with eviction, native on macOS and Linux, OpenAI-compatible endpoint, embeddings and chat in one server | higher throughput for concurrent users, true OpenAI API, streaming, one fixed model per server |
| Problems seen | context size cannot be set per request through the OpenAI endpoint (Modelfile aliases needed); `num_predict` must be inside `options`; cold loads of 30–45 s against short client timeouts; tags move under you; parallelism limited by `OLLAMA_NUM_PARALLEL` and memory | needs NGC login for the NVIDIA container and a Hugging Face token for gated Llama weights; `--gpu-memory-utilization 0.92` on a 128 GB unified-memory GB10 leaves little for everything else; about 60 s first load; served with no API key on all interfaces; model ids differ from Ollama tags, so one project sent an Ollama tag to vLLM and silently got empty answers |
| Position | dev, evaluation, embeddings, single-user | multi-user production with a pinned model |

Knowledge Engine's stance is "Ollama now, vLLM later": the app speaks only
the OpenAI-compatible API through one guarded client, so the switch is a
config change, and the model host is reachable only through the stack
gateway on an egress allowlist. Any change of host is an ADR amendment.

### 6.2 Docker vs VMs vs bare metal

- Every project runs its stores (Neo4j, Postgres, Redis/Valkey, Phoenix) in
  Docker Compose. No project used a VM.
- Ollama is almost always native on the host and reached from containers
  through `host.docker.internal` or `extra_hosts: host-gateway`. The reason
  is GPU access: Docker Desktop on macOS has no GPU passthrough, and Linux
  needs the NVIDIA Container Toolkit. vLLM runs as `docker run --gpus all
  --network host` with a large `--shm-size`.
- Knowledge Engine hardening that the earlier stacks lack: every image
  digest-pinned; the gateway is the only service that publishes ports, on
  loopback; the gate services run with no network; the offline bundle is
  one tarball per CPU architecture with a SHA-256 manifest; teardown lists
  leftovers and never deletes them itself.
- The GB10 is aarch64. Images must be built natively on an arm64 daemon
  (no `--platform` emulation), and some vendor images do not exist for
  arm64 (SQL Server among them).

### 6.3 WSL, Linux, macOS

- **Windows:** PowerShell 7.3+ scripts exist for build, launch, teardown
  and install. Gotchas recorded: CRLF checkouts broke shell scripts inside
  containers (fixed with `.gitattributes`); a winget `jq.exe` writes CRLF
  (run `jq.exe -b`); Docker inside WSL is a stub unless Docker Desktop's
  WSL integration is enabled for that distro; `.env` permissions need
  `icacls`; older projects hard-code drive letters; torch on Windows comes
  from the CUDA 13 index while Linux pulls proprietary nvidia wheels;
  console code page and emoji logging break; Gunicorn does not run on
  Windows.
- **Linux (Ubuntu 24.04 on the GB10, Docker 29):** the production target.
  Reached from a developer machine through a Docker context over SSH;
  arm64 proof is a recorded build, bundle, install, launch and smoke run.
- **macOS (Mac Studio M3):** Ollama as a root LaunchDaemon with one shared
  94 GB model store symlinked into each user; Docker Desktop per user with
  shared Neo4j/Redis via a LaunchAgent. Knowledge Engine supports macOS only
  through the offline arm64 bundle, and `install.sh`, `launch.sh` and
  `teardown.sh` are held to bash 3.2 and BSD tools by a test. MLX serving
  is deferred (Q52). The Mac's disaster-recovery plan was written but not
  executed, and some of it is wrong for Apple silicon.

## 7. Gotchas and pitfalls for the next group building a full stack

Licensing

1. Choose a licence and a copyright holder on day one; an unlicensed repo
   cannot be reused by anyone.
2. Keep a licence register keyed by image digest, and make the build fail
   when a row is missing. Pin digests, never `:latest`: unpinned `redis`
   and `neo4j` tags changed licence terms underneath two projects.
3. Avoid AGPL libraries (PyMuPDF) unless you intend to release under AGPL
   or buy a licence. Prefer Valkey to Redis, and know that Phoenix is
   Elastic-2.0 and Neo4j Community allows one user database.
4. If you redistribute images or an offline bundle, GPL source offers are
   your obligation. Knowledge Engine's SBOM and source-lock scripts do this.
5. Record model licences and the digest of every model you tested. Llama,
   Gemma and Nemotron carry conditions; Qwen, gpt-oss and nomic do not.
6. Budget for Docker Desktop, Neo4j Enterprise, SQL Server and NGC
   entitlements, or design them out.

Content

7. Store a rights statement, rights holder and source URL per item, carry
   it through chunks and citations, and refuse exports (fine-tuning,
   redistribution) that the statement does not allow.
8. Harvest politely: identify your client, throttle, use OAI-PMH where the
   repository offers it, and get a written agreement before bulk download.
9. Never commit harvested PDFs, zip snapshots or `.env` files. Three
   repositories did; one zip appears to hold real credentials.
10. Treat SFU calendar and outline exports as personal data (instructor
    emails and phones) and strip them before ingestion.

Models

11. Embedding dimension and model are one decision; changing either means
    dropping and rebuilding the index. Add nomic's task prefixes.
12. Set context length and token caps explicitly; Ollama ignores them in
    the wrong place and reasoning models return empty content when capped.
13. Size client timeouts to cold loads, and order tests so the cold load is
    measured, not hidden.
14. Keep one source of truth for the model name. Code defaults, `.env`,
    compose and docs disagreed in four repositories.
15. Add OCR before claiming PDF coverage; silent empty text is the default
    failure mode on scanned material.
16. Build a gold set and run it before any accuracy or "production ready"
    claim. AI-generated assessment documents in two repositories overstate
    readiness and should be read as drafts.

Platform

17. Never run `docker compose down -v` as a reset; it deletes the graph and
    any user memory.
18. Bind services to loopback and put one authenticated gateway in front;
    several stacks exposed Neo4j, Redis, Ollama, Streamlit and a remote
    desktop with default or no credentials.
19. Expect arm64: build natively on the GB10 or Apple silicon, one bundle
    per architecture, and check that every vendor image exists for arm64.
20. Leave headroom on unified-memory machines: a 0.92 GPU memory fraction
    on a 128 GB GB10 starves the OS and other containers.
21. Force LF line endings, pin the Python version, lock dependencies
    (`uv.lock` with `--locked`), and run one verification entry point
    locally and in CI with the same image. Stale or duplicate docs and
    scripts were the most common defect across all ten repositories.

## 8. Questions for PSFS and SFU to settle

- Copyright holder and licence for each repository (SFU, Humanaxiom,
  individual authors, or as the funding agreement says).
- Who engages SFU legal/IP on redistribution, GPL source offers and the
  AGPL exposure, and whether distribution outside SFU is intended.
- Terms for Summit content: metadata licence, bulk harvesting, and whether
  the educational non-commercial permission covers model training.
- Whether an Arca BC integration is still wanted, and if so an approach to
  BC ELN before any harvesting.
- Entitlements: Neo4j Community versus Enterprise, Docker Desktop,
  SQL Server, NVIDIA NGC, and whether cloud model APIs (Azure OpenAI) may
  receive Summit or student data at all.

## Appendix A: repositories scanned

| Repository | Last commit | Notes |
|---|---|---|
| humanaxiom/Knowledge-engine | 2026-10-30 | full history; docs/architecture.md, docs/open-questions.md, NOTICE.md |
| sfu-aria/student-assistant | 2026-10-20 | single squashed commit |
| adamsalah13/aria-gb10 | 2026-06-27 | single commit |
| adamsalah13/aria-macstudio | 2026-05-18 | single commit |
| adamsalah13/aria-openclaw-research-assistant | 2026-05-04 | single commit |
| adamsalah13/arcabc, adamsalah13/arcabc_core | 2026-01-07 | single commit each |
| adamsalah13/summit_data | 2026-01-07 | single commit |
| adamsalah13/research_assistant | 2025-11-15 | single commit |
| adamsalah13/mcp_summit | 2025-06-27 | public; the only LICENSE besides Knowledge-engine |
| teamworxAI/campus-ai | not scanned | could not be attached to this session |

## Appendix B: external sources consulted

- Europeana terms of use: https://www.europeana.eu/en/rights/terms-of-use
- Europeana API FAQ: https://europeana.atlassian.net/wiki/spaces/EF/pages/2360508417/API+FAQ
- Summit OAI-PMH registry entry: https://ird.coar-repositories.org/systems/b6987f6b-ad8c-453f-b232-d2b38a3c8cd0?lang=en
- About Summit: https://summit.sfu.ca/about-summit
- Arca OAI-PMH documentation: https://bceln.github.io/arca-docs/how-to/exposure/oai-pmh
- Arca registry entry: https://ird.coar-repositories.org/systems/e5636ebd-aad1-4305-9faf-75e043feb690?lang=en
- Arca FAQ on copyright: https://sc.arcabc.ca/about/faqs
