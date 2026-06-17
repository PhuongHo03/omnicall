import json
import os
import subprocess
from pathlib import Path

from huggingface_hub import snapshot_download


MODEL_SPECS = (
    ("ASR", "asr"),
    ("DIARIZATION", "diarization"),
    ("RERANK", "rerank"),
)


def main() -> None:
    cache_dir = Path(os.getenv("MODEL_CACHE_DIR", "/models"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache_dir / ".hf-cache"))

    for prefix, subdir in MODEL_SPECS:
        target_dir = Path(os.getenv(f"{prefix}_MODEL_DIR", str(cache_dir / subdir)))
        target_dir.mkdir(parents=True, exist_ok=True)
        command = os.getenv(f"{prefix}_DOWNLOAD_COMMAND", "").strip()
        repo_id = os.getenv(f"{prefix}_HF_REPO", "").strip()
        revision = os.getenv(f"{prefix}_HF_REVISION", "main").strip() or "main"

        if command:
            _run_download_command(prefix=prefix, command=command, target_dir=target_dir, cache_dir=cache_dir)
            continue
        if repo_id:
            _download_hugging_face_snapshot(prefix=prefix, repo_id=repo_id, revision=revision, target_dir=target_dir)
            continue
        print(f"[model-init] {prefix}: no repository or command configured; skipping.")


def _run_download_command(*, prefix: str, command: str, target_dir: Path, cache_dir: Path) -> None:
    env = {
        **os.environ,
        "MODEL_CACHE_DIR": str(cache_dir),
        "MODEL_TARGET_DIR": str(target_dir),
    }
    print(f"[model-init] {prefix}: running custom download command.")
    subprocess.run(command, shell=True, check=True, env=env)
    _write_marker(target_dir, {"source": "command", "prefix": prefix})


def _download_hugging_face_snapshot(*, prefix: str, repo_id: str, revision: str, target_dir: Path) -> None:
    print(f"[model-init] {prefix}: downloading {repo_id}@{revision} into {target_dir}.")
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(target_dir),
    )
    _write_marker(
        target_dir,
        {
            "source": "huggingface",
            "prefix": prefix,
            "repoId": repo_id,
            "revision": revision,
        },
    )


def _write_marker(target_dir: Path, metadata: dict) -> None:
    marker_path = target_dir / ".omnicall-model.json"
    marker_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
