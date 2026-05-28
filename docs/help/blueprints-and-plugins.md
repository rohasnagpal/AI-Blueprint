# Blueprints and Plugins

Blueprints turn repeatable legal work into structured workflows. A blueprint is created from a plugin. The current blueprint plugins are Contract Review, AI Council, and Legal Research.

## Enable a Plugin

To use a plugin in a workspace:

1. Sign in.
2. Open Plugins.
3. Select the workspace.
4. Enable the plugin needed for that workspace.

If a plugin is not enabled, it may not appear as a blueprint option.

## Create a Blueprint

To create a blueprint:

1. Open Blueprints.
2. Select the workspace.
3. Choose the matter filter if relevant.
4. Enter a blueprint name.
5. Select the plugin.
6. Choose the matter if the workflow belongs to a matter.
7. Add an optional description.
8. Create the blueprint.

Use clear blueprint names:

- `ABC v XYZ - Arbitration Prep`
- `Vendor MSA Review`
- `Limitation Research - Consumer Claim`

## Open a Blueprint

Open a blueprint from the Blueprints list. The blueprint workspace shows plugin configuration, new run fields, previous runs, exports, and plugin-specific review screens.

Many blueprint cards also include a Chat button. Blueprint chat opens chat with the active blueprint as context so document search can be limited to that blueprint.

## Blueprint Scope

Blueprint scope matters. Documents and outputs should usually stay within the same matter. If a blueprint belongs to a matter, use matter documents or blueprint-linked documents that match the matter.

## Plugin Configuration

Each plugin has a JSON configuration area. Users can keep defaults or edit configuration when they understand the plugin schema.

Common defaults:

- Contract Review: review standard, jurisdiction, risk tolerance, and mode.
- AI Council: agents, phases, instructions, and retrieval query.
- Legal Research: jurisdiction, memo format, and whether authorities are required.

Do not edit plugin JSON casually. Invalid configuration can produce weak or failed runs.

## New Runs

A run is a single execution of a blueprint. Runs may take time. Watch the run status and progress indicator.

After completion, review outputs before relying on them. Legal outputs should be treated as drafts and analysis aids, not final professional judgment.

## Exports

Most blueprint runs can be exported. Exports are useful for work papers, client updates, internal review, and audit packages.

Do not send exported work product externally without lawyer review.
