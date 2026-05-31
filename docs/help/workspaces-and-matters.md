# Workspaces and Matters

Workspaces and matters organize access, documents, workflow runs, and legal work product.

## Workspaces

A workspace is the top-level container for a user, firm, team, department, client group, or project. It contains matters, documents, settings, personas, runs, and members.

Use separate workspaces when:

- Access should be separated.
- Different teams or clients should not share documents.
- Different model or RAG settings are needed.
- A deployment needs clear administrative boundaries.

## Workspace Selection

Most major screens include a workspace selector or inherit the active workspace:

- Chat document scope
- Add Document
- View Documents
- Contract Review
- Arbitration, Litigation, Mediation, and Negotiation Prep
- Draft
- Email document context
- Translate history and workspace outputs where applicable
- Settings administration tabs

Changing the workspace changes the available matters, documents, and run history. If expected documents or runs are missing, check the selected workspace first.

## Matters

A matter groups documents and workflows for a specific client, dispute, transaction, research project, or legal file.

Use matters to keep related material together:

- Client dispute
- Arbitration
- Litigation
- Mediation
- Contract negotiation
- Regulatory question
- Research assignment
- Due diligence review

## Creating a Matter

To create a matter:

1. Open **Settings**.
2. Open the **Matters** tab if it is visible for your role.
3. Select the workspace.
4. Enter the matter name.
5. Add the client name and description if useful.
6. Create the matter.

If the Matters tab is not visible, the current user may not have the required workspace or admin permissions.

## Using Matters in Workflows

Select the matter before uploading documents or running a workflow. Contract Review and Prep workflows require the selected source documents to belong to the selected matter.

Matter selection affects:

- Which source documents are listed.
- Which documents are searched in Documents mode.
- Which run history is shown.
- Whether workflow APIs accept the selected documents.

## Matter Status

Matters can be active or closed. Status helps users understand whether the matter is ongoing.

## Deleting a Matter

Deleting a matter can affect linked documents and workflow history. Review the matter before deleting it, especially if it has indexed documents or completed runs.

## Best Practices

- Create the matter before uploading documents.
- Upload documents to the correct matter.
- Run Contract Review and Prep workflows inside the matching matter.
- Use clear matter names that include client, opposing party, transaction, or project.
- Keep unrelated client files in separate matters.
