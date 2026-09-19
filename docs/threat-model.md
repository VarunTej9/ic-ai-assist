# IC AI Assist - Initial Threat Model

| Threat | Impact | Control |
|---|---|---|
| Sensitive data is added accidentally | High | Use synthetic data only |
| AI produces an incorrect answer | Medium | Display evidence and uncertainty |
| AI invents evidence | High | Require source IDs for every answer |
| Prompt injection in a document | Medium | Treat documents as untrusted content |
| Unauthorized local access | Medium | Do not expose the app publicly |
| Secrets committed to Git | High | Use `.env` and `.gitignore` |
| AI modifies data | High | No write endpoints |
| Excessive model usage | Low | Add request limits |
| Malicious file upload | Medium | Use fixed local sample files initially |
| Incorrect anomaly classification | Medium | Use neutral wording such as “unusual” |

## Security rules

- Never use real client data.
- Never use InvestCloud credentials.
- Never commit API keys.
- Never connect to production systems.
- Do not allow shell commands from the AI.
- Do not allow automatic database updates.
- Log only synthetic identifiers.
- Keep the application local during development.

## Residual risks

The model can still produce incorrect or incomplete answers. The application must clearly communicate that AI output is advisory and requires human review.
