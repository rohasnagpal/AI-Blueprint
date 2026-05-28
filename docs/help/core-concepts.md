# Core Concepts

## Workspace

A workspace is the top-level container for a firm, team, department, solo practice, client group, or project environment. Workspaces hold matters, documents, plugins, blueprints, members, and settings.

Users must have workspace access before they can see workspace material. Workspace admins can manage workspace details, members, and plugin enablement.

## Matter

A matter organizes documents and workflows for a specific client, case, transaction, dispute, research project, or internal file. A matter can have multiple blueprints.

Use one matter when the documents and outputs should be considered together. Use separate matters when access, facts, clients, or work product should stay separate.

## Document

A document is an uploaded file or ingested source that can be indexed for retrieval. Documents may belong to a workspace, a matter, or a blueprint link.

Document-grounded answers depend on successful indexing. If a document is not indexed, chat, voice, and workflows may not find its contents.

## Blueprint

A blueprint is a plugin-backed workspace for a repeatable legal workflow. A blueprint has a name, plugin type, optional matter, status, members, configuration, runs, and outputs.

Examples:

- Contract Review blueprint
- AI Council blueprint
- Legal Research blueprint

## Plugin

A plugin provides a workflow type that blueprints can use. The current app exposes these blueprint plugins:

- Contract Review
- AI Council
- Legal Research

A plugin must be enabled for a workspace before users can create blueprints from it.

## Run

A run is one execution of a blueprint workflow. Runs have status values such as pending, running, completed, or failed. Runs may generate outputs, exports, audit events, summaries, findings, or review screens.

## Persona

A persona changes assistant behavior. Personas can provide role, tone, reasoning style, output structure, and constraints. Text chat and live voice can use the selected persona.

Changing persona after a live voice session starts does not change the active voice session. Stop and restart voice after changing persona.

## Chat Modes

Chat has two core modes:

- General: no document search.
- Documents: search uploaded documents in the selected scope.

Use Documents mode for file-grounded answers. Use General mode for app questions, brainstorming, drafting without documents, and open-ended discussion.

## Voice Mode

Live voice is a WebRTC speech-to-speech session. It can use the selected persona. In Documents mode, it can call document search and answer from retrieved excerpts.

Live voice currently uses OpenAI Realtime and requires an OpenAI API key. The selected typed-chat provider, such as Groq, does not power live voice.
