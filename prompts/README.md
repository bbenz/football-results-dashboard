# Prompts

This folder holds the generation prompt used to build this repository with a coding agent.

| Prompt | What it does |
| --- | --- |
| [demopromptv1.md](demopromptv1.md) | The complete requirements for this demo, written for a coding agent. It defines the seven questions, the rule that deterministic code owns every number, the no-data rule, the Azure proof of concept on AKS and ACA, the 60-minute run of show, and the checks the finished repository must pass. The agent works through it in gated phases, stopping for the presenter's decisions. |

The prompt is a generation prompt, not the livestream script: the script is [docs/ONSTAGE-SCRIPT.md](../docs/ONSTAGE-SCRIPT.md), and the run of show is [docs/RUNBOOK.md](../docs/RUNBOOK.md).

The presenter's session information, proof-of-concept notes, and evidence are kept outside this repository, and nothing here depends on them. To adapt the prompt for your own talk or project, replace the session details, names, and paths with your own.
