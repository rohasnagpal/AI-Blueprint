# Drafting

The Draft feature generates legal work product from structured drafting inputs. It is useful when the user needs a document, clause, notice, letter, resolution, reply, memo, or other legal draft rather than a conversational answer.

Drafting is an assistance workflow. It produces reviewable work product with assumptions, missing information, source usage, and review warnings. A lawyer should review and revise every draft before use.

## Where to Find Draft

Open **Workflows** and choose **Draft**.

The Draft screen contains:

- Workspace and matter selectors.
- Document type, tone, jurisdiction, title, and audience fields.
- Party details.
- Facts and background.
- Key terms.
- Drafting instructions.
- Optional source document selection.
- Generate Draft and Clear actions.
- Progress, saved draft history, and output panels.

## Inputs

Important drafting inputs include:

- Document type: the kind of document to prepare, such as legal notice, SaaS agreement, board resolution, reply to show-cause notice, clause, memo, or client letter.
- Tone: formal, neutral, firm, aggressive, collaborative, client-friendly, or plain-language.
- Jurisdiction: the legal or geographic context.
- Audience: client, counterparty, court, board, regulator, internal team, or another recipient.
- Parties: names, roles, addresses, representatives, and company details.
- Facts and background: the events, dates, problem, transaction, dispute, or legal issue.
- Key terms: commercial terms, clauses, relief sought, payment terms, deadlines, or fallback positions.
- Drafting instructions: formatting preferences, clauses to include or exclude, strategy, negotiation posture, or special constraints.

Facts and background are required. Other fields improve quality and reduce placeholders.

## Source Documents

Drafting can use selected source documents from the workspace or matter. Source documents are useful when the draft should reflect:

- A contract or clause.
- Matter correspondence.
- Notices or pleadings.
- Policies, board papers, or transaction documents.
- Prior instructions or factual records.

Only select documents that are relevant to the draft. If a matter is selected, source documents should belong to that matter or workspace scope. If the source list is empty, check that documents are uploaded, indexed, and in the selected workspace or matter.

## Running a Draft

To generate a draft:

1. Open Draft from Workflows.
2. Select the workspace and matter if relevant.
3. Enter the document type.
4. Choose tone and jurisdiction.
5. Add party details, facts, key terms, and instructions.
6. Select source documents if the draft should rely on uploaded material.
7. Click **Generate Draft**.
8. Watch the progress panel.
9. Review the result, assumptions, missing information, sources, and warnings.

Workspace drafts run as jobs. The progress panel may show stages such as input reading, planning, drafting, QA/revision, rendering, and saving.

## Results

Drafting returns:

- Printable HTML.
- Plain text.
- Assumptions.
- Missing information.
- Review warnings.
- Source usage.
- Provider and model metadata when available.
- Saved draft history for workspace drafts.

The output panel supports print, copy HTML, copy text, and download HTML.

## Draft History

Signed-in workspace drafts are saved in Draft History. Use history to reopen or download prior drafts.

If a draft is not visible in history, confirm:

- The user is signed in.
- The correct workspace is selected.
- The draft job completed successfully.
- The app can reach the workspace draft API.

## When to Use Draft Instead of Chat

Use Draft when:

- The target output is a document or formal work product.
- The user has structured facts, parties, terms, and drafting instructions.
- The output needs review warnings and missing-information tracking.
- The draft should be saved in workspace history.

Use Chat when:

- The user wants an explanation, quick answer, brainstorm, or informal summary.
- The user wants to ask follow-up questions before drafting.
- The task is exploratory and not yet ready for a document.

Use Email when the output is a reply to an imported email. Use Contract Review when the core task is analyzing contract risk rather than preparing a new document. Use Prep when the core task is structured dispute, mediation, or negotiation preparation.

## Best Practices

- Give complete facts, dates, party names, amounts, deadlines, and governing law where possible.
- Use placeholders intentionally when facts are not yet known.
- Select only relevant source documents.
- Add jurisdiction and audience.
- Use Drafting instructions for strategy, tone, formatting, and clauses to include or avoid.
- Review assumptions and missing information before relying on the draft.
- Verify legal citations, statutory references, deadlines, and defined terms.

## Common Problems

If draft generation fails, check that the configured chat model provider has a working API key.

If the draft contains placeholders, add the missing facts and generate again or edit the draft manually.

If the draft invents facts, remove irrelevant source documents, add stricter instructions, and review the facts field for ambiguity.

If source documents are missing, confirm the workspace, matter, indexing status, and document scope.

If the draft is too generic, add document type, jurisdiction, audience, key terms, and drafting instructions.
