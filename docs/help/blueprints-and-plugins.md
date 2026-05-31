# Blueprints and Plugins

The current AI Blueprint UI uses direct screens instead of asking users to create blueprint instances manually. The visible workflow areas are:

- **Prep**: Arbitration Prep, Litigation Prep, Mediation Prep, Negotiation Prep.
- **Workflows**: Contract Review, Draft, Email, Translate.

Older versions exposed **Blueprints** and **Plugins** as primary screens. Some backend records still use plugin and blueprint tables so workflow runs can be persisted, audited, and related to matters. In normal use, users do not need to create or configure blueprint records directly.

## Current User Workflow

To run a structured workflow:

1. Open the relevant Prep or Workflow screen.
2. Select the workspace.
3. Select the matter when the workflow requires one.
4. Select indexed source documents if the workflow uses documents.
5. Fill in the structured fields.
6. Run the workflow.
7. Review the output, source list, warnings, and history.

## Prep Screens

Prep workflows produce structured preparation packages from indexed matter documents:

- Arbitration Prep
- Litigation Prep
- Mediation Prep
- Negotiation Prep

They persist recent runs and expose copy and Markdown download actions.

## Workflow Screens

Contract Review analyzes indexed contracts using review depth, playbooks, selected documents, and instructions.

Draft generates legal work product from structured inputs and optional source documents.

Email imports unread messages through IMAP, drafts replies, and sends approved replies through SMTP.

Translate translates pasted text or one uploaded document into HTML output with notes and warnings.

## Hidden Blueprint Records

When a Prep workflow runs, the backend may create or reuse a hidden system blueprint for that matter and workflow type. This is an implementation detail used for persistence and auditability.

Users should manage work from the visible Prep and Workflow screens, not by editing hidden blueprint records.

## Legacy References

If older documentation, exports, or database records mention AI Council, Legal Research, blueprint instances, plugin enablement, or blueprint membership, treat those as legacy concepts unless a current screen exposes them.

For current structured multi-role analysis, use the Prep workflows and Documents mode in Chat.
