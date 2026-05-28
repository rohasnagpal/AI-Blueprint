# Email

AI Blueprint includes an Email area for checking incoming mail, generating AI-assisted draft replies, reviewing those drafts, and sending approved replies.

## What the Email Feature Does

The Email feature can:

- Connect to an IMAP inbox.
- Poll unread messages.
- Store imported messages in AI Blueprint.
- Generate professional draft replies.
- Use a selected persona for drafting style.
- Use selected document context when drafting replies.
- Let a human review and edit the draft.
- Send an approved reply through SMTP.
- Delete imported email records from the app.

The Email feature is designed for assisted drafting and review. It should not send replies without human approval.

## Where to Find Email

Open the sidebar More menu and choose **Email**.

The Email screen contains:

- Email settings.
- A check/poll action for incoming mail.
- A list of imported messages.
- Persona and document context controls for drafting.
- A draft text area.
- Generate Draft, Send Approved Reply, and Delete actions.

## Email Settings

Configure email settings before polling or sending.

Incoming mail uses IMAP:

- IMAP host
- IMAP port, usually `993`
- IMAP username
- IMAP password
- IMAP folder, usually `INBOX`

Outgoing mail uses SMTP:

- SMTP host
- SMTP port, default may be `2525`
- SMTP TLS verification setting
- SMTP username
- SMTP password
- From address

AI drafting settings:

- Email persona
- Email document context

The app stores email passwords as secret settings. Do not share screenshots or logs containing credentials.

## Checking Email

To import unread messages:

1. Open Email.
2. Confirm IMAP settings are saved.
3. Click the email check or poll control.
4. AI Blueprint imports recent unread messages from the configured IMAP folder.

The app imports up to a recent set of unread messages and avoids duplicate imports using message IDs.

## Generating a Draft Reply

To draft a reply:

1. Open Email.
2. Find the imported message.
3. Choose the persona if needed.
4. Choose the RAG/document scope if the reply should use uploaded documents.
5. Add drafting instructions if the UI provides an instruction field.
6. Click **Generate Draft**.
7. Review the generated draft in the draft text area.

The draft generator is instructed to:

- Draft a professional email reply.
- Avoid inventing facts.
- Flag anything that needs human approval.
- Return only the email body.

## Using Documents With Email Drafts

Email drafts can use document context. This is useful when replying based on contracts, case files, matter documents, policies, research, or prior correspondence.

Use document context when:

- The email asks a factual question answered by uploaded documents.
- The reply should cite or rely on matter materials.
- The email concerns a contract clause, deadline, obligation, or evidence item.

Do not use document context when:

- The reply is purely administrative.
- No uploaded documents are relevant.
- The document scope is uncertain.

If the draft seems unsupported, narrow the document scope or upload the missing source documents.

## Sending a Reply

Sending requires human approval.

To send:

1. Generate or write a draft.
2. Review and edit the draft.
3. Confirm SMTP settings are saved.
4. Click **Send Approved Reply**.

The backend requires an explicit approval flag before sending. If the draft is empty or SMTP settings are missing, sending fails.

## Common Email Questions

If no messages import:

- Check IMAP host, port, username, password, and folder.
- Confirm there are unread messages.
- Confirm the provider allows IMAP access.

If sending fails:

- Check SMTP host, port, username, password, TLS setting, and from address.
- Confirm the provider allows SMTP sending.
- Check whether the provider requires an app password.

If the draft is weak:

- Select a better persona.
- Add drafting instructions.
- Use document context if the answer depends on documents.
- Review the incoming email for missing facts.

If the draft invents facts:

- Do not send it.
- Add explicit instructions.
- Narrow or remove document context.
- Provide the missing facts manually.

## Safety

Always review drafts before sending. Check tone, recipients, privilege, confidentiality, factual accuracy, client instructions, attachments, deadlines, and legal implications.
