# Contributing to AI Blueprint

Thanks for your interest in contributing. This project is a local-first document chat app, so contributions should preserve privacy, avoid committing runtime data, and keep setup simple.

## Getting Started

1. Fork the repository and clone your fork.
2. Create a virtual environment with Python 3.10 or newer.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app:

```bash
python main.py
```

5. Open `http://localhost:8000`.

For Local RAG work, also install the dependencies in `requirements-local.txt` after following the README's ChromaDB notes.

## Development Guidelines

- Keep changes focused and easy to review.
- Do not commit `.secret_key`, `.db` files, uploaded documents, ChromaDB data, logs, or local virtual environments.
- Update `README.md` when setup steps, supported behavior, or user-facing features change.
- Prefer small, explicit changes over broad refactors.
- When changing privacy-sensitive behavior, document where data is stored or sent.

## Pull Requests

Before opening a pull request:

- Run the app locally for the workflow you changed.
- Run `python -m compileall main.py database.py routes rag`.
- Fill out the pull request template.
- Link related issues when available.

## Issues

Use the bug report template for reproducible failures and the feature request template for proposed enhancements. Open-ended support questions and ideas are better suited to GitHub Discussions.

