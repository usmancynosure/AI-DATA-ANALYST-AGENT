import io

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _csv_bytes() -> bytes:
    df = pd.DataFrame({"region": ["N", "S", "N"], "amount": [10, 20, 30]})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_and_query_flow():
    # create session
    r = client.post("/sessions")
    assert r.status_code == 200
    session_id = r.json()["session_id"]

    # upload
    r = client.post(
        f"/sessions/{session_id}/upload",
        files={"file": ("data.csv", _csv_bytes(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tables"] == ["data"]
    assert body["schema_info"]["tables"][0]["row_count"] == 3

    # query
    r = client.post(
        f"/sessions/{session_id}/query",
        json={"query": "SELECT region, SUM(amount) AS total FROM data GROUP BY region ORDER BY region"},
    )
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result["columns"] == ["region", "total"]
    assert result["rows"] == [["N", 40], ["S", 20]]


def test_query_rejects_write():
    r = client.post("/sessions")
    session_id = r.json()["session_id"]
    client.post(
        f"/sessions/{session_id}/upload",
        files={"file": ("data.csv", _csv_bytes(), "text/csv")},
    )
    r = client.post(f"/sessions/{session_id}/query", json={"query": "DROP TABLE data"})
    assert r.status_code == 400


def test_missing_session_404():
    r = client.get("/sessions/nonexistent")
    assert r.status_code == 404
