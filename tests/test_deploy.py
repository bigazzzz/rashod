import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("fail_decrypt", [False, True])
def test_deploy_uses_cloudflare_sops_file(tmp_path, fail_decrypt):
    repo = Path(__file__).resolve().parents[1]
    tools = tmp_path / "bin"
    tools.mkdir()
    (tmp_path / "scripts").mkdir()
    shutil.copy2(repo / "deploy.sh", tmp_path)
    shutil.copy2(repo / "scripts/sops-decrypt-env.sh", tmp_path / "scripts")
    for name in (".env", "secrets.enc.yaml", "cloudflare.enc.yaml", "test.key"):
        (tmp_path / name).write_text("fixture\n")
    sops = tools / "sops"
    sops.write_text("""#!/bin/sh
case "$4" in
  *cloudflare.enc.yaml)
    test "$FAIL_DECRYPT" = 0 || exit 1
    echo CLOUDFLARE_API_TOKEN=test-value
    ;;
  *) echo OPS_TOKEN=test-ops ;;
esac
""")
    docker = tools / "docker"
    docker.write_text("""#!/bin/sh
if [ "$1" = compose ]; then
    last_env=''
    while [ "$#" -gt 0 ]; do
        if [ "$1" = --env-file ]; then last_env="$2"; shift; fi
        shift
    done
    echo "$last_env" > docker-env-path
    grep -qx CLOUDFLARE_API_TOKEN=test-value "$last_env" || exit 1
    test -z "${CLOUDFLARE_API_TOKEN:-}" || exit 1
fi
""")
    for tool in (sops, docker):
        tool.chmod(0o700)
    env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "SKIP_GIT_PULL": "1",
           "SOPS_AGE_KEY_FILE": str(tmp_path / "test.key"), "TMPDIR": str(tmp_path),
           "FAIL_DECRYPT": str(int(fail_decrypt)), "CLOUDFLARE_API_TOKEN": "stale"}
    result = subprocess.run(["bash", "deploy.sh"], cwd=tmp_path, env=env, capture_output=True)
    marker = tmp_path / "docker-env-path"
    if fail_decrypt:
        assert result.returncode != 0
        assert not marker.exists()
    else:
        assert result.returncode == 0
        assert not Path(marker.read_text().strip()).exists()
        assert (tmp_path / ".env.secrets").read_text() == "OPS_TOKEN=test-ops\n"
