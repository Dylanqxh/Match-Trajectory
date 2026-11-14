from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_docker_image_builds_locked_frontend_and_matching_browser_runtime():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "playwright install --with-deps chromium" in dockerfile
    assert "fonts-noto-cjk" in dockerfile
    assert "MATCH_TRAJECTORY_FONT_PATH" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert '["--host", "0.0.0.0"' in dockerfile


def test_compose_publishes_only_to_loopback_and_persists_workspace_data():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["match-trajectory"]

    assert service["build"] == "."
    assert service["ports"] == ["127.0.0.1:${MATCH_TRAJECTORY_PORT:-18765}:18765"]
    assert service["volumes"] == ["match-trajectory-data:/app/data"]
    assert "match-trajectory-data" in compose["volumes"]


def test_docker_context_excludes_local_secrets_data_and_dependency_caches():
    rules = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for expected in [".env", "data", ".venv", "node_modules", "artifacts", ".git"]:
        assert expected in rules
