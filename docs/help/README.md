# AI Blueprint Help Pack

This folder is the source help knowledge base for AI Blueprint. It is written so a future text or voice assistant can answer product-use questions from grounded documentation instead of guessing from UI labels.

## Files

- [Start Here](start-here.md): first-time setup and the fastest successful path.
- [Core Concepts](core-concepts.md): workspaces, matters, documents, blueprints, plugins, personas, chats, councils, and runs.
- [Workspaces and Matters](workspaces-and-matters.md): workspace selection, matter creation, access, and scope.
- [Documents and RAG](documents-and-rag.md): uploading, indexing, scope selection, and document-grounded Q&A.
- [Document Management](document-management.md): Add Documents, View Documents, URL ingestion, connected folders, sync, search, and deletion.
- [Chat and Voice](chat-and-voice.md): typed chat, live voice, personas, document search, and model behavior.
- [Personas](personas.md): built-in and custom role-based behavior for chat, voice, email, and workflows.
- [Councils](councils.md): legacy council templates, runs, agents, phases, evidence, and outputs.
- [Blueprints and Plugins](blueprints-and-plugins.md): enabling plugins, creating blueprints, opening blueprint workspaces, and running workflows.
- [Contract Review](contract-review.md): structured contract review workflow, playbooks, review outputs, and human review.
- [AI Council and Arbitration Prep](ai-council-and-arbitration-prep.md): council workflows and arbitration preparation patterns.
- [Legal Research](legal-research.md): research memo workflow, questions, outputs, limitations, and exports.
- [Email](email.md): email account setup, polling, AI drafts, document-grounded replies, approval, and sending.
- [Translation](translation.md): text and document translation with modes, context, warnings, notes, and HTML output.
- [Admin and Settings](admin-and-settings.md): users, providers, API keys, model settings, and deployment controls.
- [Troubleshooting](troubleshooting.md): common issues and fixes.

## Intended Assistant Behavior

When this help pack is connected to chat or voice:

- Answer user-product questions from these files first.
- Ask a clarifying question when the user's current screen, workspace, matter, blueprint, or selected document scope is unclear.
- Do not invent buttons, workflows, or plugin capabilities not documented here.
- Distinguish between guidance and actions. Guidance explains what the user should do; actions change app state and should require explicit tool support and confirmation where needed.
- For legal work, remind users that AI Blueprint helps organize and draft work product but does not replace professional legal judgment.
