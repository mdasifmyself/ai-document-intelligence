# Evaluation

`run_eval.py` measures the real, running system against the labelled dataset: it uploads every file through the
public API, waits for the background workers, then compares every extracted field with the answer key.

```bash
python evaluation/run_eval.py --api https://<api> --code <access-code> --data dataset/out          # 96 files
python evaluation/run_eval.py --api https://<api> --code <access-code> --data dataset/out --big    # 1,000 pages
```

Results: `results/evaluation.md|json`, `results/big-batch.md|json`; earlier runs and what was fixed after each are in
`results/history/`. The method and the final numbers are explained in [../docs/08-evaluation-report.md](../docs/08-evaluation-report.md).

How a field counts as correct: invoice numbers equal after removing spaces and punctuation; dates equal; supplier and
customer names ≥ 90 % similar after removing legal suffixes; amounts within 0.01; currency codes equal. A field that
is not printed must come back empty, and anything else counts as an invented value.
