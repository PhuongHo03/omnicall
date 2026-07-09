import argparse
import contextlib
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local faster-whisper ASR and emit Omnicall JSON segments.")
    parser.add_argument("--audio-path", required=True)
    parser.add_argument("--model-dir", default="")
    parser.add_argument("--model-name", default="medium")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--beam-size", type=int, default=5)
    args = parser.parse_args()

    model_ref = _model_ref(args.model_dir, args.model_name)
    with contextlib.redirect_stdout(sys.stderr):
        from faster_whisper import WhisperModel

        model = WhisperModel(
            model_ref,
            device="cpu",
            compute_type=args.compute_type,
            local_files_only=Path(model_ref).exists(),
        )
        segments, info = model.transcribe(
            args.audio_path,
            beam_size=args.beam_size,
            language=None if args.language == "auto" else args.language,
            vad_filter=True,
        )
        result = {
            "language": getattr(info, "language", None),
            "languageProbability": getattr(info, "language_probability", None),
            "segments": [_segment_payload(index, segment) for index, segment in enumerate(segments, start=1)],
        }
    print(json.dumps(result, ensure_ascii=False))


def _model_ref(model_dir: str, model_name: str) -> str:
    path = Path(model_dir) if model_dir else None
    if path and path.exists() and any(path.iterdir()):
        return str(path)
    return model_name


def _segment_payload(index: int, segment) -> dict:
    avg_logprob = getattr(segment, "avg_logprob", None)
    no_speech_prob = getattr(segment, "no_speech_prob", None)
    confidence = _confidence(avg_logprob=avg_logprob, no_speech_prob=no_speech_prob)
    return {
        "id": f"seg-{index:03d}",
        "speaker": "unknown",
        "startMs": int(max(0.0, float(segment.start)) * 1000),
        "endMs": int(max(0.0, float(segment.end)) * 1000),
        "text": str(segment.text or "").strip(),
        "confidence": confidence,
        "avg_logprob": avg_logprob,
        "no_speech_prob": no_speech_prob,
    }


def _confidence(*, avg_logprob: float | None, no_speech_prob: float | None) -> float:
    confidence = 0.8
    if avg_logprob is not None:
        confidence = max(0.0, min(1.0, 1.0 + float(avg_logprob)))
    if no_speech_prob is not None:
        confidence *= max(0.0, min(1.0, 1.0 - float(no_speech_prob)))
    return round(confidence, 4)


if __name__ == "__main__":
    main()
