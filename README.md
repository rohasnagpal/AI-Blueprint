# AI Blueprint for Lawyers

[![CI](https://img.shields.io/github/actions/workflow/status/rohasnagpal/AI-Blueprint/ci.yml?branch=main&label=CI)](https://github.com/rohasnagpal/AI-Blueprint/actions/workflows/ci.yml)
[![Installers](https://img.shields.io/github/actions/workflow/status/rohasnagpal/AI-Blueprint/build-installers.yml?label=installers)](https://github.com/rohasnagpal/AI-Blueprint/actions/workflows/build-installers.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136.1-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](https://github.com/rohasnagpal/AI-Blueprint/blob/main/Dockerfile)
[![License](https://img.shields.io/github/license/rohasnagpal/AI-Blueprint)](https://github.com/rohasnagpal/AI-Blueprint/blob/main/LICENSE)

A local-first legal AI workspace for document-grounded chat, live voice assistance, legal drafting, contract review, preparation workflows, translation, email drafting, and matter document management.

AI Blueprint is built for lawyers, firms, legal teams, and legal operations teams that need AI to work with confidential documents, matter context, source grounding, review workflows, and auditability.

The goal is not to replace legal judgment. The goal is to give lawyers a structured workspace for reviewing documents, preparing disputes and negotiations, drafting work product, translating legal material, and organizing matter knowledge with stronger control over data, models, and retrieval scope.

## Core Capabilities

- **Document-grounded legal chat and RAG**  
  Ask questions across uploaded files, matter documents, contracts, emails, precedents, policies, statutes, regulations, and approved sources with scoped retrieval.

- **Legal drafting workspace**  
  Generate legal notices, agreements, replies, board documents, clauses, client-facing drafts, and other legal work product from facts, parties, terms, instructions, jurisdiction, tone, and optional source documents. Drafts include printable HTML, plain text, assumptions, missing information, review warnings, source usage, progress events, and saved draft history.

- **Contract review workflows**  
  Review indexed contracts directly from a workspace and matter. Use review depth, playbooks, selected source contracts, and review instructions to produce clause analysis, risks, redline suggestions, summaries, warnings, source references, and downloadable Markdown output.

- **Preparation workflows**
  Prepare structured arbitration, litigation, mediation, and negotiation work product from indexed matter documents. Prep runs can produce case snapshots, issue maps, chronologies, evidence matrices, procedural tasks, witness or participant preparation, damages and remedies analysis, risks, gaps, trace data, warnings, and source basis.

- **Legal research support**
  Use Chat, Documents mode, Draft, and Prep workflows to research legal questions, analyze uploaded authorities, produce research memos, and test arguments. Current primary navigation does not expose a separate Legal Research screen.

- **Email and client communication drafting**  
  Poll IMAP inboxes, generate AI-assisted replies using personas and document context, review drafts, and send approved replies through SMTP.

- **Translation for legal and business documents**  
  Translate pasted text or uploaded documents with legal, business, technical, literal, and plain-language modes, review warnings, translator notes, preserved terms, and downloadable HTML output.

- **Live voice assistance**  
  Use OpenAI Realtime voice for spoken legal assistance, matter walkthroughs, document questions, and workflow guidance, including document search in Documents mode.

- **Workspaces, matters, users, and permissions**  
  Organize documents, runs, members, roles, outputs, and access by workspace and matter.

- **Current navigation**
  Work from New Chat, Add Document, View Documents, Prep, Workflows, Personas, and Settings. The Prep menu includes Arbitration Prep, Litigation Prep, Mediation Prep, and Negotiation Prep. The Workflows menu includes Contract Review, Draft, Email, and Translate.

- **Document management**  
  Upload files, ingest URLs, connect local folders, sync folder sources, index documents, search document libraries, and manage deletion.

- **Personas and role-specific behavior**  
  Configure reusable legal roles such as Contract Reviewer, Litigation Associate, Legal Researcher, Partner Reviewer, Plain-English Explainer, Evidence Analyst, and Client Email Drafter.

- **Auditability, jobs, and trust controls**  
  Track runs, job progress, exports, escalations, audit events, provider/model use, encrypted secrets, review warnings, and human approval points.

- **Local-first and privacy-conscious deployment**  
  Run locally or deploy for teams with explicit runtime paths, secure cookies, CORS controls, migrations, encrypted secrets, and protected upload/database storage.

## Example Workflows

- Draft a legal notice from facts, parties, jurisdiction, tone, and selected source documents.
- Review a contract against a playbook and produce risks, fallback language, summaries, warnings, and source references.
- Prepare for arbitration by mapping issues, chronology, evidence, witnesses, damages, and procedural risks.
- Build a litigation preparation package from pleadings, exhibits, emails, and notes.
- Prepare mediation or negotiation strategy with positions, interests, information gaps, talking points, concessions, and settlement options.
- Draft a legal research memo from a precise question, jurisdiction, facts, and uploaded source materials.
- Translate a legal document into another language with preserved terms and review warnings.
- Generate and approve a document-grounded client email reply.
- Compare clauses across versions of an agreement.
- Use a Partner Reviewer persona before sending work product.

## Local and Network Versions

AI Blueprint can be used in two ways:

- **Local version:** run AI Blueprint privately on one machine for solo lawyers, experiments, document review, drafting, research, translation, and local-first workflows.
- **Network/server version:** run AI Blueprint for a firm, team, or legal department with shared workspaces, matter access, permissions, audit trails, reusable workflows, and centralized configuration.

The local version is the fastest way to start. The network version is the direction for multi-user legal practice.

## Quick Start

Requirements:

- Python 3.10 or newer
- A browser
- Provider API keys depending on the models, voice, and retrieval mode you choose

Run locally:

```bash
git clone https://github.com/rohasnagpal/AI-Blueprint.git
cd AI-Blueprint

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

Open:

```text
http://127.0.0.1:8000
```

On first use, complete the setup flow, create or select a workspace, and open Settings to add the model or provider keys you need.

For closed local deployments that need a temporary bootstrap account, set `AI_BLUEPRINT_BOOTSTRAP_DEFAULT_ADMIN=true` before starting the server, then sign in with the bootstrap credentials and immediately change them. Do not use the bootstrap account path for public deployments.

## Local-Only Beta Notes

For a local-only beta, run AI Blueprint on the user's own machine and open it only through:

```text
http://127.0.0.1:8000
http://localhost:8000
```

Do not bind the app to a public interface or share the local port on a LAN unless you are intentionally running a network/server deployment.

Recommended local-only settings:

```bash
AI_BLUEPRINT_ENV=development
AI_BLUEPRINT_SECURE_COOKIES=false
AI_BLUEPRINT_CORS_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

HTTPS is not required for same-machine localhost use. HTTPS and `AI_BLUEPRINT_SECURE_COOKIES=true` are required when AI Blueprint is exposed through a real domain, reverse proxy, tunnel, LAN hostname, or public server.

### Local Data and Backups

Local users are responsible for their own backups. Back up these runtime files together:

```text
ai_blueprint.db
ai_blueprint_v2.db
uploads/
uploads_v2/
chroma_db/
.secret_key
.secret_key_v2
```

The secret key files are required to decrypt stored credentials after restore. Keep backup archives outside the repository and treat them as confidential client data.

### Provider Privacy

AI Blueprint runs locally, but configured external providers may still receive data. Depending on enabled settings, model, embedding, retrieval, email, or voice providers may receive prompts, document excerpts, embeddings, credentials, audio, outputs, or related metadata.

Review each provider's data usage and retention policy before using confidential client material. If no external provider is configured, local documents and local databases remain on the user's machine.

## First Run

The fastest successful path is:

1. Sign in or complete first-run admin setup.
2. Create or select a workspace.
3. Create a matter for the client, dispute, transaction, research project, or internal file.
4. Add provider API keys in Settings.
5. Upload or ingest relevant documents.
6. Wait until documents are indexed.
7. Use Chat, Voice, Prep, Contract Review, Draft, Translate, or Email.
8. Review all outputs before using them in client, court, regulatory, or transaction work.

## Built With

- Python
- FastAPI
- Uvicorn
- SQLAlchemy
- Alembic
- SQLite
- Configurable provider integrations including OpenAI, Anthropic, Groq, OpenRouter, Gemini, Perplexity, Mistral, xAI, and Ollama
- Optional local RAG dependencies with Chroma, LlamaIndex, and sentence-transformers
- Vanilla HTML, CSS, and JavaScript frontend

## Configuration

AI Blueprint supports configurable model providers, document retrieval settings, web search providers, personas, email settings, workspaces, matters, upload limits, app branding, users, activity logs, and deployment controls from inside the app and through environment variables.

For legal use, configure the system around the matter:

- which documents are available
- which sources are approved
- which persona, draft settings, prep workflow, or contract review settings should be used
- which users can access the matter
- which outputs need review before use
- which model providers may receive prompts, document snippets, embeddings, and outputs

For production settings, see [Deployment Guide](docs/DEPLOYMENT.md).

## Privacy Note

AI Blueprint is designed as a local-first legal AI workspace. Sensitive runtime data such as uploaded documents, chat history, draft history, translation history, local databases, vector indexes, logs, and API keys should not be committed to version control.

When using external model, embedding, retrieval, email, or voice providers, review where document text, prompts, embeddings, credentials, audio, and outputs are sent before using the system with confidential material.

AI Blueprint supports legal workflows but does not replace professional legal judgment. Review all outputs before using them in client, court, regulatory, or transaction work.

## Documentation

- [User Help Pack](docs/help/README.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Public Launch Checklist](docs/PUBLIC_LAUNCH_CHECKLIST.md)
- [Operations Guide](OPERATIONS.md)
- [Security Policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## Public Deployment

Before exposing AI Blueprint to public users, review:

- [Deployment Guide](docs/DEPLOYMENT.md)
- [Public Launch Checklist](docs/PUBLIC_LAUNCH_CHECKLIST.md)

Production deployments should run database migrations explicitly before app startup:

```bash
.venv/bin/python scripts/migrate.py
```

Keep `AI_BLUEPRINT_RUN_MIGRATIONS_ON_STARTUP=false` in production so multiple workers cannot race while applying migrations.

## Development

Install dependencies and run the app as shown in Quick Start. Before opening a pull request, run:

```bash
python -m compileall main.py database.py routes rag app migrations
python -m unittest discover -s tests
```

See [Contributing](CONTRIBUTING.md) for contribution expectations.

## Development Status

AI Blueprint is an evolving open-source platform being shaped into a practical legal AI workspace for lawyers, firms, and legal teams.

The current project includes document-grounded chat, live voice, legal drafting, translation, email drafting, personas, document management, workspaces and matters, standalone contract review, arbitration prep, litigation prep, mediation prep, negotiation prep, permissions, jobs, audit events, encrypted secrets, and deployment controls.

## License

AI Blueprint is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

## Authors and Acknowledgments

Created by Rohas Nagpal.

This project has been developed with assistance from AI coding tools including Claude and Codex.
