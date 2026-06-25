MODEL_CACHE_DIR = "/models"
VOICE_FFMPEG_PATH = "ffmpeg"
VOICE_WORK_DIR = "/tmp/omnicall-audio"

ASR_MODEL = "whisper-small-int8"
ASR_COMPUTE_TYPE = "int8"
ASR_COMMAND = (
    "python -m backend.model_runners.asr "
    "--audio-path {audio_path} "
    f"--model-dir {MODEL_CACHE_DIR}/asr "
    f"--model-name {ASR_MODEL} "
    f"--compute-type {ASR_COMPUTE_TYPE}"
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
