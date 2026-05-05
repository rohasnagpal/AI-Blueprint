# AI Blueprint

Chat with your documents using AI — privately, on your own laptop. No accounts, no cloud uploads, no data leaving your machine (unless you choose OpenAI mode).

Upload PDFs, Word docs, spreadsheets, or plain text. Ask questions in natural language. Get cited answers streamed in real time.

---

## Features

- **Two RAG modes** — OpenAI (cloud, easiest) or fully local with ChromaDB + sentence-transformers (no API key needed)
- **Streaming responses** — answers appear word by word, like ChatGPT
- **Source citations** — every answer links back to the exact document it came from
- **27 languages** — respond in English, Hindi, Arabic, Spanish, French, German, Japanese, Chinese, and more
- **Multiple LLM backends** — OpenAI, Groq, or Ollama (run local models like Llama 3)
- **No setup friction** — all configuration (API keys, models, settings) lives inside the app's Settings page. No `.env` files to edit.

---

## Supported File Types

| Format | Extension |
|--------|-----------|
| PDF | `.pdf` |
| Word | `.docx` |
| Plain text | `.txt` |
| CSV | `.csv` |
| Excel | `.xlsx` |
| Markdown | `.md` |
| JSON | `.json` |

---

## Quick Start

### Requirements

- Python 3.10 or higher — [download here](https://python.org)
- An OpenAI API key (for OpenAI mode) — [get one here](https://platform.openai.com/api-keys)

### Install and run

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/ai-blueprint.git
cd ai-blueprint

# 2. Create a virtual environment
python3 -m venv .venv

# 3. Activate it
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Start the app
python main.py
```

Then open **http://localhost:8000** in your browser.

On first launch, go to **Settings → API Keys** and enter your OpenAI API key. That's it — start uploading documents and chatting.

---

## RAG Modes

AI Blueprint supports two retrieval modes. Switch between them in **Settings → RAG Provider**.

### OpenAI RAG (default)

Uses OpenAI's Files API, Vector Stores, and Assistants API.

- Requires an OpenAI API key
- Documents are uploaded to and searched by OpenAI
- Best answer quality, easiest to set up

### Local RAG

Uses [LlamaIndex](https://www.llamaindex.ai/) + [ChromaDB](https://www.trychroma.com/) + [sentence-transformers](https://sbert.net/) — everything runs on your machine.

- No API key needed for embeddings
- Documents never leave your computer
- Uses `all-MiniLM-L6-v2` by default (downloads ~90 MB on first use)
- LLM is still required — use OpenAI, Groq (free tier available), or a local model via Ollama

To install the extra dependencies for Local RAG:

```bash
# Step 1 — chromadb (install without its default embedding engine,
# which requires onnxruntime — not yet available for Python 3.13+)
pip install chromadb --no-deps

# Step 2 — LlamaIndex + sentence-transformers
pip install -r requirements-local.txt
```

> **Python 3.12 or earlier?** You can skip `--no-deps` and just run `pip install chromadb && pip install -r requirements-local.txt`. The two-step method works on all versions.

---

## LLM Options (for Local RAG mode)

| Provider | Setup | Notes |
|----------|-------|-------|
| **OpenAI** | Add key in Settings | Default — works out of the box |
| **Groq** | Add key in Settings | Free tier, very fast — [get a key](https://console.groq.com) |
| **Ollama** | Run locally | Fully offline — see below |

### Using Ollama (fully offline)

1. Download Ollama from [ollama.com](https://ollama.com)
2. Pull a model: `ollama pull llama3`
3. Start the server: `ollama serve`
4. In AI Blueprint: Settings → Local LLM Provider → Ollama

---

## Settings Reference

All settings are saved in the app — nothing to configure in files.

| Setting | Where | Description |
|---------|-------|-------------|
| API Keys | Settings → API Keys | OpenAI, Groq, and other provider keys (AES-256 encrypted at rest) |
| RAG Provider | Settings → RAG Provider | OpenAI or Local |
| Chat Model | Settings → Model | GPT-4o, GPT-4-turbo, etc. |
| Temperature | Settings → Model | Response creativity (0 = factual, 1 = creative) |
| Max Tokens | Settings → Model | Maximum response length |
| Top K | Settings → RAG | Number of document chunks retrieved per query |
| Similarity Threshold | Settings → RAG | Minimum relevance score to include a chunk |
| Chunk Size / Overlap | Settings → RAG | Controls how documents are split |
| Response Language | Settings → Chat | Language for all responses |
| Auto-detect Language | Settings → Chat | Detects the language of your question and replies in kind |
| Response Length | Settings → Chat | Concise / Balanced / Detailed |
| Dark Mode | Settings → Appearance | Toggle dark/light theme |
| Font Size | Settings → Appearance | 13px to 18px |

---

## Project Structure

```
ai-blueprint/
├── main.py                  # FastAPI entry point
├── database.py              # SQLite + AES-256 encrypted settings
├── rag/
│   ├── base.py              # Abstract RAG provider interface
│   ├── openai_rag.py        # OpenAI Files API + Assistants
│   └── llamaindex_rag.py    # LlamaIndex + ChromaDB (local)
├── routes/
│   ├── documents.py         # Upload, list, delete documents
│   ├── chats.py             # Create chats, stream responses (SSE)
│   └── settings.py          # Read and write all settings
├── public/
│   └── index.html           # Single-page frontend (no build step)
├── uploads/                 # Uploaded files (auto-created)
├── chroma_db/               # ChromaDB vector store (auto-created, local mode only)
├── requirements.txt
└── README.md
```

---

## Security

- API keys are encrypted with **AES-256-GCM** before being written to the database
- The encryption key is generated on first run and stored in `.secret_key` (local file, never committed)
- No keys are ever returned in plain text by the API — they are masked as `••••••••` in all responses
- All data stays on your machine (Local RAG mode) or goes only to your own OpenAI account (OpenAI mode)

---

## Supported Languages

English, Hindi, Arabic, Spanish, French, German, Portuguese, Japanese, Chinese (Simplified), Chinese (Traditional), Korean, Italian, Dutch, Russian, Turkish, Polish, Swedish, Indonesian, Malay, Bengali, Tamil, Urdu, Vietnamese, Thai, Greek, Hebrew, Swahili

Change the response language at any time in **Settings → Chat Preferences**, or enable auto-detect to match whatever language you write in.

---

## Troubleshooting

**Port 8000 is already in use**
```bash
# Run on a different port
uvicorn main:app --host 0.0.0.0 --port 8080
```
Then open http://localhost:8080.

**`pip install` fails on macOS with Homebrew Python**

Use a virtual environment (the Quick Start instructions above already do this). If you skipped it:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Local RAG: "No module named chromadb"**

The local RAG dependencies are in a separate file to avoid pip resolution issues. Run:
```bash
pip install -r requirements-local.txt
```

**Ollama: "Ollama is not running"**

Make sure the Ollama server is running before sending a message:
```bash
ollama serve
```

**First-time embedding model download is slow**

When you switch to Local RAG for the first time, `all-MiniLM-L6-v2` (~90 MB) downloads automatically. This only happens once.

---

## License

MIT
