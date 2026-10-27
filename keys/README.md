# Age private key (local / server only)

Place `age.key` here (`chmod 600`). This directory is gitignored except this README.

Generate (once):

```bash
age-keygen -o keys/age.key
```

Then put the printed **public** key into `.sops.yaml` `age:` recipient and run
`sops updatekeys secrets.enc.yaml` if rotating.
