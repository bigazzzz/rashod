# Age keys (never commit `*.key`)

| File | Where | Purpose |
|------|--------|---------|
| `age-deploy.key` | **server only** | `deploy.sh` decrypts `secrets.enc.yaml` |
| `age-dev.key` | developer machine | `sops secrets.enc.yaml` edits |
| `age-deploy.pub.txt` / `age-dev.pub.txt` | optional local notes | public keys (also in `.sops.yaml`) |

Do **not** put a personal age key on the server. Deploy uses `age-deploy.key` only.

```bash
chmod 600 keys/age-deploy.key keys/age-dev.key
```
