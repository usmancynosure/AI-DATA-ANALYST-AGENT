"""Run agent-generated Python inside an isolated Docker container.

Security model — the container is started with:
  * ``--network none``               no network access at all
  * ``--memory`` / ``--cpus``        hard resource caps (swap disabled)
  * ``--pids-limit``                 fork-bomb protection
  * ``--read-only`` root filesystem  + small writable tmpfs for /tmp
  * ``--cap-drop ALL`` + ``--security-opt no-new-privileges``
  * non-root user (uid 10001)
  * a wall-clock timeout enforced by the host (container force-removed on expiry)

Data is injected as JSON (no pickle, no network DB access from inside). Only a bind
mount of the per-job scratch directory is shared with the container.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

from app.core.config import get_settings

_BOOTSTRAP_SRC = Path(__file__).parent / "runner_bootstrap.py"


class SandboxResult(BaseModel):
    ok: bool
    stdout: str = ""
    error: str | None = None
    images: list[str] = []  # base64-encoded PNGs
    result: object | None = None
    timed_out: bool = False
    exit_code: int | None = None
    elapsed_ms: float | None = None


class SandboxError(RuntimeError):
    """Infrastructure failure (docker missing, image absent, etc.) — not user-code error."""


class DockerSandbox:
    def __init__(
        self,
        image: str | None = None,
        timeout_seconds: int | None = None,
        memory_limit: str | None = None,
        cpu_limit: float | None = None,
        work_root: Path | None = None,
    ):
        settings = get_settings()
        self.image = image or settings.sandbox_image
        self.timeout_seconds = timeout_seconds or settings.sandbox_timeout_seconds
        self.memory_limit = memory_limit or settings.sandbox_memory_limit
        self.cpu_limit = cpu_limit or settings.sandbox_cpu_limit
        self.work_root = work_root or (settings.data_dir / "sandbox")
        self.work_root.mkdir(parents=True, exist_ok=True)

    # ── availability ─────────────────────────────────────────────────────
    @staticmethod
    def docker_available() -> bool:
        try:
            subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
                check=True,
            )
            return True
        except Exception:
            return False

    def image_available(self) -> bool:
        try:
            out = subprocess.run(
                ["docker", "image", "inspect", self.image],
                capture_output=True,
                timeout=10,
            )
            return out.returncode == 0
        except Exception:
            return False

    # ── execution ────────────────────────────────────────────────────────
    def run(
        self,
        code: str,
        dataframes: dict[str, dict] | None = None,
    ) -> SandboxResult:
        """Execute ``code`` in the sandbox.

        ``dataframes`` maps a variable name to a ``{"columns": [...], "rows": [...]}``
        payload (the shape of :class:`QueryResult`). Each becomes a pandas DataFrame in
        the code's namespace; a single frame is also aliased as ``df``.
        """
        job_id = uuid.uuid4().hex
        job_dir = self.work_root / job_id
        inputs_dir = job_dir / "inputs"
        out_dir = job_dir / "out"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._materialize_job(job_dir, inputs_dir, code, dataframes)
            # The container user (uid 10001) must be able to write outputs.
            _chmod_tree(job_dir, 0o777)
            return self._docker_run(job_dir, out_dir)
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    def _materialize_job(
        self,
        job_dir: Path,
        inputs_dir: Path,
        code: str,
        dataframes: dict[str, dict] | None,
    ) -> None:
        (job_dir / "user_code.py").write_text(code)
        shutil.copyfile(_BOOTSTRAP_SRC, job_dir / "_bootstrap.py")

        manifest: dict[str, dict] = {}
        for i, (name, payload) in enumerate((dataframes or {}).items()):
            filename = f"frame_{i}.json"
            (inputs_dir / filename).write_text(
                json.dumps(
                    {
                        "columns": list(payload.get("columns", [])),
                        "rows": list(payload.get("rows", [])),
                    }
                )
            )
            manifest[name] = {"file": filename}
        (inputs_dir / "manifest.json").write_text(json.dumps(manifest))

    def _docker_run(self, job_dir: Path, out_dir: Path) -> SandboxResult:
        container_name = f"sandbox_{job_dir.name}"
        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--network", "none",
            "--memory", self.memory_limit,
            "--memory-swap", self.memory_limit,  # == memory disables swap
            "--cpus", str(self.cpu_limit),
            "--pids-limit", "128",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m,noexec",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "10001:10001",
            "-e", "HOME=/work",
            "-e", "MPLCONFIGDIR=/work/.mpl",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{job_dir}:/work",
            "-w", "/work",
            self.image,
            "python", "/work/_bootstrap.py",
        ]

        start = time.perf_counter()
        timed_out = False
        exit_code: int | None = None
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.timeout_seconds + 5,  # grace over the in-container budget
            )
            exit_code = proc.returncode
            docker_stderr = proc.stderr.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            timed_out = True
            docker_stderr = "Execution exceeded the time limit."
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        except FileNotFoundError as exc:  # docker not installed
            raise SandboxError("Docker CLI not found on the host.") from exc

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        result_path = out_dir / "result.json"
        if timed_out:
            return SandboxResult(
                ok=False,
                error=f"Execution timed out after {self.timeout_seconds}s.",
                timed_out=True,
                exit_code=exit_code,
                elapsed_ms=elapsed_ms,
            )

        if not result_path.exists():
            # Container died before writing a result (OOM-kill, image error, ...).
            detail = docker_stderr.strip() or "Sandbox produced no result."
            raise SandboxError(f"Sandbox failed (exit {exit_code}): {detail}")

        data = json.loads(result_path.read_text())
        return SandboxResult(
            ok=bool(data.get("ok")),
            stdout=data.get("stdout", ""),
            error=data.get("error"),
            images=data.get("images", []),
            result=data.get("result"),
            timed_out=False,
            exit_code=exit_code,
            elapsed_ms=elapsed_ms,
        )


def _chmod_tree(root: Path, mode: int) -> None:
    root.chmod(mode)
    for p in root.rglob("*"):
        try:
            p.chmod(mode)
        except OSError:
            pass
