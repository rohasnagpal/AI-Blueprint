# Start Here

AI Blueprint is a legal AI workspace for document-grounded chat, live voice assistance, reusable personas, legal drafting, translation, email replies, contract review, and structured preparation workflows.

## AI Blueprint Mini

Use [AI Blueprint Mini](../../mini.html) when you want the supported single-file browser tool without installing the full workspace. Open the file in a browser, add an OpenRouter key, upload documents if needed, and describe the legal task in plain language.

Use the full AI Blueprint workspace when you need workspaces, matters, users, permissions, audit trails, document libraries, workflow history, email, voice, local RAG, or deployment controls.

The fastest successful path is:

1. Sign in or complete first-run admin setup.
2. Create or select a workspace.
3. Create a matter for the client, dispute, transaction, or project.
4. Upload or connect the relevant documents.
5. Wait until documents are indexed.
6. Choose Chat, a Prep workflow, Contract Review, Draft, Email, Translate, or Voice.
7. Use Documents mode whenever answers should be grounded in uploaded files.

## First-Time Setup

Open the app in a browser and complete sign-in or first-run admin setup. Workspace, matter, document, and workflow features require an authenticated user. In a local single-user deployment, the same person may be both system admin and workspace user.

After sign-in, confirm:

- A workspace exists.
- The current user has workspace access.
- The correct model, voice, and search provider settings are configured in Settings.
- Documents are uploaded, ingested from URL, or connected from a folder into the right workspace and matter.
- Documents show an indexed status before relying on document search.

## Main Navigation

The primary sidebar includes:

- **New Chat**: typed chat, document Q&A, web search toggle, and live voice.
- **Add Document**: upload files, ingest URLs, connect browser-selected folders, and sync local folders.
- **View Documents**: browse, search, inspect status, and delete documents.
- **Prep**: Arbitration Prep, Litigation Prep, Mediation Prep, and Negotiation Prep.
- **Workflows**: Contract Review, Draft, Email, and Translate.
- **Personas**: create and manage role-based assistant behavior.
- **Settings**: API keys, models, RAG, chat preferences, document settings, workspaces, matters, appearance, users, and activity.

## Choosing the Right Area

Use **Chat** for quick questions, summaries, explanations, document Q&A, and exploratory legal analysis.

Use the chat web search toggle when the answer depends on current external information rather than only uploaded matter files.

Use **Voice** for live spoken conversation. Voice can use the selected persona and, in Documents mode, can search the current document scope.

Use **Prep** for structured preparation packages:

- Arbitration Prep
- Litigation Prep
- Mediation Prep
- Negotiation Prep

Use **Contract Review** to review indexed contracts with a playbook, review depth, and optional review instructions.

Use **Draft** to generate legal notices, agreements, replies, clauses, board documents, client-facing drafts, and other legal work product from structured facts and optional source documents.

Use **Email** to poll an inbox, generate AI-assisted draft replies, review them, and send approved replies through SMTP.

Use **Translate** to translate pasted text or one uploaded document with review warnings and HTML output.

Use **Settings** to configure provider keys, models, RAG behavior, document limits, workspace and matter administration, appearance, users, and activity logs.

## Good First Prompts

For general chat:

- "Explain what this app can do."
- "Help me choose the right workflow for this matter."
- "What should I upload before mediation prep?"

For document chat:

- "Summarize the selected documents."
- "List the key dates and deadlines."
- "What are the main risks in these documents?"

For voice:

- "Help me prepare this matter."
- "Search the documents for termination provisions."
- "Walk me through what to do before arbitration prep."

For drafting:

- "Draft a legal notice from these facts and source documents."
- "Prepare a client-friendly summary letter using this matter background."
- "Draft a board resolution with these key terms."

For workflows:

- "Review this contract using the standard playbook."
- "Prepare an arbitration issue map from these documents."
- "Prepare negotiation talking points and fallback positions."
