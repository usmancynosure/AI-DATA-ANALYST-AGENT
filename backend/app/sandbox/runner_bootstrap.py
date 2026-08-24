"""Bootstrap executed INSIDE the sandbox container.

This file must be standalone: it may only import the standard library plus the packages
installed in the sandbox image (pandas, numpy, matplotlib, ...). It must NOT import
anything from the `app` package.

Contract (all paths inside the container's /work bind mount):
  in:  /work/user_code.py            the agent's Python
       /work/inputs/manifest.json    {var_name: relative_parquet_or_json_path}
  out: /work/out/result.json         {ok, stdout, error, images[], result, ...}
       /work/out/fig_*.png           any matplotlib figures left open by the code
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout

WORK = "/work"
OUT = os.path.join(WORK, "out")


def _load_inputs(namespace: dict) -> None:
    manifest_path = os.path.join(WORK, "inputs", "manifest.json")
    if not os.path.exists(manifest_path):
        return
    import pandas as pd

    with open(manifest_path) as f:
        manifest = json.load(f)

    loaded: dict = {}
    for var_name, spec in manifest.items():
        path = os.path.join(WORK, "inputs", spec["file"])
        with open(path) as f:
            payload = json.load(f)
        df = pd.DataFrame(data=payload["rows"], columns=payload["columns"])
        namespace[var_name] = df
        loaded[var_name] = df

    # Convenience alias: if exactly one frame was provided and it is not already
    # called "df", expose that frame as `df` too.
    if len(loaded) == 1 and "df" not in loaded:
        namespace["df"] = next(iter(loaded.values()))


def _save_figures() -> list[str]:
    images: list[str] = []
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return images

    for i, num in enumerate(plt.get_fignums()):
        fig = plt.figure(num)
        png_path = os.path.join(OUT, f"fig_{i}.png")
        fig.savefig(png_path, dpi=120, bbox_inches="tight")
        with open(png_path, "rb") as f:
            images.append(base64.b64encode(f.read()).decode("ascii"))
    return images


def _jsonable(value):
    """Best-effort conversion of a `result` variable to something JSON-serializable."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        pass
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            return {
                "columns": list(value.columns.astype(str)),
                "rows": value.head(1000).astype(object).where(value.notna(), None).values.tolist(),
            }
        if isinstance(value, pd.Series):
            return value.head(1000).to_dict()
    except Exception:
        pass
    return str(value)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    # Force a non-interactive backend before any user import of matplotlib.
    os.environ["MPLBACKEND"] = "Agg"

    namespace: dict = {"__name__": "__main__"}

    result_obj = {
        "ok": False,
        "stdout": "",
        "error": None,
        "images": [],
        "result": None,
    }

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        _load_inputs(namespace)
        with open(os.path.join(WORK, "user_code.py")) as f:
            source = f.read()
        compiled = compile(source, "<user_code>", "exec")
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(compiled, namespace)  # noqa: S102 - this is the whole point of the sandbox
        result_obj["ok"] = True
        if "result" in namespace:
            result_obj["result"] = _jsonable(namespace["result"])
    except Exception:
        result_obj["ok"] = False
        result_obj["error"] = traceback.format_exc()
    finally:
        result_obj["stdout"] = stdout_buf.getvalue()
        stderr = stderr_buf.getvalue()
        if stderr:
            result_obj["stdout"] += ("\n[stderr]\n" + stderr)
        try:
            result_obj["images"] = _save_figures()
        except Exception:
            result_obj["images"] = []

    with open(os.path.join(OUT, "result.json"), "w") as f:
        json.dump(result_obj, f)


if __name__ == "__main__":
    sys.exit(main())
