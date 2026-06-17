import argparse
import contextlib
import json
import sys
import wave
from array import array
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local WeSpeaker diarization and emit Omnicall speaker turns.")
    parser.add_argument("--audio-path", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    request = _read_stdin_json()
    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        raise SystemExit(f"WeSpeaker model directory was not found: {model_dir}")
    _ensure_wespeaker_layout(model_dir)

    with contextlib.redirect_stdout(sys.stderr):
        import wespeaker

        model = wespeaker.load_model_local(str(model_dir)) if hasattr(wespeaker, "load_model_local") else wespeaker.load_model(str(model_dir))
        if hasattr(model, "set_device"):
            model.set_device(args.device)
        elif hasattr(model, "set_gpu"):
            model.set_gpu(-1)
        _patch_torchaudio_wav_loader()
        raw_turns = model.diarize(args.audio_path)

    turns = _normalize_turns(raw_turns)
    segments = _assign_segments(request.get("segments", []), turns)
    print(json.dumps({"turns": turns, "segments": segments}, ensure_ascii=False))


def _ensure_wespeaker_layout(model_dir: Path) -> None:
    expected = model_dir / "avg_model.pt"
    source = model_dir / "avg_model"
    if expected.exists() or not source.exists():
        return
    try:
        expected.symlink_to(source.name)
    except OSError:
        expected.write_bytes(source.read_bytes())


def _patch_torchaudio_wav_loader() -> None:
    import torch
    import torchaudio

    original_load = torchaudio.load

    def load(uri, *args, **kwargs):
        path = Path(str(uri))
        if path.suffix.lower() != ".wav":
            return original_load(uri, *args, **kwargs)
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channel_count = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frames = wav_file.readframes(wav_file.getnframes())
        if sample_width != 2:
            return original_load(uri, *args, **kwargs)
        samples = array("h")
        samples.frombytes(frames)
        tensor = torch.tensor(samples, dtype=torch.float32)
        if channel_count > 1:
            tensor = tensor.reshape(-1, channel_count).transpose(0, 1)
        else:
            tensor = tensor.unsqueeze(0)
        tensor = tensor / 32768.0
        return tensor, sample_rate

    torchaudio.load = load


def _read_stdin_json() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


def _normalize_turns(raw_turns: Any) -> list[dict]:
    turns: list[dict] = []
    for index, item in enumerate(raw_turns or [], start=1):
        if isinstance(item, dict):
            start = _seconds(item.get("start", item.get("startMs", 0)))
            end = _seconds(item.get("end", item.get("endMs", start)))
            label = item.get("speaker", item.get("label", index))
        elif isinstance(item, (list, tuple)) and len(item) >= 4:
            _, start, end, label = item[:4]
            start = float(start)
            end = float(end)
        else:
            continue
        if end <= start:
            continue
        speaker_index = int(label) + 1 if isinstance(label, int) or str(label).isdigit() else str(label)
        turns.append(
            {
                "speaker": f"Speaker {speaker_index}" if isinstance(speaker_index, int) else str(speaker_index),
                "startMs": int(start * 1000),
                "endMs": int(end * 1000),
                "confidence": 0.82,
            }
        )
    return turns


def _assign_segments(segments: list, turns: list[dict]) -> list[dict]:
    assigned = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        turn = _best_turn(segment, turns)
        assigned.append(
            {
                "id": segment.get("id"),
                "speaker": turn.get("speaker", segment.get("speaker", "unknown")),
                "confidence": turn.get("confidence", segment.get("confidence", 0.8)),
            }
        )
    return assigned


def _best_turn(segment: dict, turns: list[dict]) -> dict:
    best: dict = {}
    best_overlap = -1
    start = int(segment.get("startMs") or 0)
    end = int(segment.get("endMs") or start)
    for turn in turns:
        overlap = max(0, min(end, int(turn["endMs"])) - max(start, int(turn["startMs"])))
        if overlap > best_overlap:
            best = turn
            best_overlap = overlap
    return best


def _seconds(value: Any) -> float:
    numeric = float(value)
    return numeric / 1000 if numeric > 1000 else numeric


if __name__ == "__main__":
    main()
