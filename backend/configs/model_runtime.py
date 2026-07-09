MODEL_CACHE_DIR = "/models"
VOICE_FFMPEG_PATH = "ffmpeg"
VOICE_WORK_DIR = "/tmp/omnicall-audio"

ASR_MODEL = "whisper-medium"
ASR_COMPUTE_TYPE = "int8"
ASR_BEAM_SIZE = 5
ASR_LANGUAGE = "auto"

ASR_COMMAND = (
    "python -m backend.model_runners.asr "
    "--audio-path {audio_path} "
    f"--model-dir {MODEL_CACHE_DIR}/asr "
    f"--model-name {ASR_MODEL} "
    f"--compute-type {ASR_COMPUTE_TYPE} "
    f"--beam-size {ASR_BEAM_SIZE} "
    f"--language {ASR_LANGUAGE}"
)


def build_asr_command(
    audio_path_placeholder: str = "{audio_path}",
    *,
    model_name: str = ASR_MODEL,
    compute_type: str = ASR_COMPUTE_TYPE,
    beam_size: int = ASR_BEAM_SIZE,
    language: str = ASR_LANGUAGE,
) -> str:
    return (
        "python -m backend.model_runners.asr "
        f"--audio-path {audio_path_placeholder} "
        f"--model-dir {MODEL_CACHE_DIR}/asr "
        f"--model-name {model_name} "
        f"--compute-type {compute_type} "
        f"--beam-size {beam_size} "
        f"--language {language}"
    )


DIARIZATION_MODEL = "wespeaker-voxceleb-resnet34"
DIARIZATION_COMMAND = (
    "python -m backend.model_runners.diarization "
    "--audio-path {audio_path} "
    f"--model-dir {MODEL_CACHE_DIR}/diarization "
    "--device cpu"
)

RERANK_MODEL = "bge-reranker-v2-m3"
RERANK_COMMAND = (
    "python -m backend.model_runners.rerank "
    f"--model-dir {MODEL_CACHE_DIR}/rerank "
    f"--model-name {RERANK_MODEL}"
)
