# Troubleshooting

## A Screen Is Missing From the Sidebar

Refresh the page. Static JS/CSS assets may be cached. If the server was recently updated, restart the backend and refresh again.

The current primary navigation is New Chat, Add Document, View Documents, Prep, Workflows, Personas, and Settings. Some admin tabs are only visible to users with the required permissions.

## Live Voice Says Method Not Allowed

The backend is likely running an older version without the Realtime route. Restart the backend. The app should expose:

- `POST /api/v2/realtime/session`
- `POST /api/realtime/session`

## Live Voice Says OpenAI API Key Is Not Configured

Live voice requires an OpenAI API key because it uses OpenAI Realtime. Typed chat can use other providers such as Groq, but voice currently cannot.

## Voice Uses the Wrong Grammatical Gender

Live voice instructions tell the assistant to use feminine first-person forms in Hindi and other gendered languages. Restart voice after backend changes or persona changes.

## Voice Does Not Search Documents

Check:

- The composer is in Documents mode.
- The active workspace, matter, or selected documents are correct.
- Documents are indexed.
- The spoken question clearly asks about uploaded documents or document-grounded facts.

If the composer is in General mode, voice should not search documents.

## Typed Chat Uses One Provider but Voice Still Needs OpenAI

This is expected. Typed chat uses the Chat Model provider in Settings. Live voice uses OpenAI Realtime.

## No Documents Found

Check:

- Documents were uploaded, URL-ingested, or synced to the correct workspace or matter.
- Documents are indexed.
- The document scope is not accidentally narrowed to unrelated files.
- The selected workflow is using the same matter as the documents.

## Connected Folder Sync Fails

Check that the folder path exists, the app has permission to read it, and the files are supported. Reconnect the folder if the path changed.

For browser-selected folders, keep the folder selection active until sync completes.

## Contract Review Has No Source Documents

Confirm:

- Documents are uploaded.
- Documents are indexed.
- Documents belong to the selected matter.
- You selected the correct workspace and matter.

## Contract Review Output Is Too Generic

Improve the review:

- Select a better playbook.
- Use Detailed depth.
- Add jurisdiction, client position, negotiation posture, and clause concerns in review instructions.
- Narrow source documents to the actual contract and relevant attachments.

## Prep Workflow Has No Source Documents

Confirm:

- Documents are uploaded or synced.
- Documents are indexed.
- Documents belong to the selected matter.
- The selected workspace and matter are correct.

## Prep Output Is Too Generic

Improve the run:

- Add specific prep instructions.
- Select the right focus value.
- Add forum, court, jurisdiction, stage, and dates.
- Select documents that directly support the task.
- Ask for issue maps, evidence matrices, risks, next steps, talking points, or procedural tasks.

## Chat or Workflow Fails With Missing Key

Open Settings and add the provider API key for the selected provider. Confirm the selected model belongs to that provider.

## Email Does Not Import Messages

Check IMAP host, port, username, password, and folder. Confirm the mailbox has unread messages and the email provider allows IMAP access. Some providers require app-specific passwords.

## Email Draft Generation Fails

Check that the selected chat model provider has a configured API key. If the draft uses document context, confirm the selected documents are indexed and the RAG scope is correct.

## Email Sending Fails

Check SMTP host, port, username, password, TLS setting, and from address. Confirm the email provider allows SMTP sending and does not require a separate app password.

## Draft Generation Fails

Check that the configured chat model provider has a working API key and that the selected model is available for that provider. If source documents are selected, confirm they are indexed and belong to the selected workspace or matter.

## Draft Has Too Many Placeholders

Add missing party details, dates, amounts, addresses, deadlines, governing law, and key terms. Placeholders usually mean the model was instructed not to invent facts.

## Draft Source Documents Are Missing

Check:

- The correct workspace is selected.
- The correct matter is selected.
- Documents were uploaded, ingested, or synced successfully.
- Documents are indexed.
- The documents belong to the selected matter or workspace scope.

## Draft History Does Not Load

Confirm the user is signed in, the correct workspace is selected, and the draft job completed successfully. Refresh Draft History after generation completes.

## Translation Fails

Check that a target language is selected, source text or one supported upload is provided, and the configured chat model provider has a working API key. For uploaded files, confirm the file type is supported and the file contains extractable text.

## Translation Output Looks Incomplete

Try a smaller source text, add context, or use a more precise mode such as Legal or Literal. For scanned documents, extract text with OCR before uploading if the app cannot read the file contents.

## Persona Does Not Affect Voice

Stop the current voice session and start a new one after changing persona. Voice reads the selected persona only when the Realtime session starts.

## Output Should Not Be Used Directly

AI Blueprint outputs require professional review. Verify facts, citations, legal authorities, deadlines, procedural rules, privilege issues, confidentiality issues, and client instructions before external use.
