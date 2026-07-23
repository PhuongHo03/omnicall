import math
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from backend.configs.settings import Settings
from backend.models.meeting_models import MeetingAsset
from backend.providers.voice import (
    AudioPreprocessingResult,
    LocalASRProvider,
    LocalAudioPreprocessor,
    LocalCommandDiarizationProvider,
    LocalVADProvider,
    SpeechRegion,
    _voice_command_timeout,
    get_asr_provider,
)
from backend.providers.transcript_types import TranscriptSegment


class FakeStorageProvider:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.read_count = 0

    def get_object_bytes(self, *, object_key: str) -> bytes:
        self.read_count += 1
        return self.content


class VoiceProviderTestCase(unittest.TestCase):
    def test_wav_metadata_fallback_returns_working_path_and_audio_metadata(self) -> None:
        wav_bytes = _wav_bytes(with_tone=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            provider = LocalAudioPreprocessor(
                FakeStorageProvider(wav_bytes),
                Settings(),
                ffmpeg_path="/missing/ffmpeg",
                work_dir=tmp_dir,
            )

            result = provider.preprocess(_asset())
            remaining_files = list(Path(tmp_dir).iterdir())

        self.assertIsNotNone(result.working_path)
        self.assertEqual(result.duration_ms, 1000)
        self.assertEqual(result.sample_rate_hz, 16000)
        self.assertEqual(result.channel_count, 1)
        self.assertEqual(len(remaining_files), 1)
        self.assertEqual(remaining_files[0].suffix, ".wav")
        self.assertTrue(any("ffmpeg was not found" in warning for warning in result.warnings))

    def test_audio_preprocessing_reuses_stable_derived_wav_across_retries(self) -> None:
        wav_bytes = _wav_bytes(with_tone=True)
        storage = FakeStorageProvider(wav_bytes)
        with tempfile.TemporaryDirectory() as tmp_dir:
            provider = LocalAudioPreprocessor(
                storage,
                Settings(),
                ffmpeg_path="/missing/ffmpeg",
                work_dir=tmp_dir,
            )

            first = provider.preprocess(_asset())
            second = provider.preprocess(_asset())
            remaining_files = list(Path(tmp_dir).iterdir())

        self.assertEqual(first.working_path, second.working_path)
        self.assertEqual(storage.read_count, 1)
        self.assertEqual(len(remaining_files), 1)
        self.assertEqual(first.duration_ms, second.duration_ms)

    def test_energy_vad_detects_speech_region_from_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "speech.wav"
            path.write_bytes(_wav_bytes(with_tone=True))
            settings = Settings(
                vad_energy_threshold=0.001,
                vad_min_speech_ms=100,
                vad_silence_gap_ms=100,
            )
            provider = LocalVADProvider(settings)

            regions = provider.detect_speech(
                type(
                    "Audio",
                    (),
                    {
                        "working_path": str(path),
                    },
                )()
            )

        self.assertTrue(regions)
        self.assertEqual(regions[0].start_ms, 0)
        self.assertGreaterEqual(regions[0].end_ms, 900)

    def test_local_asr_command_parses_json_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "speech.wav"
            audio_path.write_bytes(_wav_bytes(with_tone=True))
            script_path = Path(tmp_dir) / "fake_asr.py"
            script_path.write_text(
                "import json\n"
                "print(json.dumps({'segments': ["
                "{'text': 'Local command transcript.', 'start': 0.25, 'end': 1.25, 'confidence': 0.91}"
                "]}))\n",
                encoding="utf-8",
            )
            provider = LocalASRProvider(
                Settings(),
                command_template=f"{sys.executable} {script_path} --audio {{audio_path}}",
                model_name="fake-whisper-int8",
            )

            segments = provider.transcribe_audio(
                audio=_audio_result(str(audio_path)),
                speech_regions=[SpeechRegion(start_ms=100, end_ms=1300, confidence=0.8)],
            )

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].id, "seg-001")
        self.assertEqual(segments[0].text, "Local command transcript.")
        self.assertEqual(segments[0].start_ms, 250)
        self.assertEqual(segments[0].end_ms, 1250)
        self.assertEqual(segments[0].confidence, 0.91)
        self.assertEqual(provider.provider_model, "fake-whisper-int8")

    def test_local_asr_rejects_low_confidence_hallucination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "noise.wav"
            audio_path.write_bytes(_wav_bytes(with_tone=False))
            script_path = Path(tmp_dir) / "fake_asr.py"
            script_path.write_text(
                "import json\n"
                "print(json.dumps({'segments': [{"
                "'text': 'Thank you.', 'start': 3.15, 'end': 4.15, "
                "'confidence': 0.0103, 'avg_logprob': -0.942653, 'no_speech_prob': 0.820743"
                "}]}))\n",
                encoding="utf-8",
            )
            provider = LocalASRProvider(
                Settings(asr_min_segment_confidence=0.1, asr_max_no_speech_probability=0.6),
                command_template=f"{sys.executable} {script_path} --audio {{audio_path}}",
            )

            segments = provider.transcribe_audio(
                audio=_audio_result(str(audio_path)),
                speech_regions=[SpeechRegion(start_ms=200, end_ms=900, confidence=0.2)],
            )

        self.assertEqual(segments, [])

    def test_local_asr_keeps_legacy_segment_without_quality_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "speech.wav"
            audio_path.write_bytes(_wav_bytes(with_tone=True))
            script_path = Path(tmp_dir) / "fake_asr.py"
            script_path.write_text(
                "import json\n"
                "print(json.dumps({'segments': [{'text': 'Xin chao.', 'start': 0, 'end': 1}]}))\n",
                encoding="utf-8",
            )
            provider = LocalASRProvider(
                Settings(),
                command_template=f"{sys.executable} {script_path} --audio {{audio_path}}",
            )

            segments = provider.transcribe_audio(
                audio=_audio_result(str(audio_path)),
                speech_regions=[SpeechRegion(start_ms=0, end_ms=1000, confidence=0.8)],
            )

        self.assertEqual([segment.text for segment in segments], ["Xin chao."])

    def test_asr_provider_factory_keeps_asr_local_only(self) -> None:
        provider = get_asr_provider(Settings())

        self.assertIsInstance(provider, LocalASRProvider)

    def test_voice_command_timeout_scales_with_audio_duration(self) -> None:
        long_audio = AudioPreprocessingResult(
            source_object_key="test/long.wav",
            working_path="/tmp/long.wav",
            duration_ms=566_496,
            sample_rate_hz=16000,
            channel_count=1,
            warnings=[],
        )

        self.assertEqual(
            _voice_command_timeout(
                audio=_audio_result("/tmp/short.wav"),
                minimum_seconds=120,
                realtime_factor=1.0,
            ),
            120,
        )
        self.assertEqual(
            _voice_command_timeout(
                audio=long_audio,
                minimum_seconds=120,
                realtime_factor=1.0,
            ),
            566.496,
        )

    def test_local_diarization_command_assigns_speaker_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "speech.wav"
            audio_path.write_bytes(_wav_bytes(with_tone=True))
            script_path = Path(tmp_dir) / "fake_diarization.py"
            script_path.write_text(
                "import json, sys\n"
                "payload = json.load(sys.stdin)\n"
                "print(json.dumps({'segments': ["
                "{'id': 'seg-001', 'speaker': 'Speaker 1', 'confidence': 0.93},"
                "{'id': 'seg-002', 'speaker': 'Speaker 2', 'confidence': 0.89}"
                "]}))\n",
                encoding="utf-8",
            )
            provider = LocalCommandDiarizationProvider(
                Settings(),
                command_template=f"{sys.executable} {script_path}",
                model_name="fake-wespeaker",
            )

            segments = provider.assign_speakers(
                audio=_audio_result(str(audio_path)),
                transcript_segments=[
                    TranscriptSegment("seg-001", "unknown", 0, 1000, "Hello", 0.91),
                    TranscriptSegment("seg-002", "unknown", 1000, 2000, "Hi", 0.88),
                ],
            )

        self.assertEqual([segment.speaker for segment in segments], ["Speaker 1", "Speaker 2"])
        self.assertEqual(segments[0].confidence, 0.93)
        self.assertEqual(provider.provider_model, "fake-wespeaker")


def _asset() -> MeetingAsset:
    return MeetingAsset(
        id="44444444-4444-4444-8444-444444444444",
            owner_user_id="33333333-3333-4333-8333-333333333333",
        meeting_id="11111111-1111-4111-8111-111111111111",
        object_key="workspaces/test/meetings/test/uploads/meeting.wav",
        file_name="meeting.wav",
        content_type="audio/wav",
        size_bytes=32044,
        idempotency_key="upload-test",
    )


def _audio_result(path: str) -> AudioPreprocessingResult:
    return AudioPreprocessingResult(
        source_object_key="test/audio.wav",
        working_path=path,
        duration_ms=1000,
        sample_rate_hz=16000,
        channel_count=1,
        warnings=[],
    )


def _wav_bytes(*, with_tone: bool) -> bytes:
    sample_rate = 16000
    samples = array("h")
    for index in range(sample_rate):
        value = int(9000 * math.sin(2 * math.pi * 440 * index / sample_rate)) if with_tone else 0
        samples.append(value)
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        with wave.open(handle.name, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())
        return Path(handle.name).read_bytes()




if __name__ == "__main__":
    unittest.main()
