# Core Concepts

## Workspace

A workspace is the top-level container for a firm, team, department, solo practice, client group, or project environment. Workspaces hold matters, documents, personas, workflow runs, settings, members, and audit activity.

Users must have workspace access before they can see workspace material. System admins and workspace admins can manage workspace details and membership from Settings when those tabs are available.

## Matter

A matter organizes documents and workflows for a specific client, case, transaction, dispute, research project, or internal file.

Use one matter when the documents and outputs should be considered together. Use separate matters when access, facts, clients, or work product should stay separate.

## Document

A document is an uploaded file, URL-ingested page, browser-folder file, or local-folder synced file that can be indexed for retrieval. Documents belong to a workspace and may also belong to a matter.

Document-grounded answers depend on successful indexing. If a document is not indexed, Chat, Voice, Contract Review, Draft, and Prep workflows may not find its contents.

## RAG

RAG means retrieval-augmented generation. AI Blueprint retrieves chunks from indexed documents and passes relevant excerpts to the model. RAG depends on the selected workspace, matter, document IDs, and retrieval settings.

## Persona

A persona changes assistant behavior. Personas can provide role, tone, reasoning style, output structure, and constraints. Text chat, live voice, email drafting, and some workflows can use selected personas.

Changing persona after a live voice session starts does not change the active voice session. Stop and restart voice after changing persona.

## Chat Modes

Chat has two core modes:

- General: no document search.
- Documents: search uploaded and indexed documents in the selected scope.

Use Documents mode for file-grounded answers. Use General mode for app questions, brainstorming, drafting without documents, and open-ended discussion.

## Voice Mode

Live voice is a WebRTC speech-to-speech session. It can use the selected persona. In Documents mode, it can call document search and answer from retrieved excerpts.

Live voice currently uses OpenAI Realtime and requires an OpenAI API key. The selected typed-chat provider, such as Groq or Anthropic, does not power live voice.

## Job

A job tracks longer-running work such as draft generation, contract review, translation, and prep runs. Jobs can have pending, running, completed, failed, or cancelled status values and may expose progress events.

## Run

A run is one execution of a workflow. Current user-facing runs include Contract Review runs and Prep runs. Runs may generate outputs, source lists, warnings, audit traces, history entries, and downloadable Markdown or HTML.

## Draft

A draft is generated legal work product created from structured inputs such as document type, jurisdiction, tone, audience, parties, facts, key terms, drafting instructions, and optional source documents.

Drafts are standalone workspace outputs that can be copied, printed, downloaded, and reopened from Draft History.

## Translation Run

A translation run translates pasted text or one uploaded document. It may produce HTML output, translator notes, preserved terms, review warnings, and quality checks.

## Contract Review Run

A contract review run analyzes indexed contract documents using review depth, playbook selection, and review instructions. It can produce clause analysis, risks, redline suggestions, summaries, warnings, and source references.

## Prep Run

A prep run produces a structured preparation package for arbitration, litigation, mediation, or negotiation. Prep runs use matter documents and fields such as party role, forum or court, jurisdiction, stage, dates, focus, and instructions.

## Blueprint Records

Older AI Blueprint versions exposed blueprints and plugins directly. The current UI uses direct Prep and Workflow screens. Some backend records are still stored as blueprint instances so runs can be persisted, audited, and related to matters. Users normally do not need to create or edit these records directly.

## Escalation

An escalation is a flagged issue that needs attention, such as a high-risk contract finding or workflow concern. Escalations should be resolved or dismissed only after human review.
