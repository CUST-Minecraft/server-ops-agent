"""A fresh checkout must expose protected APIs before the UI is built."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("frontend_built", [False, True], ids=["api-only", "built-ui"])
def test_web_starts_with_or_without_frontend(tmp_path, frontend_built):
    project = Path(__file__).resolve().parents[1]
    module = tmp_path / "app" / "web" / "app.py"
    module.parent.mkdir(parents=True)
    module.write_text((project / "app/web/app.py").read_text(encoding="utf-8"), encoding="utf-8")
    if frontend_built:
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("fixture frontend", encoding="utf-8")

    # An isolated process avoids reusing an already-imported app or a local build.
    script = """
import runpy
import sys
from fastapi.testclient import TestClient
web = runpy.run_path(sys.argv[1])
client = TestClient(web["app"])
assert client.get("/api/status").status_code == 401
response = client.get("/")
if sys.argv[2] == "True":
    assert response.status_code == 200
    assert response.text == "fixture frontend"
else:
    assert response.status_code == 404
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(module), str(frontend_built)],
        cwd=project, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
