"""Integration tests for the Docker sandbox.

These require a working Docker daemon and the `ai-analyst-sandbox:latest` image
(`docker build -t ai-analyst-sandbox:latest ./sandbox-image`). They skip otherwise.
"""

import pytest

from app.sandbox.runner import DockerSandbox

sandbox = DockerSandbox()

pytestmark = pytest.mark.skipif(
    not (DockerSandbox.docker_available() and sandbox.image_available()),
    reason="Docker daemon or sandbox image not available",
)


def test_basic_stdout():
    res = sandbox.run("print('hello from sandbox')")
    assert res.ok
    assert "hello from sandbox" in res.stdout
    assert res.error is None


def test_dataframe_injection_and_result():
    frames = {
        "sales": {
            "columns": ["region", "amount"],
            "rows": [["N", 10], ["S", 20], ["N", 30]],
        }
    }
    code = "result = sales.groupby('region')['amount'].sum().to_dict()"
    res = sandbox.run(code, dataframes=frames)
    assert res.ok, res.error
    assert res.result == {"N": 40, "S": 20}


def test_single_frame_aliased_as_df():
    frames = {"sales": {"columns": ["x"], "rows": [[1], [2], [3]]}}
    res = sandbox.run("result = int(df['x'].sum())", dataframes=frames)
    assert res.ok, res.error
    assert res.result == 6


def test_matplotlib_figure_captured():
    code = (
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3], [4, 5, 6])\n"
        "plt.title('demo')\n"
    )
    res = sandbox.run(code)
    assert res.ok, res.error
    assert len(res.images) == 1
    assert isinstance(res.images[0], str) and len(res.images[0]) > 100


def test_runtime_error_is_captured():
    res = sandbox.run("raise ValueError('boom')")
    assert res.ok is False
    assert "ValueError" in (res.error or "")
    assert "boom" in (res.error or "")


def test_network_is_disabled():
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('8.8.8.8', 53), timeout=3)\n"
        "    result = 'connected'\n"
        "except Exception as e:\n"
        "    result = 'blocked'\n"
    )
    res = sandbox.run(code)
    assert res.ok, res.error
    assert res.result == "blocked"


def test_timeout_is_enforced():
    fast = DockerSandbox(timeout_seconds=3)
    res = fast.run("while True:\n    pass")
    assert res.timed_out is True
    assert res.ok is False
