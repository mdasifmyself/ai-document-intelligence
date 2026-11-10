"""Builds and deploys the n8n "AI Gateway" workflow used by DocIntel.

Why a gateway: the OpenAI key stays inside n8n's credential store. The DocIntel worker never
holds it; it calls one authenticated webhook, and n8n forwards an allow-listed request to OpenAI.

    python3 n8n/build_gateway.py            # create or update by name, then activate
    python3 n8n/build_gateway.py --export   # also write the shareable export (no ids, no secrets)

Reads from ~/.config/docintel/ (never committed):
    n8n_url, n8n_api_key, openai_credential.json ({"id": "...", "name": "..."})
Writes ~/.config/docintel/gateway_key (the header secret the worker must send) on first run.
"""
import json, pathlib, secrets, sys, urllib.error, urllib.request, uuid

ROOT = pathlib.Path(__file__).resolve().parent
CFG = pathlib.Path.home() / ".config/docintel"
NAME = "DEMO DocIntel | AI Gateway"
PATH = "docintel/ai"
HEADER = "X-DocIntel-Key"


def cfg(name):
    return (CFG / name).read_text().strip()


def api(method, path, body=None):
    req = urllib.request.Request(cfg("n8n_url") + "/api/v1" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-N8N-API-KEY": cfg("n8n_api_key"), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read()
            return json.loads(t) if t else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"n8n API {method} {path} -> {e.code}: {e.read().decode()[:400]}")


def find_workflow(name):
    cursor = None
    while True:
        d = api("GET", "/workflows?limit=100" + (f"&cursor={cursor}" if cursor else ""))
        for w in d["data"]:
            if w["name"] == name:
                return w
        cursor = d.get("nextCursor")
        if not cursor:
            return None


def header_credential():
    f = CFG / "gateway_cred.json"
    if f.exists():
        return json.loads(f.read_text())
    key = secrets.token_urlsafe(32)
    (CFG / "gateway_key").write_text(key)
    (CFG / "gateway_key").chmod(0o600)
    c = api("POST", "/credentials", {"name": "DocIntel | gateway key", "type": "httpHeaderAuth",
                                     "data": {"name": HEADER, "value": key}})
    ref = {"id": c["id"], "name": c["name"]}
    f.write_text(json.dumps(ref))
    f.chmod(0o600)
    return ref


CHECK_JS = r"""
// Allow-list: only these OpenAI endpoints can be reached through the gateway.
const ALLOWED = { responses: 'https://api.openai.com/v1/responses',
                  embeddings: 'https://api.openai.com/v1/embeddings' };
const MAX_BYTES = 6 * 1024 * 1024;   // page images for the vision fallback are sent as base64
const b = $json.body || {};
const op = String(b.op || '');
if (!ALLOWED[op]) return [{ json: { ok: false, status: 400, error: 'unknown op' } }];
if (!b.payload || typeof b.payload !== 'object') return [{ json: { ok: false, status: 400, error: 'payload missing' } }];
const size = JSON.stringify(b.payload).length;
if (size > MAX_BYTES) return [{ json: { ok: false, status: 413, error: 'payload too large' } }];
const payload = { ...b.payload };
if (op === 'responses') payload.store = false;      // never keep document text at OpenAI
return [{ json: { ok: true, url: ALLOWED[op], payload } }];
"""


def node(name, type_, pos, params, version=1, **extra):
    return {"id": str(uuid.uuid4()), "name": name, "type": type_, "typeVersion": version,
            "position": pos, "parameters": params, **extra}


def respond(name, body, code, pos):
    return node(name, "n8n-nodes-base.respondToWebhook", pos,
                {"respondWith": "json", "responseBody": body, "options": {"responseCode": code}}, 1.1)


def sticky(title, body, pos, w, h):
    return node(f"Note: {title}", "n8n-nodes-base.stickyNote", pos,
                {"content": f"## {title}\n{body}", "width": w, "height": h})


def build(hook_cred, openai_cred):
    y = 300
    nodes = [
        node("Webhook", "n8n-nodes-base.webhook", [0, y],
             {"httpMethod": "POST", "path": PATH, "authentication": "headerAuth",
              "responseMode": "responseNode", "options": {}}, 2,
             webhookId="4f1d9a2e-6c3b-4d8e-9b1a-d0c1e2f3a4b5",
             credentials={"httpHeaderAuth": hook_cred}),
        node("Check request", "n8n-nodes-base.code", [220, y], {"jsCode": CHECK_JS}, 2),
        node("Allowed?", "n8n-nodes-base.if", [440, y], {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.ok }}", "rightValue": "",
                            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
            "combinator": "and"}, "options": {}}, 2.2),
        node("Call OpenAI", "n8n-nodes-base.httpRequest", [680, y - 20],
             {"method": "POST", "url": "={{ $json.url }}",
              "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi",
              "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.payload) }}",
              "options": {"timeout": 110000}}, 4.2,
             onError="continueErrorOutput", credentials={"openAiApi": openai_cred}),
        respond("Reply: result", "={{ JSON.stringify($json) }}", 200, [920, y - 120]),
        respond("Reply: upstream error",
                "={{ JSON.stringify({ ok: false, error: 'upstream', detail: String($json.error && ($json.error.message || $json.error)).slice(0, 400) }) }}",
                502, [920, y + 80]),
        respond("Reply: rejected", "={{ JSON.stringify({ ok: false, error: $json.error }) }}", 400, [680, y + 220]),
        sticky("DocIntel AI Gateway",
               "Keeps the OpenAI key inside n8n. The DocIntel worker sends `{op, payload}` with the "
               f"`{HEADER}` header.\n\n**Allowed ops:** `responses` (extraction, vision fallback), `embeddings` "
               "(semantic search).\n**Privacy:** `store:false` is forced; successful and failed executions are "
               "not saved, so no document text stays in n8n.", [-40, -40], 620, 260),
    ]
    c = lambda a, b, i=0: (a, b, i)
    links = [c("Webhook", "Check request"), c("Check request", "Allowed?"), c("Allowed?", "Call OpenAI"),
             c("Allowed?", "Reply: rejected", 1), c("Call OpenAI", "Reply: result"),
             c("Call OpenAI", "Reply: upstream error", 1)]
    connections = {}
    for a, b, i in links:
        outs = connections.setdefault(a, {"main": []})["main"]
        while len(outs) <= i:
            outs.append([])
        outs[i].append({"node": b, "type": "main", "index": 0})
    return {"name": NAME, "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none",
                         "saveDataErrorExecution": "none", "saveManualExecutions": False,
                         "executionTimeout": 150}}


def export(wf):
    clean = json.loads(json.dumps(wf))
    for n in clean["nodes"]:
        for k in n.get("credentials", {}):
            n["credentials"][k] = {"id": "REPLACE_ME", "name": f"<your {k} credential>"}
    out = ROOT / "ai-gateway.workflow.json"
    out.write_text(json.dumps(clean, indent=2) + "\n")
    print("exported", out.relative_to(ROOT.parent))


def main():
    openai_cred = json.loads(cfg("openai_credential.json"))
    wf = build(header_credential(), openai_cred)
    existing = find_workflow(NAME)
    if existing:
        api("POST", f"/workflows/{existing['id']}/deactivate")
        api("PUT", f"/workflows/{existing['id']}", wf)
        wid = existing["id"]
    else:
        wid = api("POST", "/workflows", wf)["id"]
    api("POST", f"/workflows/{wid}/activate")
    (CFG / "gateway_url").write_text(cfg("n8n_url") + "/webhook/" + PATH)
    print("deployed", wid, "->", "/webhook/" + PATH)
    if "--export" in sys.argv:
        export(wf)


if __name__ == "__main__":
    main()
