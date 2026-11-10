# Limitations and next steps

Honest limits of this version, and what a production rollout would add.

## Known limitations

| Limitation | Effect | Mitigation today |
|---|---|---|
| The labelled dataset is synthetic (generated invoices with planted problems) | Real-world layouts vary more; accuracy on real documents may be lower than measured | Three layouts, four currencies, scans, photos, blur, rotation, broken files; the pipeline flags uncertainty rather than guessing |
| Very poor photos can still be misread | A wrong value may be extracted | Such invoices are always flagged for review ("read from the image" / "two readings differ") |
| Invoices longer than 3 pages that are scanned get one reading (text), not two | Less cross-checking on long scanned invoices | Validation still checks all maths |
| Throughput is bounded by the AI provider's rate limit on the account used | A 1,000-page batch takes minutes, not seconds | Parallel calls inside a document; more workers; higher provider tier |
| One access code for the demo | No per-user accounts or roles | Production: SSO and roles (below) |
| OCR language: English | Other scripts (e.g. Bangla) are not OCR'd | Tesseract supports 100+ languages; add language packs |
| Currency "$" alone is read as USD | Wrong for CAD/AUD invoices without a code | Configurable rule; flag when ambiguous |

## Roadmap

1. **Accounts and roles**: SSO (OIDC), uploader / reviewer / admin roles, per-team data separation.
2. **Learning from corrections**: use approved corrections as few-shot examples per supplier, and track per-supplier
   accuracy.
3. **Supplier master data**: match suppliers to a vendor list (tax ID, bank details) and flag new or changed bank
   details (fraud check).
4. **More document types**: purchase orders, delivery notes and statements, with three-way matching
   (PO ↔ delivery ↔ invoice).
5. **Integrations**: push approved invoices to the accounting system (QuickBooks, Xero, ERP) through n8n or the API;
   email inbox and shared-folder intake.
6. **Compliance**: encryption at rest for originals, retention policies, audit export, signed BAA with the AI provider
   for health-related documents.
7. **Scale-out**: managed PostgreSQL, object storage for originals, autoscaled workers, a metrics dashboard
   (Prometheus/Grafana) with alerts on failure rate and backlog.
