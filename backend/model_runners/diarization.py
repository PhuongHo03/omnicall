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
            raw_confidence = item.get("confidence")
        elif isinstance(item, (list, tuple)) and len(item) >= 4:
            _, start, end, label = item[:4]
            start = float(start)
            end = float(end)
            raw_confidence = None
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
                "confidence": max(0.1, min(0.99, float(raw_confidence))) if raw_confidence is not None else 0.85,
            }
        )
    return turns


def _assign_segments(segments: list, turns: list[dict]) -> list[dict]:
    assigned = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        seg_start = int(segment.get("startMs") or 0)
        seg_end = int(segment.get("endMs") or seg_start)
        seg_duration = max(1, seg_end - seg_start)
        turn, overlap_ratio = _best_turn(segment, turns)
        if turn and overlap_ratio >= _min_overlap_threshold(seg_duration):
            confidence = _dynamic_confidence(turn.get("confidence", 0.85), overlap_ratio)
            assigned.append(
                {
                    "id": segment.get("id"),
                    "speaker": turn["speaker"],
                    "confidence": confidence,
                }
            )
        else:
            assigned.append(
                {
                    "id": segment.get("id"),
                    "speaker": segment.get("speaker", "unknown"),
                    "confidence": segment.get("confidence", 0.5),
                }
            )
    return assigned


def _best_turn(segment: dict, turns: list[dict]) -> tuple[dict, float]:
    best: dict = {}
    best_score = -1.0
    best_ratio = 0.0
    start = int(segment.get("startMs") or 0)
    end = int(segment.get("endMs") or start)
    seg_duration = max(1, end - start)
    for turn in turns:
        t_start = int(turn["startMs"])
        t_end = int(turn["endMs"])
        overlap = max(0, min(end, t_end) - max(start, t_start))
        if overlap <= 0:
            continue
        overlap_ratio = overlap / seg_duration
        turn_confidence = turn.get("confidence", 0.85)
        score = overlap_ratio * 0.7 + turn_confidence * 0.3
        if score > best_score:
            best = turn
            best_score = score
            best_ratio = overlap_ratio
    return best, best_ratio


def _min_overlap_threshold(seg_duration_ms: int) -> float:
    if seg_duration_ms < 500:
        return 0.05
    return 0.10


def _dynamic_confidence(turn_confidence: float, overlap_ratio: float) -> float:
    return max(0.1, min(0.99, turn_confidence * overlap_ratio))


def _seconds(value: Any) -> float:
    numeric = float(value)
    return numeric / 1000 if numeric > 1000 else numeric


if __name__ == "__main__":
    main()
