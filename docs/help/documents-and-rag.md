# Documents and RAG

RAG means retrieval-augmented generation. In AI Blueprint, RAG lets chat, voice, and workflows search uploaded documents and use relevant excerpts as context.

## Uploading Documents

Upload documents into the correct workspace and, when appropriate, the correct matter. For blueprint-specific work, link or select documents that belong to the same matter or blueprint.

Use clear filenames. Good filenames improve human review and citations:

- `Claim Statement - 2026-02-14.pdf`
- `Respondent Email Bundle - March 2026.pdf`
- `Master Services Agreement - Signed.pdf`

## Indexing

After upload, documents must be indexed before document search can find them. If a document is still processing, failed, or not indexed, it may not appear in document-grounded results.

For best results:

- Upload readable PDFs or text-based documents where possible.
- Avoid scanned images unless OCR is available in the pipeline.
- Split very large bundles if they contain unrelated material.
- Keep matter documents in the correct matter.

## Scope

Document answers depend on scope. The common scopes are:

- Workspace: search all indexed workspace documents.
- Matter: search documents assigned to one matter.
- Blueprint: search documents linked to or relevant for one blueprint.
- Selected documents: search only specific selected files.

If the assistant gives weak answers, confirm that the right scope is active.

## Chat With Documents

To ask document-grounded questions:

1. Open Chat.
2. Switch the composer from General to Documents.
3. Select the relevant workspace, matter, blueprint, or documents.
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

Voice will call document search when the spoken question is about uploaded files, workspace knowledge, matters, blueprints, contracts, clauses, or document-grounded facts.

If the composer is in General mode, voice should not search documents.

## Common RAG Problems

If the answer says no matching context was found:

- Check the composer is in Documents mode.
- Check documents are indexed.
- Check the active workspace/matter/blueprint is correct.
- Ask a more specific question using names, dates, clauses, parties, or topics.

If the answer cites the wrong material:

- Narrow the scope to a matter, blueprint, or selected documents.
- Use clearer filenames.
- Separate unrelated bundles.

If the answer is too generic:

- Ask for exact excerpts, clauses, dates, parties, obligations, or evidence references.
- Use a legal persona or relevant blueprint workflow.
