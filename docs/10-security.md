# Security

| Area | What is done |
|---|---|
| Access | Every API endpoint (except `/health`, `/meta`) needs an access code (`X-Access-Code` header), compared in constant time. The web app keeps the code in the browser's session storage only (gone when the browser closes; **Lock demo** clears it at once), and a one-time `?code=` link is removed from the address bar immediately. The code is never stored in the repository. |
| Transport | HTTPS everywhere: Vercel for the web app, Traefik with Let's Encrypt certificates for the API. |
| One origin | The browser talks only to the web app's domain; Vercel forwards `/api/*` to the processing server. The server address is a Vercel secret, not in code or in the browser. |
| Uploads | File type is detected from content (magic bytes), never trusted from the name. Size limit per file (50 MB), per request (50 files, 250 MB at the proxy), page limit (1,500). Files are stored under random names; original names are only kept in the database. |
| Rate limits | Per-IP limits on uploads and sample processing (Redis, fixed window); a daily AI call budget protects cost. |
| Containers | Run as a non-root user, on private Docker networks; database and Redis are not reachable from the internet. Hard CPU and memory limits isolate the stack from other services on the same machine. |
| Secrets | Nothing secret in the repository. Server settings live in an `.env` file on the server (mode 600); the OpenAI key stays inside the n8n credential store and the worker only holds a gateway header key. |
| AI data handling | AI requests use `store: false`; the n8n gateway saves no execution data; only two OpenAI endpoints are allow-listed and the payload size is capped. |
| Integrity and audit | Every manual change is stored (old value, new value, who, when, why). Every processing stage is logged with its time. A file fingerprint (SHA-256) detects re-uploads. |
| Headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` on the web app and API. |
| Least privilege | The demo access code only grants the demo API. Production would add user accounts (SSO/OIDC), roles (uploader, reviewer, admin), per-tenant data separation and encryption at rest for stored originals. |

Handling of real personal or health data (for example HIPAA-covered documents) would additionally need a signed
business associate agreement with the AI provider, data retention rules and audit export. These are listed in
[12-limitations-and-roadmap.md](12-limitations-and-roadmap.md).
