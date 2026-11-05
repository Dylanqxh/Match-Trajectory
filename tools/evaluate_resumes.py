"""Local, opt-in Workflow comparison. No resume/retry of existing runs."""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

# Support both `python -m tools.evaluate_resumes` and direct script invocation.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.budget import DEFAULT_POLICY
from app.generation_models import GenerationInput
from app.jobs import JobStore
from app.model_client import (
    OUTPUT_CONTRACT_VERSION,
    ModelClient,
    ModelRegistry,
    safe_usage,
)
from app.providers import ProviderConfig, ProviderError
from app.skill import load_skill
from app.store import ResumeStore
from app.supervisor import probe_context
from app.workflow import Workflow


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_manifest(data):
    allowed = {"version", "dataset_label", "rules_version", "provider", "max_calls", "timeout_seconds",
               "case_max_calls", "case_timeout_seconds", "cases"}
    if not isinstance(data, dict) or set(data) != allowed or data["version"] != 1:
        raise ValueError("Invalid manifest fields/version")
    if data["dataset_label"] not in ("synthetic", "authorized") or not isinstance(data["rules_version"], str) or not data["rules_version"].strip():
        raise ValueError("Declare dataset_label and rules_version")
    for key in ("max_calls", "timeout_seconds", "case_max_calls", "case_timeout_seconds"):
        if type(data[key]) is not int or not 1 <= data[key] <= 86400:
            raise ValueError("Budgets must be positive bounded integers")
    provider = data["provider"]
    if not isinstance(provider, dict) or set(provider) != {"provider", "base_url", "model"}:
        raise ValueError("Provider must contain provider/base_url/model only; keys belong in environment")
    ProviderConfig(**provider, api_key="offline-placeholder")
    if not isinstance(data["cases"], list) or not 1 <= len(data["cases"]) <= 100:
        raise ValueError("Provide 1-100 cases")
    seen = set()
    for case in data["cases"]:
        if not isinstance(case, dict) or set(case) != {"id", "input"}:
            raise ValueError("Case requires id/input only")
        case_id = case["id"]
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", case_id) or case_id in seen:
            raise ValueError("Unique ASCII case id required")
        seen.add(case_id)
        inputs = case["input"]
        if not isinstance(inputs, dict) or set(inputs) & {"request_id", "execution_mode", "send_materials"}:
            raise ValueError("Runner owns request_id/execution_mode/send_materials")
        parsed = GenerationInput(**inputs, request_id="evaluation-validate", send_materials=True)
        if not parsed.source_text or not parsed.name or not parsed.contact:
            raise ValueError("Each case requires source_text/name/contact")
    return json.loads(json.dumps(data))


class Journal:
    def __init__(self, path, data, secret):
        self.path, self.data, self.secret = path, data, secret
        self.started = time.monotonic()
        self.calls = self.case_calls = 0
        self.case_id = self.mode = ""
        self.case_deadline = 0
        self.block_reason = ""
        self.usage = {}

    def append(self, value):
        # Never store prompts, responses, headers, addresses, or exceptions here.
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def reserve(self, stage):
        if self.calls >= self.data["max_calls"] or self.case_calls >= self.data["case_max_calls"]:
            self.block_reason = "budget_exhausted"
        if time.monotonic() >= min(self.case_deadline, self.started + self.data["timeout_seconds"]):
            self.block_reason = "timeout"
        if self.block_reason:
            raise ProviderError("Evaluation budget exhausted; no further request sent")
        self.calls += 1
        self.case_calls += 1
        attempt = {"event": "attempt", "attempt_id": self.calls, "case_id": self.case_id,
                   "mode": self.mode, "stage": stage, "time_unix": time.time()}
        self.append(attempt)
        return self.calls


class AccountedClient(ModelClient):
    def __init__(self, journal, *, transport=None):
        super().__init__(transport=transport)
        self.journal = journal
        self.stage = ""

    async def complete(self, config, stage, context, schema):
        self.stage = stage
        return await super().complete(config, stage, context, schema)

    async def delegate(self, config, context):
        self.stage = "probe" if self.stage == "probe" else "supervise"
        return await super().delegate(config, context)

    async def _post(self, config, payload, policy=DEFAULT_POLICY):
        journal = self.journal
        attempt_id = journal.reserve(self.stage)
        outcome, usage = "unknown", {}
        try:
            body = await super()._post(config, payload, policy)
            outcome = "response_received"  # Does not imply valid schema or content.
            try:
                usage = safe_usage(json.loads(body))
            except (ValueError, TypeError):
                pass
            for key, value in usage.items():
                journal.usage[key] = journal.usage.get(key, 0) + value
            return body
        except asyncio.CancelledError:
            raise
        except Exception:
            outcome = "failed_may_be_billed"
            raise
        finally:
            journal.append({"event": "outcome", "attempt_id": attempt_id, "outcome": outcome, "usage": usage})


async def evaluate(manifest, output, *, run=False, transport=None):
    data = validate_manifest(manifest)
    output = Path(output)
    if output.exists():
        raise FileExistsError("Run directory already exists; resume is unsupported. Choose a NEW directory explicitly.")
    secret = os.environ.get("EVALUATION_API_KEY", "") if run else ""
    if run and not secret:
        raise ValueError("Set EVALUATION_API_KEY before --run")
    if secret and any(secret in case['id'] for case in data['cases']):
        raise ValueError('Credentials cannot occur in case identifiers')
    output.mkdir(parents=True, exist_ok=False)

    def redact(value):
        if isinstance(value, str):
            return value.replace(secret, "[REDACTED]") if secret else value
        if isinstance(value, dict):
            return {redact(key): redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    def write(name, value):
        text = json.dumps(redact(value), ensure_ascii=False, indent=2)
        (output / name).write_text(text + "\n", encoding="utf-8")

    planned = [{"case_id": case["id"], "mode": mode} for case in data["cases"] for mode in ("langgraph", "supervisor")]
    code_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "app").glob("*.py"))}
    skills = {case["id"]: asdict(load_skill(case["input"]["target_role"], case["input"].get("career_stage", "unspecified"),
                                             case["input"].get("has_career_gap", False))) for case in data["cases"]}
    frozen = {"manifest": data, "manifest_sha256": digest(data), "output_contract_version": OUTPUT_CONTRACT_VERSION,
              "app_sha256": code_hashes, "skills": skills, "skill_sha256": digest(skills),
              "question_policy": "skip_once", "order": "case_then_langgraph_then_supervisor", "resume_supported": False}
    write("frozen.json", frozen)
    report = {"status": "running" if run else "prepared", "attempts": 0, "planned_runs": planned, "results": [],
              "quality_evidence": "synthetic inputs are engineering fixtures; human review required",
              "cost": None, "usage_note": "reported provider token counters only; missing usage is unknown, not zero"}
    write("report.json", report)
    journal = Journal(output / "attempts.jsonl", data, secret)

    def checkpoint():
        report["attempts"] = journal.calls
        report["actual_usage"] = journal.usage
        write("report.json", report)
        with (output / "human_review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["case_id", "mode", "candidate_file", "reviewer", "review_date", "severe_factual_error",
                             "unsupported_claim_ids", "source_evidence_ids", "writing_quality_notes", "accept", "notes"])
            for row in planned:
                candidate = next((r.get("candidate_file", "") for r in report["results"] if r["case_id"] == row["case_id"] and r["mode"] == row["mode"]), "")
                writer.writerow([row["case_id"], row["mode"], candidate, "", "", "", "", "", "", "", ""])

    checkpoint()
    if not run:
        return report
    config = ProviderConfig(**data["provider"], api_key=secret)
    for case in data["cases"]:
        for mode in ("langgraph", "supervisor"):
            journal.case_id, journal.mode = case["id"], mode
            journal.case_calls, journal.block_reason = 0, ""
            journal.case_deadline = time.monotonic() + data["case_timeout_seconds"]
            row = {"case_id": case["id"], "mode": mode, "status": "not_started", "usage": {}, "model_calls": 0}
            client = AccountedClient(journal, transport=transport)
            registry = ModelRegistry()
            registry.register(config)
            job = None
            with tempfile.TemporaryDirectory(prefix="resume-eval-") as workspace:
                store = ResumeStore(Path(workspace) / "resumes.sqlite3")
                jobs = JobStore(store)
                workflow = Workflow(store, jobs, registry, client)
                before_usage = dict(journal.usage)
                try:
                    remaining = min(journal.case_deadline, journal.started + data["timeout_seconds"]) - time.monotonic()
                    if journal.calls >= data["max_calls"]:
                        journal.block_reason = "budget_exhausted"
                        raise ProviderError("Budget exhausted")
                    if remaining <= 0:
                        raise TimeoutError
                    async with asyncio.timeout(remaining):
                        if mode == "supervisor":
                            client.stage = "probe"
                            probe = await client.delegate(config, probe_context())
                            if probe.value.action != "revise" or probe.value.issue_indices != [0]:
                                raise ProviderError("Synthetic tool probe did not follow its task")
                            client.stage = ""
                            registry.verify_tools(registry.current)
                        inputs = GenerationInput(**case["input"], request_id=f"evaluation-{case['id']}-{mode}",
                                                 send_materials=True, execution_mode=mode)
                        job = workflow.submit(inputs)
                        await workflow.run_one()
                        current = jobs.get(job["id"])
                        if current["state"] == "waiting_input":
                            workflow.answer(job["id"], {"question_group": current["question_group"], "skip": True, "answers": {}})
                            await workflow.run_one()
                        row["status"] = jobs.get(job["id"])["state"]
                except TimeoutError:
                    row["status"] = "timeout"
                except Exception:  # noqa: BLE001 -- never serialize provider/database exception material.
                    row["status"] = "failed"  # Never persist exception strings or credentials.
                finally:
                    if job:
                        current = jobs.get(job["id"])
                        row.update(engine_version=current.get("engine_version"), skill_version=current["skill"].get("version"),
                                   budget_policy=current.get("budget_policy"),
                                   stage=current["stage"], workflow_calls=current["calls"], call_log=current["call_log"],
                                   issues=current["issues"], stop_reason=current.get("stop_reason", ""))
                        if current.get("draft"):
                            name = f"{case['id']}-{mode}-candidate.json"
                            write(name, {"draft": current["draft"], "evidence": current["evidence"], "review": current["review"]})
                            row["candidate_file"] = name
                    store.engine.dispose()
            row["status"] = journal.block_reason or row["status"]
            row["model_calls"] = journal.case_calls
            row["usage"] = {key: value - before_usage.get(key, 0) for key, value in journal.usage.items() if value > before_usage.get(key, 0)}
            report["results"].append(row)
            checkpoint()
    report["status"] = "finished"
    checkpoint()
    return redact(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="Send supplied materials to the configured model; may incur charges")
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        report = asyncio.run(evaluate(data, args.output, run=args.run))
    except FileExistsError:
        parser.exit(2, "Existing run refused; no resume. Choose a new --output directory.\n")
    except Exception:  # noqa: BLE001 -- CLI errors must not echo keys or user material.
        parser.exit(2, "Evaluation failed. Check manifest, budgets and EVALUATION_API_KEY; existing reports/attempts retained.\n")
    print(json.dumps({"status": report["status"], "attempts": report["attempts"]}))


if __name__ == "__main__":
    main()
