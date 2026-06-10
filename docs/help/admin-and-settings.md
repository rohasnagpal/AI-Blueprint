# Admin and Settings

Settings control API keys, models, RAG behavior, chat preferences, document limits, workspaces, matters, app branding, users, and activity logs. Some tabs are visible only to system admins or workspace admins.

## Settings Tabs

The current Settings area can include:

- API Keys
- Models
- RAG Provider
- RAG Behaviour
- Chat Preferences
- Documents
- Workspaces
- Matters
- Appearance
- Users
- Activity Log

If a tab is not visible, the current user may not have permission or the deployment may not expose that feature.

## Model Providers

Typed chat, Draft, Translate, Email draft generation, Contract Review, and Prep workflows use the configured chat model provider and model.

In the current Settings UI, the main Chat Model selector exposes OpenAI, Groq, and Ollama directly.

The API Keys and Model Registry areas can also store keys and model metadata for additional providers such as OpenRouter, Anthropic, Gemini, Perplexity, Mistral, xAI, Cloudflare Workers AI, and Together AI. Live model discovery is available for several of these providers, but visible chat provider choices and runtime behavior can vary by deployment and saved settings.

Live voice uses OpenAI Realtime and requires an OpenAI API key, regardless of the typed chat provider.

## API Keys

Add API keys in Settings. Missing keys cause provider-specific failures.

Examples:

- Groq typed chat requires a Groq API key.
- OpenAI typed chat requires an OpenAI API key.
- Ollama typed chat requires a reachable Ollama server or Ollama API endpoint. Local Ollama does not require a key.
- Draft, Translate, Contract Review, and Prep require a working configured chat model provider for full model-generated output.
- Live voice requires an OpenAI API key.
- Web search can use Brave Search or SearXNG. If neither is configured, some deployments can fall back to DuckDuckGo-style public search.

Do not expose API keys in screenshots, logs, commits, or shared exports.

## RAG Provider

RAG Provider controls how AI Blueprint stores and searches document embeddings. Switching providers may require existing documents to be re-indexed.

The current UI exposes:

- OpenAI RAG
- Local LlamaIndex + ChromaDB

Use this tab when changing the retrieval backend, embedding provider, or vector search configuration.

## RAG Behaviour

Important RAG behavior settings include:

- Top K: number of retrieved chunks.
- Similarity threshold: how strict retrieval should be.
- Chunk size and overlap: how documents are split.
- Retrieval strategy.
- Embedding model.

Embedding behavior depends on the configured environment. OpenAI embeddings are used when available. Some local or limited setups may fall back to a local embedding path rather than the external embedding provider shown in the UI.

If retrieval misses useful context, increase Top K or adjust scope. If answers include irrelevant material, narrow scope or tune retrieval settings.

## Chat Preferences

Chat preferences control default conversational behavior, including response length, source display, streaming, response language, and auto-detect language. Voice greetings use the configured app name and signed-in user when available.

## Web Search Providers

Search provider settings live in the API Keys area.

The current UI includes:

- Brave Search
- SearXNG

Use web search when the answer depends on current external information. Use Documents mode when the answer should rely on uploaded matter files.

## Documents Settings

Document settings include upload and indexing behavior such as maximum file size. If uploads fail, check file type, size, and document settings.

## Workspaces and Matters

System admins and authorized workspace users can manage workspaces and matters from Settings.

Roles matter:

- Workspace membership controls workspace visibility.
- Workspace admin permissions control workspace and matter administration.
- System admin permissions control user and activity administration.

## Users

System admins can manage users and workspace membership. Use this area to create users, change roles, and control access.

## Activity Log

The Activity Log shows audit events such as important user, workspace, document, and workflow activity. Use it for administrative review and troubleshooting.

## Appearance

Appearance settings control app name and branding. The app name appears in the UI and live voice greeting.

Example signed-in voice greeting:

`Hello Rohas Nagpal. Welcome to AI Blueprint for Lawyers.`

If no user is signed in, voice says:

`Welcome to AI Blueprint for Lawyers.`

## Email Settings

Email uses IMAP for incoming mail and SMTP for outgoing replies. Configure IMAP host, port, username, password, and folder before checking mail. Configure SMTP host, port, TLS verification, username, password, and from address before sending replies.

Email drafting can use a default persona and document context. Sending requires human approval.

## Deployment Controls

For production deployments:

- Use secure cookies.
- Run migrations explicitly.
- Protect secret key files.
- Restrict CORS origins.
- Configure upload limits.
- Avoid committing runtime data.
- Review activity logs and access controls.

Review deployment docs before exposing the app to public users.
