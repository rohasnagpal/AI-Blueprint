# Chat and Voice

## Typed Chat

Typed chat is best for precise questions, longer drafting, summaries, document Q&A, and outputs that users may copy into work product.

Typed chat uses the configured Chat Model provider and model in Settings. Supported providers can include OpenAI, Anthropic, Groq, OpenRouter, Gemini, xAI, and Ollama depending on configured keys and installed dependencies.

## Chat Modes

Chat supports:

- **General**: no document search.
- **Documents**: retrieves excerpts from the selected workspace, matter, or document set.

Use Documents mode when the answer should be grounded in uploaded files. Use General mode for product questions, brainstorming, strategy discussion, or early drafting.

## Web Search

The chat interface can expose a web search toggle when configured. Use web search for current external information. Use Documents mode for the user's uploaded matter materials. When both current law and uploaded facts matter, verify important sources before relying on the answer.

## Live Voice

Live voice is best for interactive guidance, quick document questions, brainstorming, walkthroughs, and hands-free preparation.

Live voice uses OpenAI Realtime and requires an OpenAI API key. It does not use the selected typed-chat provider.

When voice connects, it greets the user. If the user is signed in, it says:

`Hello {user}. Welcome to {app name}.`

If the user is not signed in, it says:

`Welcome to {app name}.`

## Personas in Chat and Voice

Select a persona before sending a typed message or starting voice. Personas can change role, tone, structure, and constraints.

Examples:

- Contract Reviewer for structured contract analysis.
- Litigation Associate for case preparation.
- Arbitration Prep Analyst for dispute preparation.
- Plain-English Explainer for client-friendly summaries.
- Partner Reviewer for critique before delivery.

For voice, changing persona during an active session does not alter the session. Stop and restart voice after changing persona.

## Documents in Chat and Voice

Both typed chat and live voice can answer from documents when the composer is in Documents mode.

Typed chat sends the user question through the chat RAG pipeline.

Live voice exposes a `search_documents` tool to the Realtime model. When the model decides document context is needed, it calls the tool, receives excerpts, and speaks an answer grounded in those excerpts.

## When to Use Chat

Use typed chat when:

- You need a long or structured answer.
- You want to copy text.
- You need a table, list, memo, or draft.
- You want careful review of document evidence.
- You are comparing many clauses or sources.

## When to Use Voice

Use live voice when:

- You want a conversational walkthrough.
- You are preparing orally for a meeting, hearing, negotiation, mediation, or client call.
- You want to ask follow-ups quickly.
- You want the app to guide you through what to do next.

## Limits

Voice can search documents and follow personas, but it does not operate every app action by speech. For example, it can explain how to run Contract Review or Arbitration Prep, but it should not click Run, delete outputs, send email, or change settings unless app-action tools are added later.

Typed chat can guide users through workflows, but product-use answers should be grounded in this help pack.
