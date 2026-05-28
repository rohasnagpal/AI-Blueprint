# Admin and Settings

Settings control model providers, API keys, RAG behavior, app branding, upload limits, and workspace behavior.

## Model Providers

Typed chat uses the configured Chat Model provider and model. Supported providers in the app include OpenAI, Anthropic, Groq, OpenRouter, Gemini, xAI, and Ollama, depending on installed packages and configured keys.

Live voice uses OpenAI Realtime and requires an OpenAI API key, regardless of the typed chat provider.

## API Keys

Add API keys in Settings. Missing keys cause provider-specific failures.

Examples:

- Groq typed chat requires a Groq API key.
- OpenAI typed chat requires an OpenAI API key.
- Live voice requires an OpenAI API key.
- Web search may require configured search provider keys.

Do not expose API keys in screenshots, logs, commits, or shared exports.

## Email Settings

Email uses IMAP for incoming mail and SMTP for outgoing replies. Configure IMAP host, port, username, password, and folder before checking mail. Configure SMTP host, port, TLS verification, username, password, and from address before sending replies.

Email drafting can use a default persona and document context. Sending requires human approval.

## RAG Settings

Important RAG settings include:

- Top K: number of retrieved chunks.
- Similarity threshold: how strict retrieval should be.
- Chunk size and overlap: how documents are split.
- Retrieval strategy.
- Embedding model.

If retrieval misses useful context, increase Top K or adjust scope. If answers include irrelevant material, narrow scope or tune retrieval settings.

## App Branding

The app name appears in the UI and live voice greeting. Example:

`Hello Rohas Nagpal. Welcome to AI Blueprint for Lawyers.`

If no user is signed in, voice says:

`Welcome to AI Blueprint for Lawyers.`

## Users and Workspaces

System admins can manage users. Workspace admins can manage workspace access and plugin enablement.

Roles matter:

- Workspace membership controls workspace visibility.
- Blueprint membership controls blueprint access.
- Blueprint owner/editor roles control editing and runs.

## Deployment Controls

For production deployments:

- Use secure cookies.
- Run migrations explicitly.
- Protect secret key files.
- Restrict CORS origins.
- Configure upload limits.
- Avoid committing runtime data.

Review deployment docs before exposing the app to public users.
