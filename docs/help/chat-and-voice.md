# Chat and Voice

## Typed Chat

Typed chat is best for precise questions, longer drafting, summaries, document Q&A, and outputs that users may copy into work product.

Typed chat uses the configured Chat Model provider and model in Settings. For example, it may use Groq with `openai/gpt-oss-120b`, OpenAI, Anthropic, Gemini, OpenRouter, xAI, or Ollama depending on configuration.

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
- Socratic persona for guided questioning.
- Plain-English explainer for client-friendly summaries.
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
- You are preparing orally for a meeting, hearing, or client call.
- You want to ask follow-ups quickly.
- You want the app to guide you through what to do next.

## Limits

Voice can search documents and follow personas, but it does not yet operate every blueprint action by speech. For example, it can explain how to run a Contract Review blueprint, but it cannot safely click Run Contract Review or delete outputs unless app-action tools are added later.

Typed chat can guide users through workflows, but it also needs app-help context to answer product-use questions reliably.
