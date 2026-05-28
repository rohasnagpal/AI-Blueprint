# Councils

Councils are multi-agent workflows. They let multiple AI agents work through an objective in phases, retrieve evidence, produce outputs, and synthesize analysis.

AI Blueprint has both a legacy Councils area and an AI Council blueprint plugin. The legacy area is useful for reusable council templates and standalone council runs. The blueprint plugin is better when council work should belong to a workspace, matter, or blueprint.

## Where to Find Councils

Open **Councils** from the sidebar.

The Councils area includes:

- Runs
- Templates
- Builder

## Council Templates

Templates define the structure of a council.

A template may include:

- Name
- Description
- Objective prompt
- Agents
- Phases
- Retrieval settings
- Output format

Use templates for repeatable workflows such as arbitration analysis, partner review, litigation strategy, settlement analysis, and evidence review.

## Agents

Agents are role-specific AI participants. Each agent can have:

- Name
- Instructions
- Provider and model
- Temperature
- Token limit
- Context access
- Output type
- Citation requirements

Good councils use distinct agents with clear roles rather than many agents with overlapping instructions.

## Phases

Phases control the order of analysis. A phase can run one or more agents and can use previous outputs.

Examples:

- Evidence retrieval
- Claimant position
- Respondent position
- Weakness review
- Procedural risk
- Synthesis

## Running a Council

To run a council:

1. Open Councils.
2. Choose or create a template.
3. Enter the objective.
4. Choose document context if needed.
5. Create or start the run.
6. Review phase outputs and evidence.

## Council Evidence

Council phases can retrieve document evidence. Evidence should be reviewed for relevance and completeness.

If evidence is missing, narrow or improve the objective, upload documents, or choose the correct document context.

## When to Use Councils

Use councils when one perspective is not enough:

- Arbitration preparation
- Litigation strategy
- Mediation strategy
- Settlement evaluation
- Contract negotiation strategy
- Due diligence review
- Internal partner review

Use regular chat for simple questions. Use a blueprint plugin when the work should be tied to a matter or workflow.
