# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `main` | Yes |
| older commits | Best effort |

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Use GitHub Security Advisories for this repository, or contact the repository owner privately. Include:

- affected endpoint or component,
- steps to reproduce,
- potential impact,
- suggested fix if available.

The maintainers will acknowledge valid reports, investigate, and publish a fix when appropriate.

## Security Notes

- The API only reads public upstream sources.
- Do not commit Telegram session files, `.env` files, caches, OCR debug output, or local runtime data.
- Production deployments should set explicit `ALLOWED_HOSTS`, `CORS_ORIGINS`, and reverse-proxy TLS.
