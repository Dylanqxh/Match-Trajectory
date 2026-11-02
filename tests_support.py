from fastapi.testclient import TestClient


def new_client(tmp_path):
    from app.main import create_app

    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")
    client.get("/api/session")
    return client

def fixture_quality(status="ready"):
    """Protocol fixture only, not a claim about semantic model quality."""
    dimensions = [{"dimension": name, "score": 2, "reason": "本地协议测试的固定结构，不代表真实写作评价。", "item_ids": ["document"],
                   "evidence_ids": ["e1"], "action": "keep"} for name in ("fit", "contribution", "evidence", "readability")]
    return {"status": status, "dimensions": dimensions, "interview_topics": []}
