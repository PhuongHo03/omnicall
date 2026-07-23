import sys
import tempfile
import unittest
from pathlib import Path

from backend.configs.settings import Settings
from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.transcript_types import TranscriptSegment
from backend.providers.transcription_provider import (
    LocalTranscriptionProvider,
    NoRecognizableSpeechError,
    TranscriptionProviderError,
)
from backend.providers.voice import AudioPreprocessingResult, LocalASRProvider, LocalCommandDiarizationProvider, SpeechRegion


class FakeAudioPreprocessor:
    provider_name = "fake-preprocessor"
    provider_model = "fake-preprocessor-model"

    def preprocess(self, asset: MeetingAsset) -> AudioPreprocessingResult:
        return AudioPreprocessingResult(
            source_object_key=asset.object_key,
            working_path="/tmp/fake.wav",
            duration_ms=5000,
            sample_rate_hz=16000,
            channel_count=1,
            warnings=[],
        )


class ExistingAudioPreprocessor(FakeAudioPreprocessor):
    def __init__(self, path: str) -> None:
        self.path = path

    def preprocess(self, asset: MeetingAsset) -> AudioPreprocessingResult:
        return AudioPreprocessingResult(
            source_object_key=asset.object_key,
            working_path=self.path,
            duration_ms=1000,
            sample_rate_hz=16000,
            channel_count=1,
            warnings=[],
        )


class FakeVADProvider:
    provider_name = "fake-vad"
    provider_model = "fake-vad-model"

    def detect_speech(self, audio: AudioPreprocessingResult) -> list[SpeechRegion]:
        return [SpeechRegion(start_ms=0, end_ms=5000, confidence=0.9)]


class FakeASRProvider:
    provider_name = "fake-asr"
    provider_model = "fake-asr-model"

    def transcribe_audio(
        self,
        *,
        audio: AudioPreprocessingResult,
        speech_regions: list[SpeechRegion],
    ) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(
                id="seg-001",
                speaker="unknown",
                start_ms=0,
                end_ms=5000,
                text="Audio transcript text from ASR.",
                confidence=0.88,
            )
        ]


class BrokenASRProvider:
    provider_name = "broken-asr"
    provider_model = "broken-asr-model"

    def transcribe_audio(
        self,
        *,
        audio: AudioPreprocessingResult,
        speech_regions: list[SpeechRegion],
    ) -> list[TranscriptSegment]:
        raise RuntimeError("asr crashed")


class EmptyASRProvider:
    provider_name = "empty-asr"
    provider_model = "empty-asr-model"
    last_detected_language = None

    def transcribe_audio(self, *, audio, speech_regions) -> list[TranscriptSegment]:
        return []


class FakeDiarizationProvider:
    provider_name = "fake-diarization"
    provider_model = "fake-diarization-model"

    def assign_speakers(
        self,
        *,
        audio: AudioPreprocessingResult,
        transcript_segments: list[TranscriptSegment],
    ) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(
                id=segment.id,
                speaker="Speaker 1",
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
                confidence=segment.confidence,
            )
            for segment in transcript_segments
        ]


class TranscriptionProviderTestCase(unittest.TestCase):
    def test_voice_provider_contract_outputs_diarized_transcript_segments(self) -> None:
        provider = LocalTranscriptionProvider(
            audio_preprocessor=FakeAudioPreprocessor(),
            vad_provider=FakeVADProvider(),
            asr_provider=FakeASRProvider(),
            diarization_provider=FakeDiarizationProvider(),
        )

        segments = provider.transcribe(_meeting(), _asset())

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].speaker, "Speaker 1")
        self.assertEqual(segments[0].text, "Audio transcript text from ASR.")
        self.assertEqual(provider.last_provider_name, "fake-asr")
        self.assertEqual(provider.last_voice_metadata["asrProvider"], "fake-asr")
        self.assertEqual(provider.last_voice_metadata["diarizationProvider"], "fake-diarization")
        self.assertEqual(provider.last_voice_metadata["speechRegionCount"], 1)

    def test_asr_failure_raises_without_placeholder_with_safe_voice_metadata(self) -> None:
        provider = LocalTranscriptionProvider(
            audio_preprocessor=FakeAudioPreprocessor(),
            vad_provider=FakeVADProvider(),
            asr_provider=BrokenASRProvider(),
            diarization_provider=FakeDiarizationProvider(),
        )

        with self.assertRaises(TranscriptionProviderError):
            provider.transcribe(_meeting(), _asset())

        self.assertEqual(provider.last_provider_name, "broken-asr")
        self.assertEqual(provider.last_voice_metadata["asrProvider"], "broken-asr")
        self.assertNotEqual(provider.last_voice_metadata["sourceKind"], "audio-placeholder")
        self.assertIn("ASR error type: RuntimeError.", provider.last_voice_metadata["warnings"])

    def test_empty_asr_result_is_classified_as_no_recognizable_speech(self) -> None:
        provider = LocalTranscriptionProvider(
            audio_preprocessor=FakeAudioPreprocessor(),
            vad_provider=FakeVADProvider(),
            asr_provider=EmptyASRProvider(),
            diarization_provider=FakeDiarizationProvider(),
        )

        with self.assertRaisesRegex(NoRecognizableSpeechError, "No recognizable speech"):
            provider.transcribe(_meeting(), _asset())

    def test_local_asr_command_voice_input_returns_real_transcript_not_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "audio.wav"
            audio_path.write_bytes(b"fake wav bytes")
            script_path = Path(tmp_dir) / "fake_asr.py"
            script_path.write_text(
                "import json\n"
                "print(json.dumps({'segments': [{'text': 'Command ASR transcript.', 'startMs': 0, 'endMs': 900}]}))\n",
                encoding="utf-8",
            )
            diarization_script = Path(tmp_dir) / "fake_diarization.py"
            diarization_script.write_text(
                "import json\n"
                "payload = json.load(__import__('sys').stdin)\n"
                "print(json.dumps({'segments': [dict(item, speaker='Speaker 1') for item in payload['segments']]}))\n",
                encoding="utf-8",
            )
            provider = LocalTranscriptionProvider(
                audio_preprocessor=ExistingAudioPreprocessor(str(audio_path)),
                vad_provider=FakeVADProvider(),
                asr_provider=LocalASRProvider(
                    Settings(),
                    command_template=f"{sys.executable} {script_path} --audio {{audio_path}}",
                ),
                diarization_provider=LocalCommandDiarizationProvider(
                    Settings(),
                    command_template=f"{sys.executable} {diarization_script}",
                    model_name="fake-wespeaker",
                ),
            )

            segments = provider.transcribe(_meeting(), _asset())

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].text, "Command ASR transcript.")
        self.assertNotIn("placeholder transcript", segments[0].text)
        self.assertEqual(segments[0].speaker, "Speaker 1")
        self.assertEqual(provider.last_provider_name, "local-whisper-command-asr")


def _meeting() -> Meeting:
    return Meeting(
        id="11111111-1111-4111-8111-111111111111",
            owner_user_id="33333333-3333-4333-8333-333333333333",
        title="Voice contract test",
    )


def _asset(*, file_name: str = "meeting.wav", content_type: str = "audio/wav") -> MeetingAsset:
    return MeetingAsset(
        id="44444444-4444-4444-8444-444444444444",
            owner_user_id="33333333-3333-4333-8333-333333333333",
        meeting_id="11111111-1111-4111-8111-111111111111",
        object_key=f"workspaces/test/meetings/test/uploads/{file_name}",
        file_name=file_name,
        content_type=content_type,
        size_bytes=100,
        idempotency_key="upload-test",
    )


if __name__ == "__main__":
    unittest.main()
