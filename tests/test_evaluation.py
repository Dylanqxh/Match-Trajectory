import asyncio
import json

import httpx
import pytest
from test_workflow import DRAFT, PASS, PLAN

from tests_support import fixture_quality


def manifest(**updates):
    return {"version": 1, "dataset_label": "synthetic", "rules_version": "trial-1",
            "provider": {"provider": "custom", "base_url": "http://127.0.0.1:12345/v1", "model": "fixed-model"},
            "max_calls": 12, "timeout_seconds": 60, "case_max_calls": 6, "case_timeout_seconds": 20,
            "cases": [{"id": "synthetic-1", "input": {"target_role": "Java 后端", "name": "合成用户",
                "contact": "synthetic@example.invalid", "source_text": "使用 Java 完成课程预约查询接口，编写测试记录，未上线。"}}], **updates}


def evaluate(tmp_path, data=None, **kwargs):
    from tools.evaluate_resumes import evaluate as run
    return asyncio.run(run(data or manifest(), tmp_path / "run", **kwargs))


def test_default_is_offline_without_reading_credentials(tmp_path, monkeypatch):
    original_get = __import__("os").environ.get
    def guard(key, *args):
        if key == "EVALUATION_API_KEY":
            pytest.fail("offline must not read credentials")
        return original_get(key, *args)
    monkeypatch.setattr("os.environ.get", guard)
    result = evaluate(tmp_path, transport=httpx.MockTransport(lambda _: pytest.fail("offline network")))
    assert result["status"] == "prepared" and result["attempts"] == 0
    assert len(result["planned_runs"]) == 2
    assert not (tmp_path / "run" / "attempts.jsonl").exists()


def test_explicit_run_requires_environment_key(tmp_path, monkeypatch):
    monkeypatch.delenv("EVALUATION_API_KEY", raising=False)
    with pytest.raises(ValueError, match="EVALUATION_API_KEY"):
        evaluate(tmp_path, run=True)


def test_credential_cannot_leak_through_case_id_filenames_or_csv(tmp_path, monkeypatch):
    monkeypatch.setenv('EVALUATION_API_KEY', 'synthetic-1')
    with pytest.raises(ValueError):
        evaluate(tmp_path, run=True, transport=httpx.MockTransport(lambda _: pytest.fail('must not send')))
    assert not (tmp_path / 'run').exists()


def test_existing_run_directory_is_never_overwritten(tmp_path):
    evaluate(tmp_path)
    before = (tmp_path / "run" / "report.json").read_bytes()
    with pytest.raises(FileExistsError):
        evaluate(tmp_path, run=True)
    assert (tmp_path / "run" / "report.json").read_bytes() == before


def test_supervisor_probe_must_satisfy_synthetic_task_before_enabling(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALUATION_API_KEY", "probe-test-key")
    outputs = iter([PLAN, DRAFT, {**PASS, "quality": fixture_quality()}])
    def server(request):
        if 'tools' in json.loads(request.content):
            return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {
                "tool_calls": [{"type": "function", "function": {"name": "delegate_to_writer", "arguments": json.dumps({
                    "action": "deliver", "issue_indices": [], "rationale": "does not follow probe task"})}}]}}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(next(outputs))}}]})
    report = evaluate(tmp_path, run=True, transport=httpx.MockTransport(server))
    assert report["results"][0]["status"] == 'ready'
    assert report["results"][1]["status"] == 'failed'
    assert report["results"][1]["model_calls"] == 1


def test_real_client_boundary_is_journaled_before_send_and_total_budget_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALUATION_API_KEY", "secret-never-persist")
    seen = []
    def server(request):
        journal = (tmp_path / "run" / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(journal[-1])["event"] == "attempt"
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(PLAN)}}], "usage": {"total_tokens": 7}})
    result = evaluate(tmp_path, manifest(max_calls=1), run=True, transport=httpx.MockTransport(server))
    assert len(seen) == result["attempts"] == 1
    assert len(result["results"]) == 2
    assert result["results"][1]["status"] == "budget_exhausted"
    assert "secret-never-persist" not in "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "run").rglob("*") if p.is_file())


def test_full_comparison_exports_candidates_usage_and_blank_human_review(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALUATION_API_KEY", "synthetic-key-only")
    outputs = iter([PLAN, DRAFT, {**PASS, "quality": fixture_quality()}, PLAN, DRAFT, {**PASS, "quality": fixture_quality()}])
    def server(request):
        payload = json.loads(request.content)
        if "tools" in payload:
            return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{"type": "function", "function": {"name": "delegate_to_writer", "arguments": json.dumps({"action": "revise", "issue_indices": [0], "rationale": "probe"})}}]}}], "usage": {"total_tokens": 2}})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(next(outputs))}}], "usage": {"total_tokens": 7}})
    result = evaluate(tmp_path, run=True, transport=httpx.MockTransport(server))
    assert result["attempts"] == 7
    assert [row["status"] for row in result["results"]] == ["ready", "ready"]
    assert [row["usage"]["total_tokens"] for row in result["results"]] == [21, 23]  # includes supervisor probe
    assert all((tmp_path / "run" / row["candidate_file"]).exists() for row in result["results"])
    assert "severe_factual_error" in (tmp_path / "run" / "human_review.csv").read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("update", [{"max_calls": 0}, {"provider": {"api_key": "forbidden"}}, {"cases": []}])
def test_invalid_manifest_rejected_before_creating_output(tmp_path, update):
    with pytest.raises(ValueError):
        evaluate(tmp_path, manifest(**update))
    assert not (tmp_path / "run").exists()


def test_each_case_budget_includes_probe_and_never_resets_total(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALUATION_API_KEY", "synthetic-only")
    seen = []
    def server(request):
        seen.append(request)
        return httpx.Response(503)
    result = evaluate(tmp_path, manifest(case_max_calls=1), run=True, transport=httpx.MockTransport(server))
    assert len(seen) == result["attempts"] == 2
    assert all(row["model_calls"] == 1 for row in result["results"])


def test_cancelled_request_is_unknown_and_not_replayed(tmp_path, monkeypatch):
    from app.model_client import ModelClient
    monkeypatch.setenv("EVALUATION_API_KEY", "synthetic-only")
    async def slow_post(*args):
        await asyncio.sleep(10)
    monkeypatch.setattr(ModelClient, "_post", slow_post)
    result = evaluate(tmp_path, manifest(timeout_seconds=1, case_timeout_seconds=1), run=True)
    assert result["attempts"] == 1
    entries = [json.loads(line) for line in (tmp_path / "run" / "attempts.jsonl").read_text().splitlines()]
    assert entries[-1]["outcome"] == "unknown"
    assert [row["status"] for row in result["results"]] == ["timeout", "timeout"]
    with pytest.raises(FileExistsError):
        evaluate(tmp_path, run=True)


def test_unknown_manifest_fields_and_embedded_credentials_never_persist(tmp_path):
    with pytest.raises(ValueError):
        evaluate(tmp_path, manifest(api_key="embedded-forbidden"))
    assert not (tmp_path / "run").exists()


def test_key_echo_with_json_special_characters_is_redacted(tmp_path, monkeypatch):
    secret = 'synthetic-"key\\value'
    monkeypatch.setenv("EVALUATION_API_KEY", secret)
    data = manifest()
    data["cases"][0]["input"]["source_text"] += secret
    evaluate(tmp_path, data, run=True, transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    frozen = json.loads((tmp_path / "run" / "frozen.json").read_text(encoding="utf-8"))
    assert secret not in frozen["manifest"]["cases"][0]["input"]["source_text"]


def test_shipped_synthetic_example_validates_offline(tmp_path):
    from pathlib import Path
    example = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "synthetic-example.json").read_text(encoding="utf-8"))
    assert evaluate(tmp_path, example)["status"] == "prepared"
