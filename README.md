# AI Blueprint for Lawyers

A local-first legal AI workspace for document-grounded chat, legal drafting, contract review, legal research, translation, email drafting, and multi-agent legal workflows.

AI Blueprint is built for lawyers, firms, legal teams, and legal operations teams that need AI to work with confidential documents, matter context, source grounding, review workflows, and auditability.

The goal is not to replace legal judgment. The goal is to give lawyers a structured workspace for reviewing documents, preparing arguments, drafting work product, testing positions, translating legal material, and organizing matter knowledge with stronger control over data, models, and retrieval scope.

## Core Capabilities

- **Document-grounded legal chat and RAG**  
  Ask questions across uploaded files, matter documents, contracts, emails, precedents, policies, statutes, regulations, and approved sources with scoped retrieval.

- **Legal drafting workspace**  
  Generate legal notices, agreements, replies, board documents, clauses, client-facing drafts, and other legal work product from facts, parties, terms, instructions, jurisdiction, tone, and optional source documents. Drafts include printable HTML, plain text, assumptions, missing information, review warnings, source usage, progress events, and saved draft history.

- **Contract review workflows**  
  Review contracts against playbooks, extract clauses, identify risks, compare fallback positions, generate redline suggestions, create negotiation points, produce summaries, record human review decisions, and export audit packages.

- **Legal research workflows**  
  Create research memos, authority matrices, legal tests, citation packs, limitation analysis, assumptions, and exportable research outputs.

- **Multi-agent councils and arbitration preparation**  
  Run configurable multi-agent workflows for adversarial review, evidence checking, issue mapping, arbitration prep, litigation strategy, settlement analysis, and partner review.

- **Email and client communication drafting**  
  Poll IMAP inboxes, generate AI-assisted replies using personas and document context, review drafts, and send approved replies through SMTP.

- **Translation for legal and business documents**  
  Translate pasted text or uploaded documents with legal, business, technical, literal, and plain-language modes, review warnings, translator notes, preserved terms, and downloadable HTML output.

- **Live voice assistance**  
  Use OpenAI Realtime voice for spoken legal assistance, matter walkthroughs, document questions, and workflow guidance, including document search in Documents mode.

- **Workspaces, matters, users, and permissions**  
  Organize documents, blueprints, plugins, members, roles, outputs, and access by workspace and matter.

- **Blueprints and plugins**  
  Enable repeatable workflows through blueprint plugins, currently Contract Review, AI Council, and Legal Research.

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
- Review a contract against a playbook and produce risks, fallback language, summaries, and an audit package.
- Prepare for arbitration by mapping facts, claims, evidence, counterarguments, and procedural risks.
- Build a litigation chronology from pleadings, exhibits, emails, and notes.
- Draft a legal research memo with authorities, limitations, and uncertainty clearly marked.
- Translate a legal document into another language with preserved terms and review warnings.
- Generate and approve a document-grounded client email reply.
- Compare clauses across versions of an agreement.
- Run a partner-review council before sending work product.

## Local and Network Versions

AI Blueprint can be used in two ways:

- **Local version:** run AI Blueprint privately on one machine for solo lawyers, experiments, document review, drafting, research, translation, and local-first workflows.
- **Network/server version:** run AI Blueprint for a firm, team, or legal department with shared workspaces, matter access, permissions, audit trails, reusable blueprints, and centralized configuration.

The local version is the fastest way to start. The network version is the direction for multi-user legal practice.

## Quick Start

Requirements:

- Python 3.10 or newer
- A browser
- Provider API keys depending on the models, voice, and retrieval mode you choose

Run locally:

```bash
git clone <repo-url>
cd AIBlueprint

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

## First Run

The fastest successful path is:

1. Sign in or complete first-run admin setup.
2. Create or select a workspace.
3. Create a matter for the client, dispute, transaction, research project, or internal file.
4. Add provider API keys in Settings.
5. Upload or ingest relevant documents.
6. Wait until documents are indexed.
7. Use Chat, Draft, Translate, Email, Voice, or a Blueprint workflow.
8. Review all outputs before using them in client, court, regulatory, or transaction work.

## Built With

- Python
- FastAPI
- Uvicorn
- SQLAlchemy
- Alembic
- SQLite
- OpenAI and Groq provider integrations
- Optional local RAG dependencies with Chroma, LlamaIndex, and sentence-transformers
- Vanilla HTML, CSS, and JavaScript frontend

## Configuration

AI Blueprint supports configurable model providers, document retrieval settings, personas, councils, email settings, workspaces, upload limits, app branding, and deployment controls from inside the app and through environment variables.

For legal use, configure the system around the matter:

- which documents are available
- which sources are approved
- which persona, draft settings, or workflow should be used
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

The current project includes document-grounded chat, live voice, legal drafting, translation, email drafting, personas, document management, workspaces and matters, contract review, legal research, multi-agent councils, permissions, jobs, audit events, encrypted secrets, and deployment controls.

## License

No open-source license has been declared yet. Add a `LICENSE` file before treating this repository as openly licensed.

## Authors and Acknowledgments

Created by Rohas Nagpal.

This project has been developed with assistance from AI coding tools including Claude and Codex.
