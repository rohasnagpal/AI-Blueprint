# AI Blueprint

AI Blueprint is a local-first FastAPI web app for document-grounded AI chat, web-assisted research, personas, model management, and multi-agent council workflows.

It runs as a single Python server with a single-page HTML frontend. Runtime data is stored locally in SQLite, uploaded files, and optional local vector indexes.

## Current Features

- **Document chat with RAG** using either OpenAI Vector Stores or local LlamaIndex + ChromaDB.
- **URL ingestion** for adding webpages to the document knowledge base.
- **Web search in chat** with source citations.
- **Free web search fallback** through DuckDuckGo HTML search, plus optional SearXNG and Brave Search support.
- **Streaming chat responses** over server-sent events.
- **Source citations** for document chunks and web results.
- **Personas** for changing assistant behavior from the chat UI.
- **AI Councils** for running multi-agent workflows in phases against an objective and document scope.
- **Council templates and run history** stored locally.
- **Model registry** for adding, editing, disabling, and deleting model options.
- **Settings UI** for API keys, RAG behavior, chat preferences, appearance, and app text.
- **Chat archive/delete** from the sidebar.
- **GitHub Actions CI** and cross-platform package builds.

## Quick Start

### Requirements

- Python 3.10 or newer
- A browser
- Optional API keys depending on provider:
  - OpenAI for OpenAI RAG or OpenAI chat
  - Groq for Groq chat
  - Brave Search only if you want Brave instead of the free search fallback

### Run Locally

```bash
git clone https://github.com/yourusername/ai-blueprint.git
cd ai-blueprint

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

Open:

```text
http://127.0.0.1:8000
```

On first use, open **Settings -> API Keys** and add the provider keys you need.

## Core Workflows

### Add Documents

Use **Add Documents** to upload files or paste a webpage URL.

Supported uploads:

| Type | Extensions |
|---|---|
| PDF | `.pdf` |
| Word | `.docx` |
| Text | `.txt`, `.md` |
| Data | `.csv`, `.xlsx`, `.json` |
| HTML | `.html`, `.htm` |

URL ingestion fetches readable webpage text, saves it as a markdown document, and indexes it through the active RAG provider.

### Chat

The chat input supports:

- **General mode**: no document context.
- **Documents mode**: answer using uploaded documents.
- **Web search toggle**: adds live web results to the prompt and shows web citations.
- **Persona selector**: applies a saved persona to the conversation.

### Web Search

Search provider order:

1. **SearXNG** if `searxng_base_url` is set in Settings.
2. **Brave Search** if `brave_search_api_key` is set.
3. **DuckDuckGo HTML** fallback with no API key.

DuckDuckGo fallback is useful for local testing and free usage. For production reliability, use SearXNG or a paid search API.

### AI Councils

Councils let you run multiple AI participants in ordered phases.

You can:

- use built-in templates
- create custom templates
- configure participant roles, instructions, provider, model, temperature, and token limits
- run phases sequentially or in parallel
- scope runs to all documents or selected documents
- review saved outputs and evidence

## RAG Modes

Switch providers in **Settings -> RAG Provider**.

### OpenAI RAG

Uses OpenAI files, vector stores, assistants, and file search.

- Requires an OpenAI API key.
- Documents are uploaded to OpenAI.
- Easiest setup.

### Local RAG

Uses LlamaIndex, ChromaDB, and sentence-transformers.

- Keeps document embeddings local.
- Requires extra dependencies.
- Still needs a chat model provider unless using Ollama.

Install local RAG dependencies:

```bash
pip install chromadb --no-deps
pip install -r requirements-local.txt
```

For Python 3.12 or earlier, this usually also works:

```bash
pip install chromadb
pip install -r requirements-local.txt
```

## Model Providers

The app currently supports chat generation through:

- OpenAI
- Groq
- Ollama
- Anthropic path in backend code

Model dropdowns are driven by **Settings -> Model -> Model Registry**, so provider model lists can be updated without code changes.

## Settings

All settings are stored in SQLite. API keys are encrypted at rest.

Important settings:

| Setting | Purpose |
|---|---|
| `openai_api_key` | OpenAI chat and OpenAI RAG |
| `groq_api_key` | Groq chat |
| `brave_search_api_key` | Optional Brave Search |
| `searxng_base_url` | Optional SearXNG endpoint |
| `rag_provider` | `openai` or `llamaindex` |
| `local_llm_provider` | Chat provider |
| `chat_model` | Active chat model |
| `top_k` | Number of retrieved chunks |
| `similarity_threshold` | Local RAG relevance threshold |
| `chunk_size`, `chunk_overlap` | Document splitting controls |

## GitHub Actions

The repo includes two workflows.

### CI

`.github/workflows/ci.yml`

- Runs on pull requests.
- Runs on pushes to `main`.
- Tests Python 3.10, 3.11, and 3.12.
- Installs `requirements.txt`.
- Compiles Python files.

### Build Installers

`.github/workflows/build-installers.yml`

Builds portable packages for:

- Linux: `ai-blueprint-linux.tar.gz`
- macOS: `ai-blueprint-macos.dmg`
- Windows: `ai-blueprint-windows.zip`

It runs on:

- any pushed tag, such as `alpha-4` or `v1.0.0`
- published GitHub releases
- manual workflow dispatch

For an existing release, run the workflow manually and enter the release tag in `release_tag`.

macOS builds are unsigned and not notarized, so Gatekeeper may show a warning.

## Project Structure

```text
ai-blueprint/
├── main.py                       # FastAPI entry point
├── database.py                   # SQLite schema, settings, seeds, encryption
├── webtools.py                   # URL fetch/extract and web search providers
├── routes/
│   ├── chats.py                  # Chat APIs and streaming responses
│   ├── documents.py              # Uploads, URL ingestion, document deletion
│   ├── councils.py               # Council templates, runs, outputs
│   ├── personas.py               # Built-in persona listing
│   └── settings.py               # Settings and model registry APIs
├── rag/
│   ├── base.py                   # RAG provider interface
│   ├── openai_rag.py             # OpenAI vector store RAG
│   └── llamaindex_rag.py         # Local ChromaDB RAG
├── public/
│   └── index.html                # Single-page frontend
├── uploads/                      # Runtime uploads, ignored by git
├── chroma_db/                    # Runtime local vector store, ignored by git
├── .github/workflows/
│   ├── ci.yml
│   └── build-installers.yml
├── requirements.txt
├── requirements-local.txt
└── README.md
```

## Runtime Files

These are created locally and intentionally ignored by git:

- `ai_blueprint.db`
- `.secret_key`
- `uploads/`
- `chroma_db/`

Do not commit them. They may contain chat history, document data, vector indexes, or encrypted keys.

## Troubleshooting

### Port 8000 is already in use

```bash
uvicorn main:app --host 0.0.0.0 --port 8080
```

Then open:

```text
http://127.0.0.1:8080
```

### URL ingestion says Method Not Allowed

Restart the FastAPI process. This usually means the browser is serving the updated frontend while the backend is still an older process.

### Local RAG dependency errors

Install the local dependency set:

```bash
pip install chromadb --no-deps
pip install -r requirements-local.txt
```

### Ollama is not running

Start Ollama before sending chat messages:

```bash
ollama serve
```

### GitHub release only shows source code

GitHub always adds source archives automatically. To attach app packages, make sure the **Build Installers** workflow has run for that tag or run it manually with `release_tag`.

## Security Notes

- API keys are encrypted with AES-GCM before storage.
- The encryption key is stored in `.secret_key`.
- Settings APIs return masked keys, not plaintext keys.
- Local RAG keeps document retrieval local.
- OpenAI RAG uploads documents to your OpenAI account.
- Web search and URL ingestion make outbound network requests from the server.

## Current Limitations

- Packaged desktop builds are portable server executables, not native GUI apps.
- macOS DMG is unsigned and not notarized.
- URL scraping is lightweight HTML/text extraction; JavaScript-heavy pages may not extract well.
- DuckDuckGo HTML search is a free fallback, not a guaranteed production API.

## License

MIT
