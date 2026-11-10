# AI gateway (n8n)

The workers never hold the OpenAI key. They call one n8n webhook, and n8n forwards an allow-listed request to OpenAI
using its own credential store.

```
worker ──POST {op, payload} + X-DocIntel-Key──▶ n8n webhook ──▶ Check request ──▶ OpenAI (responses | embeddings)
```

* **Allowed operations:** `responses` (extraction, image reading) and `embeddings` (semantic search). Anything else is
  rejected with 400.
* **Privacy:** `store: false` is forced on every response request; successful and failed executions are not saved in n8n.
* **Limits:** payloads over 6 MB are rejected (page images are sent as compressed JPEG).

Files:

* `ai-gateway.workflow.json`: shareable export (credential ids replaced with placeholders). Import it into n8n, attach
  an OpenAI credential and a Header Auth credential named `X-DocIntel-Key`, and activate it.
* `build_gateway.py`: creates or updates the workflow through the n8n API (reads `~/.config/docintel/`), activates it
  and stores the gateway URL and header key locally.

Then set `AI_PROVIDER=n8n`, `AI_GATEWAY_URL` and `AI_GATEWAY_KEY` for the API and workers. Without n8n, set
`AI_PROVIDER=openai` and `OPENAI_API_KEY` instead; the result is the same.
