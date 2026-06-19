from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.text_extraction_provider import DocumentTextExtractionProvider, get_text_extraction_provider
from backend.providers.transcript_types import TranscriptSegment
from backend.providers.voice_provider import (
    ASRProvider,
    AudioPreprocessor,
    DiarizationProvider,
    VADProvider,
    get_asr_provider,
    get_audio_preprocessor,
    get_diarization_provider,
    get_vad_provider,
)


class TranscriptionProviderError(RuntimeError):
    pass


class LocalTranscriptionProvider:
    provider_name = "local-transcription-router"
    provider_model = "routing-v1"
    last_provider_name = provider_name
    last_provider_model = provider_model

    def __init__(
        self,
        text_extraction_provider: DocumentTextExtractionProvider | None = None,
        audio_preprocessor: AudioPreprocessor | None = None,
        vad_provider: VADProvider | None = None,
        asr_provider: ASRProvider | None = None,
        diarization_provider: DiarizationProvider | None = None,
    ) -> None:
        self.text_extraction_provider = text_extraction_provider
        self.audio_preprocessor = audio_preprocessor
        self.vad_provider = vad_provider
        self.asr_provider = asr_provider
        self.diarization_provider = diarization_provider
        self.last_voice_metadata: dict = {}

    def route_metadata(self, asset: MeetingAsset) -> dict:
        if self.text_extraction_provider is not None and self.text_extraction_provider.can_extract(asset):
            return {
                "sourceKind": "text",
                "provider": self.text_extraction_provider.provider_name,
                "model": self.text_extraction_provider.provider_model,
            }
        if self.asr_provider is not None:
            return {
                "sourceKind": "voice",
                "provider": self.asr_provider.provider_name,
                "model": self.asr_provider.provider_model,
                "audioPreprocessor": getattr(self.audio_preprocessor, "provider_name", None),
                "audioPreprocessorModel": getattr(self.audio_preprocessor, "provider_model", None),
                "vadProvider": getattr(self.vad_provider, "provider_name", None),
                "vadModel": getattr(self.vad_provider, "provider_model", None),
                "diarizationProvider": getattr(self.diarization_provider, "provider_name", None),
                "diarizationModel": getattr(self.diarization_provider, "provider_model", None),
            }
        return {
            "sourceKind": "unknown",
            "provider": self.provider_name,
            "model": self.provider_model,
        }

    def transcribe(self, meeting: Meeting, asset: MeetingAsset) -> list[TranscriptSegment]:
        self.last_voice_metadata = {}
        if self.text_extraction_provider is not None and self.text_extraction_provider.can_extract(asset):
            extracted = self.text_extraction_provider.extract(asset)
            if extracted.segments:
                self.last_provider_name = self.text_extraction_provider.provider_name
                self.last_provider_model = self.text_extraction_provider.provider_model
                self.last_voice_metadata = {"sourceKind": extracted.source_kind}
                return extracted.segments

        voice_segments = self._transcribe_voice_asset(asset)
        if voice_segments:
            return voice_segments

        raise TranscriptionProviderError("Audio transcription requires a configured local ASR model command.")

    def _transcribe_voice_asset(self, asset: MeetingAsset) -> list[TranscriptSegment]:
        if self.audio_preprocessor is None or self.vad_provider is None or self.asr_provider is None:
            raise TranscriptionProviderError("Voice transcription providers are not configured.")
        warnings: list[str] = []
        try:
            audio = self.audio_preprocessor.preprocess(asset)
        except Exception as exc:
            self.last_voice_metadata = {
                "sourceKind": "voice",
                "audioPreprocessor": getattr(self.audio_preprocessor, "provider_name", None),
                "audioPreprocessorModel": getattr(self.audio_preprocessor, "provider_model", None),
                "warnings": ["Voice preprocessing failed."],
                "errorType": type(exc).__name__,
            }
            raise TranscriptionProviderError("Voice preprocessing failed.") from exc

        warnings.extend(audio.warnings)
        try:
            speech_regions = self.vad_provider.detect_speech(audio)
        except Exception as exc:
            speech_regions = []
            warnings.append("Voice activity detection failed; ASR continued without speech-region hints.")
            warnings.append(f"VAD error type: {type(exc).__name__}.")
        if not speech_regions:
            warnings.append("No speech regions were detected by VAD.")

        try:
            segments = self.asr_provider.transcribe_audio(audio=audio, speech_regions=speech_regions)
        except Exception as exc:
            self.last_provider_name = self.asr_provider.provider_name
            self.last_provider_model = self.asr_provider.provider_model
            self.last_voice_metadata = _voice_metadata(
                audio=audio,
                audio_preprocessor=self.audio_preprocessor,
                vad_provider=self.vad_provider,
                asr_provider=self.asr_provider,
                diarization_provider=self.diarization_provider,
                speech_regions=speech_regions,
                warnings=[
                    *warnings,
                    "ASR failed.",
                    f"ASR error type: {type(exc).__name__}.",
                ],
            )
            raise TranscriptionProviderError(
                f"ASR failed: {type(exc).__name__}: {exc}"
            ) from exc
        if not segments:
            warnings.append("ASR did not return transcript segments.")
            self.last_voice_metadata = _voice_metadata(
                audio=audio,
                audio_preprocessor=self.audio_preprocessor,
                vad_provider=self.vad_provider,
                asr_provider=self.asr_provider,
                diarization_provider=self.diarization_provider,
                speech_regions=speech_regions,
                warnings=warnings,
            )
            raise TranscriptionProviderError("ASR did not return transcript segments.")
        if self.diarization_provider is not None:
            try:
                segments = self.diarization_provider.assign_speakers(audio=audio, transcript_segments=segments)
            except Exception as exc:
                warnings.append("Speaker diarization failed.")
                warnings.append(f"Diarization error type: {type(exc).__name__}.")
                self.last_voice_metadata = _voice_metadata(
                    audio=audio,
                    audio_preprocessor=self.audio_preprocessor,
                    vad_provider=self.vad_provider,
                    asr_provider=self.asr_provider,
                    diarization_provider=self.diarization_provider,
                    speech_regions=speech_regions,
                    warnings=warnings,
                )
                raise TranscriptionProviderError(
                    f"Speaker diarization failed: {type(exc).__name__}: {exc}"
                ) from exc
        self.last_provider_name = self.asr_provider.provider_name
        self.last_provider_model = self.asr_provider.provider_model
        self.last_voice_metadata = _voice_metadata(
            audio=audio,
            audio_preprocessor=self.audio_preprocessor,
            vad_provider=self.vad_provider,
            asr_provider=self.asr_provider,
            diarization_provider=self.diarization_provider,
            speech_regions=speech_regions,
            warnings=warnings,
        )
        return segments


def get_transcription_provider() -> LocalTranscriptionProvider:
    return LocalTranscriptionProvider(
        text_extraction_provider=get_text_extraction_provider(),
        audio_preprocessor=get_audio_preprocessor(),
        vad_provider=get_vad_provider(),
        asr_provider=get_asr_provider(),
        diarization_provider=get_diarization_provider(),
    )


def _voice_metadata(
    *,
    audio,
    audio_preprocessor: AudioPreprocessor,
    vad_provider: VADProvider,
    asr_provider: ASRProvider,
    diarization_provider: DiarizationProvider | None,
    speech_regions,
    warnings: list[str],
) -> dict:
    return {
        "sourceKind": "voice",
        "audioPreprocessor": getattr(audio_preprocessor, "provider_name", None),
        "audioPreprocessorModel": getattr(audio_preprocessor, "provider_model", None),
        "vadProvider": getattr(vad_provider, "provider_name", None),
        "vadModel": getattr(vad_provider, "provider_model", None),
        "asrProvider": getattr(asr_provider, "provider_name", None),
        "asrModel": getattr(asr_provider, "provider_model", None),
        "diarizationProvider": getattr(diarization_provider, "provider_name", None),
        "diarizationModel": getattr(diarization_provider, "provider_model", None),
        "durationMs": audio.duration_ms,
        "sampleRateHz": audio.sample_rate_hz,
        "channelCount": audio.channel_count,
        "speechRegionCount": len(speech_regions),
        "speechRegions": [
            {"startMs": region.start_ms, "endMs": region.end_ms, "confidence": region.confidence}
            for region in speech_regions[:20]
        ],
        "warnings": _deduplicate_warnings(warnings),
    }


def _deduplicate_warnings(warnings: list[str]) -> list[str]:
    return list(dict.fromkeys(warning for warning in warnings if warning))
