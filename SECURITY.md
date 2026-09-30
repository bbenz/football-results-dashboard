# Security

## Reporting a vulnerability

Please don't report security problems in public issues. Use GitHub's private vulnerability reporting: on the repository's **Security** tab, choose **Report a vulnerability**. Include what you found, how to reproduce it, and its possible impact. You'll get an acknowledgment, and fixes will be coordinated with you before any details are published.

## What this repository does to stay secure

- **No keys or secrets.** Every Azure service authenticates with Microsoft Entra ID: workload identity on AKS, managed identities on Container Apps, and the developer's own sign-in locally. Key-based authentication is disabled on the Foundry resource, the storage account, and Application Insights, and the registry's admin user is disabled. The code has no API-key setting.
- **Least privilege.** Each service has its own identity on each platform, with only the roles it needs. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#identity-keyless-everywhere).
- **A small public surface.** Only `web` is public, and only to the addresses in `ALLOWED_CIDRS`. It sends security headers, limits requests per client, and exposes no admin, reset, or documentation endpoints. `insights` is reachable only from `web`.
- **A bounded model.** Questions are limited in length. The agent can call only read-only analytics tools, with limits on tool calls, output tokens, and time. Microsoft Foundry content filters stay on. A deterministic check rejects any number in an answer that no tool returned.
- **No data in git.** A guard fails if a data file is ever staged or committed.

## Supported versions

This is a demo, maintained on its `main` branch only. If you deploy it, keep your deployment restricted to known addresses, and tear it down when you're done (`demo teardown`).
