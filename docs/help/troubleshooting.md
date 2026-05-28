# Troubleshooting

## Voice Button Is Missing or Looks Blank

Refresh the page. Static JS/CSS assets may be cached. If the server was recently updated, restart the backend and refresh again.

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
- The active workspace, matter, blueprint, or selected documents are correct.
- Documents are indexed.
- The spoken question clearly asks about uploaded documents or document-grounded facts.

If the composer is in General mode, voice should not search documents.

## Typed Chat Uses Groq but Voice Still Needs OpenAI

This is expected. Typed chat uses the Chat Model provider in Settings. Live voice uses OpenAI Realtime.

## No Documents Found

Check:

- Documents were uploaded to the correct workspace or matter.
- Documents are indexed.
- The blueprint belongs to the same matter as the documents.
- The document scope is not accidentally narrowed to unrelated files.

## Contract Review Has No Source Documents

Confirm:

- Documents are uploaded.
- Documents are indexed.
- Documents match the blueprint matter.
- You selected the correct source documents in New review and settings.

## Legal Research Output Is Too Vague

Improve the question:

- Add jurisdiction.
- Add legal issue.
- Add factual setting.
- Ask for legal tests, authorities, limitations, and adverse points.

## AI Council Output Is Too Generic

Improve the objective and council design:

- Add specific roles.
- Add phases.
- Use Documents mode or attach relevant documents.
- Ask for issue maps, evidence matrices, risks, and next steps.

## Chat or Workflow Fails With Missing Key

Open Settings and add the provider API key for the selected provider. Confirm the selected model belongs to that provider.

## Email Does Not Import Messages

Check IMAP host, port, username, password, and folder. Confirm the mailbox has unread messages and the email provider allows IMAP access. Some providers require app-specific passwords.

## Email Draft Generation Fails

Check that the selected chat model provider has a configured API key. If the draft uses document context, confirm the selected documents are indexed and the RAG scope is correct.

## Email Sending Fails

Check SMTP host, port, username, password, TLS setting, and from address. Confirm the email provider allows SMTP sending and does not require a separate app password.

## Translation Fails

Check that a target language is selected, source text or one supported upload is provided, and the configured chat model provider has a working API key. For uploaded files, confirm the file type is supported.

## Connected Folder Sync Fails

Check that the folder path exists, the app has permission to read it, and the files are supported. Reconnect the folder if the path changed.

## Persona Does Not Affect Voice

Stop the current voice session and start a new one after changing persona. Voice reads the selected persona only when the Realtime session starts.

## Council Output Is Missing Evidence

Check that the council run has document context, documents are indexed, and the objective includes searchable facts or issues.

## Output Should Not Be Used Directly

AI Blueprint outputs require professional review. Verify facts, citations, legal authorities, deadlines, procedural rules, privilege issues, and client instructions before external use.
