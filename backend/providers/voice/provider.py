import json
import math
import re
import shutil
import shlex
import subprocess
import wave
from array import array
from pathlib import Path
from uuid import uuid4

from backend.configs.model_runtime import (
    ASR_COMMAND,
    ASR_MODEL,
    DIARIZATION_COMMAND,
    DIARIZATION_MODEL,
    VOICE_FFMPEG_PATH,
    VOICE_WORK_DIR,
    build_asr_command,
)
from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import MeetingAsset
from backend.providers.storage_provider import ObjectStorageProvider, get_object_storage_provider
from backend.providers.transcript_types import TranscriptSegment
from backend.providers.contracts.voice import (
    ASRProvider,
    AudioPreprocessingResult,
    AudioPreprocessor,
    DiarizationProvider,
    SpeakerTurn,
    SpeechRegion,
    VADProvider,
)


class LocalAudioPreprocessor:
    provider_name = "local-ffmpeg-audio-preprocessor"
    provider_model = "ffmpeg-wav-16khz-mono-v1"

    def __init__(
        self,
        storage_provider: ObjectStorageProvider,
        settings: Settings | None = None,
        *,
        ffmpeg_path: str = VOICE_FFMPEG_PATH,
        work_dir: str = VOICE_WORK_DIR,
    ) -> None:
        self.storage_provider = storage_provider
        self.settings = settings or get_settings()
        self.ffmpeg_path = ffmpeg_path
        self.work_dir = work_dir

    def preprocess(self, asset: MeetingAsset) -> AudioPreprocessingResult:
        warnings: list[str] = []
        work_dir = Path(self.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        output_path = work_dir / f"{_safe_audio_stem(asset)}.16k-mono.wav"
        if output_path.exists():
            metadata = _wav_metadata(output_path, warnings)
            if metadata["duration_ms"] is not None:
                return AudioPreprocessingResult(
                    source_object_key=asset.object_key,
                    working_path=str(output_path),
                    duration_ms=metadata["duration_ms"],
                    sample_rate_hz=metadata["sample_rate_hz"],
                    channel_count=metadata["channel_count"],
                    warnings=warnings,
                )
            output_path.unlink(missing_ok=True)

        raw = self.storage_provider.get_object_bytes(object_key=asset.object_key)
        input_path = work_dir / f"{_safe_audio_stem(asset)}-{uuid4().hex}{Path(asset.file_name).suffix.lower() or '.bin'}"
        input_path.write_bytes(raw)

        try:
            ffmpeg_path = _resolve_binary(self.ffmpeg_path)
            if ffmpeg_path is None:
                warnings.append("ffmpeg was not found; voice preprocessing used WAV metadata fallback when possible.")
                _copy_wav_fallback(input_path=input_path, output_path=output_path, warnings=warnings)
            else:
                command = [
                    ffmpeg_path,
                    "-y",
                    "-i",
                    str(input_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "wav",
                    str(output_path),
                ]
                completed = subprocess.run(command, capture_output=True, check=False, timeout=120)
                if completed.returncode != 0:
                    warnings.append("ffmpeg could not normalize the asset; WAV metadata fallback was attempted.")
                    _copy_wav_fallback(input_path=input_path, output_path=output_path, warnings=warnings)
        finally:
            input_path.unlink(missing_ok=True)

        metadata = _wav_metadata(output_path, warnings) if output_path.exists() else _empty_metadata()
        return AudioPreprocessingResult(
            source_object_key=asset.object_key,
            working_path=str(output_path) if output_path.exists() else None,
            duration_ms=metadata["duration_ms"],
            sample_rate_hz=metadata["sample_rate_hz"],
            channel_count=metadata["channel_count"],
            warnings=warnings,
        )


class LocalVADProvider:
    provider_name = "local-energy-vad"
    provider_model = "energy-threshold-v1"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def detect_speech(self, audio: AudioPreprocessingResult) -> list[SpeechRegion]:
        if audio.working_path is None:
            return []
        path = Path(audio.working_path)
        if not path.exists():
            return []
        try:
            with wave.open(str(path), "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                sample_width = wav_file.getsampwidth()
                channel_count = wav_file.getnchannels()
                frame_count = wav_file.getnframes()
                frames = wav_file.readframes(frame_count)
        except wave.Error:
            return []
        if sample_width != 2 or sample_rate <= 0 or not frames:
            return []

        samples = array("h")
        samples.frombytes(frames)
        if channel_count > 1:
            samples = _downmix(samples, channel_count)

        window_size = max(1, int(sample_rate * 0.1))
        active_windows: list[tuple[int, int, float]] = []
        for start_index in range(0, len(samples), window_size):
            window = samples[start_index:start_index + window_size]
            if not window:
                continue
            energy = _rms_energy(window)
            if energy >= self.settings.vad_energy_threshold:
                start_ms = int(start_index / sample_rate * 1000)
                end_ms = int(min(len(samples), start_index + window_size) / sample_rate * 1000)
                active_windows.append((start_ms, end_ms, energy))
        return _merge_regions(
            active_windows,
            min_speech_ms=self.settings.vad_min_speech_ms,
            silence_gap_ms=self.settings.vad_silence_gap_ms,
        )


class LocalASRProvider:
    provider_name = "local-whisper-command-asr"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        command_template: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if command_template is not None:
            self.command_template = command_template
        else:
            self.command_template = build_asr_command(
                model_name=self.settings.asr_model,
                compute_type=self.settings.asr_compute_type,
                beam_size=self.settings.asr_beam_size,
                language=self.settings.asr_language,
            )
        self.provider_model = model_name or self.settings.asr_model

    def transcribe_audio(
        self,
        *,
        audio: AudioPreprocessingResult,
        speech_regions: list[SpeechRegion],
    ) -> list[TranscriptSegment]:
        if audio.working_path is None or not Path(audio.working_path).exists():
            return []
        command_text = self.command_template.format(
            audio_path=audio.working_path,
            language="auto",
        )
        completed = subprocess.run(
            shlex.split(command_text),
            capture_output=True,
            check=False,
            text=True,
            timeout=_voice_command_timeout(
                audio=audio,
                minimum_seconds=self.settings.asr_timeout_seconds,
                realtime_factor=self.settings.asr_timeout_realtime_factor,
            ),
        )
        if completed.returncode != 0:
            raise RuntimeError("Local ASR command failed.")
        if not completed.stdout.strip():
            return []
        payload = json.loads(completed.stdout)
        segments, language = _segments_from_asr_payload(payload, speech_regions)
        self.last_detected_language = language
        return segments


class LocalCommandDiarizationProvider:
    provider_name = "local-wespeaker-diarization"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        command_template: str = DIARIZATION_COMMAND,
        model_name: str = DIARIZATION_MODEL,
    ) -> None:
        self.settings = settings or get_settings()
        self.command_template = command_template
        self.provider_model = model_name

    def assign_speakers(
        self,
        *,
        audio: AudioPreprocessingResult,
        transcript_segments: list[TranscriptSegment],
    ) -> list[TranscriptSegment]:
        if audio.working_path is None or not Path(audio.working_path).exists():
            raise RuntimeError("Diarization requires a preprocessed audio file.")
        payload = {
            "model": self.provider_model,
            "audioPath": audio.working_path,
            "segments": [
                {
                    "id": segment.id,
                    "speaker": segment.speaker,
                    "startMs": segment.start_ms,
                    "endMs": segment.end_ms,
                    "text": segment.text,
                    "confidence": segment.confidence,
                }
                for segment in transcript_segments
            ],
        }
        command_text = self.command_template.format(
            audio_path=audio.working_path,
        )
        completed = subprocess.run(
            shlex.split(command_text),
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            check=False,
            text=True,
            timeout=_voice_command_timeout(
                audio=audio,
                minimum_seconds=self.settings.asr_timeout_seconds,
                realtime_factor=self.settings.asr_timeout_realtime_factor,
            ),
        )
        if completed.returncode != 0:
            raise RuntimeError("Local diarization command failed.")
        response = json.loads(completed.stdout)
        return _merge_diarization_payload(response, transcript_segments)


def get_audio_preprocessor(settings: Settings | None = None) -> AudioPreprocessor:
    resolved = settings or get_settings()
    return LocalAudioPreprocessor(get_object_storage_provider(), resolved)


def _voice_command_timeout(
    *,
    audio: AudioPreprocessingResult,
    minimum_seconds: float,
    realtime_factor: float,
) -> float:
    audio_seconds = max(0.0, audio.duration_ms / 1000)
    return max(minimum_seconds, audio_seconds * max(0.0, realtime_factor))


def get_vad_provider(settings: Settings | None = None) -> VADProvider:
    resolved = settings or get_settings()
    return LocalVADProvider(resolved)


def get_asr_provider(settings: Settings | None = None) -> ASRProvider:
    resolved = settings or get_settings()
    return LocalASRProvider(resolved)


def get_diarization_provider(settings: Settings | None = None) -> DiarizationProvider:
    resolved = settings or get_settings()
    return LocalCommandDiarizationProvider(resolved)


def _resolve_binary(path: str) -> str | None:
    if "/" in path:
        return path if Path(path).exists() else None
    return shutil.which(path)


def _safe_audio_stem(asset: MeetingAsset) -> str:
    raw_stem = f"{asset.id}-{Path(asset.file_name).stem}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", raw_stem).strip(".-") or str(asset.id)


def _copy_wav_fallback(*, input_path: Path, output_path: Path, warnings: list[str]) -> None:
    if input_path.suffix.lower() != ".wav":
        warnings.append("Audio asset is not a WAV file, so metadata fallback was skipped.")
        return
    shutil.copyfile(input_path, output_path)


def _wav_metadata(path: Path, warnings: list[str]) -> dict[str, int | None]:
    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channel_count = wav_file.getnchannels()
            frame_count = wav_file.getnframes()
    except wave.Error:
        warnings.append("Normalized WAV metadata could not be read.")
        return _empty_metadata()
    duration_ms = int(frame_count / sample_rate * 1000) if sample_rate > 0 else None
    return {
        "duration_ms": duration_ms,
        "sample_rate_hz": sample_rate,
        "channel_count": channel_count,
    }


def _empty_metadata() -> dict[str, int | None]:
    return {"duration_ms": None, "sample_rate_hz": None, "channel_count": None}


def _downmix(samples: array, channel_count: int) -> array:
    mixed = array("h")
    for index in range(0, len(samples), channel_count):
        frame = samples[index:index + channel_count]
        if frame:
            mixed.append(int(sum(frame) / len(frame)))
    return mixed


def _rms_energy(samples: array) -> float:
    if not samples:
        return 0.0
    square_sum = sum(sample * sample for sample in samples)
    return math.sqrt(square_sum / len(samples)) / 32768


def _merge_regions(
    windows: list[tuple[int, int, float]],
    *,
    min_speech_ms: int,
    silence_gap_ms: int,
) -> list[SpeechRegion]:
    if not windows:
        return []
    merged: list[tuple[int, int, float]] = []
    current_start, current_end, current_energy = windows[0]
    for start_ms, end_ms, energy in windows[1:]:
        if start_ms - current_end <= silence_gap_ms:
            current_end = end_ms
            current_energy = max(current_energy, energy)
            continue
        merged.append((current_start, current_end, current_energy))
        current_start, current_end, current_energy = start_ms, end_ms, energy
    merged.append((current_start, current_end, current_energy))
    return [
        SpeechRegion(start_ms=start, end_ms=end, confidence=min(0.99, max(0.1, energy)))
        for start, end, energy in merged
        if end - start >= min_speech_ms
    ]


def _segments_from_asr_payload(payload: dict | list, speech_regions: list[SpeechRegion]) -> tuple[list[TranscriptSegment], str | None]:
    raw_segments = payload if isinstance(payload, list) else payload.get("segments", [])
    language = payload.get("language") if isinstance(payload, dict) else None
    if not isinstance(raw_segments, list):
        return [], language
    segments: list[TranscriptSegment] = []
    for index, raw_segment in enumerate(raw_segments, start=1):
        if not isinstance(raw_segment, dict):
            continue
        text = str(raw_segment.get("text") or "").strip()
        if not text:
            continue
        fallback_region = speech_regions[min(index - 1, len(speech_regions) - 1)] if speech_regions else None
        start_ms = _asr_time_ms(raw_segment, "startMs", "start", fallback_region.start_ms if fallback_region else 0)
        end_ms = _asr_time_ms(raw_segment, "endMs", "end", fallback_region.end_ms if fallback_region else max(start_ms + 1000, start_ms))
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        segments.append(
            TranscriptSegment(
                id=str(raw_segment.get("id") or f"seg-{index:03d}"),
                speaker=str(raw_segment.get("speaker") or raw_segment.get("speakerLabel") or "unknown"),
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                confidence=_asr_confidence(raw_segment),
            )
        )
    return segments, language


def _merge_diarization_payload(payload: dict | list, transcript_segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    if isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        segment_labels = {
            str(item.get("id")): item
            for item in payload["segments"]
            if isinstance(item, dict) and item.get("id") is not None
        }
        if segment_labels:
            return [
                _segment_with_speaker(segment, segment_labels.get(segment.id, {}))
                for segment in transcript_segments
            ]
    turns = payload if isinstance(payload, list) else payload.get("turns", []) if isinstance(payload, dict) else []
    if not isinstance(turns, list):
        raise RuntimeError("Diarization response must include segments or turns.")
    normalized_turns = [
        item for item in turns
        if isinstance(item, dict) and item.get("speaker")
    ]
    if not normalized_turns:
        raise RuntimeError("Diarization response did not include speaker assignments.")
    result = []
    for segment in transcript_segments:
        turn, overlap_ratio = _best_turn(segment, normalized_turns)
        seg_duration = max(1, segment.end_ms - segment.start_ms)
        threshold = 0.05 if seg_duration < 500 else 0.10
        if turn and overlap_ratio >= threshold:
            result.append(_segment_with_speaker(segment, turn, overlap_ratio))
        else:
            result.append(TranscriptSegment(
                id=segment.id,
                speaker=segment.speaker or "unknown",
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
                confidence=max(0.0, min(1.0, segment.confidence * 0.5)),
            ))
    return result


def _segment_with_speaker(
    segment: TranscriptSegment,
    assignment: dict,
    overlap_ratio: float = 1.0,
) -> TranscriptSegment:
    speaker = str(assignment.get("speaker") or assignment.get("speakerLabel") or segment.speaker or "unknown")
    turn_confidence = float(assignment.get("confidence", 0.85))
    confidence = max(0.1, min(0.99, turn_confidence * overlap_ratio))
    return TranscriptSegment(
        id=segment.id,
        speaker=speaker,
        start_ms=segment.start_ms,
        end_ms=segment.end_ms,
        text=segment.text,
        confidence=confidence,
    )


def _best_turn(segment: TranscriptSegment, turns: list[dict]) -> tuple[dict, float]:
    best: dict = {}
    best_score = -1.0
    best_ratio = 0.0
    seg_duration = max(1, segment.end_ms - segment.start_ms)
    for turn in turns:
        start_ms = _turn_time_ms(turn, "startMs", "start")
        end_ms = _turn_time_ms(turn, "endMs", "end")
        overlap = max(0, min(segment.end_ms, end_ms) - max(segment.start_ms, start_ms))
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


def _asr_time_ms(raw_segment: dict, ms_key: str, seconds_key: str, fallback: int) -> int:
    if raw_segment.get(ms_key) is not None:
        return max(0, int(float(raw_segment[ms_key])))
    if raw_segment.get(seconds_key) is not None:
        return max(0, int(float(raw_segment[seconds_key]) * 1000))
    return fallback


def _asr_confidence(raw_segment: dict) -> float:
    for key in ("confidence", "score"):
        if raw_segment.get(key) is not None:
            return max(0.0, min(1.0, float(raw_segment[key])))
    if raw_segment.get("avg_logprob") is not None:
        return max(0.0, min(1.0, 1.0 + float(raw_segment["avg_logprob"])))
    return 0.8


def _turn_time_ms(raw_turn: dict, ms_key: str, seconds_key: str) -> int:
    if raw_turn.get(ms_key) is not None:
        return max(0, int(float(raw_turn[ms_key])))
    if raw_turn.get(seconds_key) is not None:
        return max(0, int(float(raw_turn[seconds_key]) * 1000))
    return 0
