# Security Policy

## Supported Versions

The `main` branch is the supported development line.

## Reporting a Vulnerability

Please do not open a public issue for suspected security vulnerabilities.

Use GitHub's private vulnerability reporting feature if it is enabled for this repository. If it is not enabled, contact the repository owner directly and include:

- A clear description of the issue
- Steps to reproduce
- Impact assessment
- Any relevant logs, screenshots, or proof of concept

## Security Expectations

AI Blueprint stores API keys encrypted at rest and keeps local runtime data out of version control. Contributions must not commit secrets, local databases, uploaded documents, ChromaDB data, or other private user data.

For public deployments:

- Use HTTPS and set `AI_BLUEPRINT_SECURE_COOKIES=true`.
- Set `AI_BLUEPRINT_CORS_ORIGINS` to the production origin, not a wildcard.
- Keep `AI_BLUEPRINT_BOOTSTRAP_DEFAULT_ADMIN` disabled.
- Store database files, upload directories, vector indexes, and secret keys outside the repository and outside the web root.
- Keep reverse-proxy upload limits aligned with `AI_BLUEPRINT_MAX_UPLOAD_BYTES`.
- Review logs to ensure document text, prompts, and secret values are not written to shared log systems.
