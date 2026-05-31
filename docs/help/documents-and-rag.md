# Documents and RAG

RAG means retrieval-augmented generation. In AI Blueprint, RAG lets Chat, Voice, Contract Review, Draft, Email, and Prep workflows search uploaded and indexed documents and use relevant excerpts as context.

## Uploading and Connecting Documents

Add documents into the correct workspace and, when appropriate, the correct matter. Supported file types include PDF, DOCX, TXT, CSV, XLSX, Markdown, JSON, HTML, and HTM.

Documents can come from:

- Direct file upload.
- Webpage URL ingestion.
- Browser-selected folder sync.
- Local folder connection where the deployment can read the path.

Use clear filenames. Good filenames improve human review and source tracing:

- `Claim Statement - 2026-02-14.pdf`
- `Respondent Email Bundle - March 2026.pdf`
- `Master Services Agreement - Signed.pdf`

## Indexing

After upload or ingestion, documents must be indexed before document search can find them. If a document is still processing, failed, cancelled, or not indexed, it may not appear in document-grounded results.

For best results:

- Upload readable PDFs or text-based documents where possible.
- Avoid scanned images unless OCR is available before upload.
- Split very large bundles if they contain unrelated material.
- Keep matter documents in the correct matter.

## Scope

Document answers depend on scope. Common scopes are:

- Workspace: search indexed documents in the selected workspace.
- Matter: search indexed documents assigned to one matter.
- Selected documents: search only specific selected files.
- Workflow selection: search documents selected for Contract Review, Draft, Email, or Prep.

If the assistant gives weak answers, confirm that the right workspace, matter, and document selection are active.

## Chat With Documents

To ask document-grounded questions:

1. Open Chat.
2. Switch the composer from General to Documents.
3. Select the relevant workspace, matter, or documents.
4. Ask a specific question.

Good examples:

- "What deadlines are mentioned in the selected documents?"
- "Find clauses dealing with termination for convenience."
- "Summarize the evidence supporting breach."
- "List contradictions between the claim statement and emails."

## Voice With Documents

To use document search in voice:

1. Set the composer to Documents mode.
2. Confirm the current scope is correct.
3. Start live voice.
4. Ask a document-grounded question.

Voice will call document search when the spoken question is about uploaded files, workspace knowledge, matters, contracts, clauses, or document-grounded facts.

If the composer is in General mode, voice should not search documents.

## Workflows With Documents

Contract Review and Prep workflows list indexed documents for the selected matter. If documents are missing from those selectors:

- Confirm the correct workspace is selected.
- Confirm the correct matter is selected.
- Confirm documents are indexed.
- Confirm the documents belong to that matter.

Draft and Email can also use selected document context. Use only relevant sources to reduce unsupported or generic output.

## Common RAG Problems

If the answer says no matching context was found:

- Check the composer or workflow is using document context.
- Check documents are indexed.
- Check the active workspace and matter are correct.
- Ask a more specific question using names, dates, clauses, parties, or topics.

If the answer cites the wrong material:

- Narrow the scope to a matter or selected documents.
- Use clearer filenames.
- Separate unrelated bundles.

If the answer is too generic:

- Ask for exact excerpts, clauses, dates, parties, obligations, or evidence references.
- Use a legal persona or the relevant Prep or Contract Review workflow.
