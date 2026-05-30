# Contract Review Blueprint

The Contract Review blueprint analyzes contracts against a review mode, selected documents, and optional playbooks.

## When to Use It

Use Contract Review for:

- Master services agreements
- NDAs
- Vendor contracts
- Customer contracts
- Employment or consultant agreements
- License agreements
- Amendments and addenda
- Commercial terms documents

Do not force the workflow on documents that are not contracts. If the document is a pleading, email chain, memo, or evidence bundle, use Chat, AI Council, or Legal Research instead.

## Before Running

Prepare:

- The contract document.
- Relevant schedules, amendments, side letters, or exhibits.
- The correct matter.
- Any internal playbook or fallback language.
- The desired risk tolerance.
- The jurisdiction if important.

Make sure the source documents are indexed.

## Review Modes

Structured workflow is better when users want extracted clauses, risk findings, redline suggestions, playbook comparison, escalation review, summaries, and a human review screen.

## Playbooks

Playbooks define expected clause positions, required clauses, prohibited patterns, approved text, fallback text, and default severity.

Use Auto-select playbook when unsure. Select a specific playbook when reviewing a known contract type or workspace standard.

Workspace users can create playbooks with:

- Name
- Contract category
- Jurisdiction
- Version
- Rules
- Clauses

Built-in playbooks should be treated as starting points, not final firm policy.

## Starting a Run

1. Open the Contract Review blueprint.
2. Expand New review and settings.
3. Enter a run title.
4. Choose review mode.
5. Choose a playbook or Auto-select.
6. Select source documents.
7. Run Contract Review.

## Reviewing Outputs

Structured review may include:

- Clause extraction
- Playbook findings
- Risk findings
- Redline suggestions
- Client summary
- Negotiation points
- Escalations
- Audit JSON

Use Open Review to inspect clauses and decisions. Use Audit JSON when you need a machine-readable trace of the run.

## Human Review

The workflow supports human review decisions. Users should confirm important findings, especially high-risk items, missing clauses, unusual terms, and proposed fallback language.

## Common Problems

If no source documents are selectable:

- Upload documents.
- Confirm they are indexed.
- Confirm they belong to the same matter as the blueprint.

If the review is too generic:

- Select the right playbook.
- Add jurisdiction.
- Narrow source documents.
- Use Structured workflow.

If the review misses clauses:

- Check document quality.
- Check whether clauses are in schedules or exhibits.
- Upload all amendments and referenced attachments.
