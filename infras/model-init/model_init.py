import json
import os
from pathlib import Path

from huggingface_hub import snapshot_download


MODEL_SPECS = (
    ("ASR", "asr", "Systran/faster-whisper-medium", "main"),
    ("DIARIZATION", "diarization", "Wespeaker/wespeaker-voxceleb-resnet34-LM", "main"),
    ("RERANK", "rerank", "BAAI/bge-reranker-v2-m3", "main"),
)


def main() -> None:
    cache_dir = Path("/models")
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache_dir / ".hf-cache"))

    for prefix, subdir, repo_id, revision in MODEL_SPECS:
        target_dir = cache_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        _download_hugging_face_snapshot(
            prefix=prefix,
            repo_id=repo_id,
            revision=revision,
            target_dir=target_dir,
        )


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
