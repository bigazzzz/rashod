# Age keys (never commit `*.key`)

| File | Where | Purpose |
|------|--------|---------|
| `age-deploy.key` | **server only** | `deploy.sh` decrypts `secrets.enc.yaml` |
| Owner's age key (`age1y6…` recipient) | owner's machine | local editing via `SOPS_AGE_KEY_FILE` |

Do **not** put a personal age key on the server. Deploy uses `age-deploy.key` only.

```bash
chmod 600 keys/age-deploy.key
```
