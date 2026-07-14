from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Omnicall API", alias="APP_NAME")
    environment: str = Field(default="local", alias="APP_ENV")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")

    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="omnicall", alias="POSTGRES_DB")
    postgres_user: str = Field(default="omnicall", alias="POSTGRES_USER")
    postgres_password: str = Field(default="change-me", alias="POSTGRES_PASSWORD")

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: str = Field(default="change-me", alias="REDIS_PASSWORD")
    redis_processing_lock_ttl_seconds: int = Field(default=900, alias="REDIS_PROCESSING_LOCK_TTL_SECONDS")
    admin_metrics_cache_key: str = Field(default="admin:metrics:snapshot", alias="ADMIN_METRICS_CACHE_KEY")
    admin_metrics_cache_ttl_seconds: int = Field(default=10, alias="ADMIN_METRICS_CACHE_TTL_SECONDS")
    operational_log_stream_key: str = Field(default="admin:logs:operational", alias="OPERATIONAL_LOG_STREAM_KEY")
    operational_log_max_length: int = Field(default=1000, alias="OPERATIONAL_LOG_MAX_LENGTH")
    operational_log_ttl_seconds: int = Field(default=86400, alias="OPERATIONAL_LOG_TTL_SECONDS")
    operational_log_default_tail: int = Field(default=100, alias="OPERATIONAL_LOG_DEFAULT_TAIL")
    auth_session_ttl_hours: int = Field(default=168, alias="AUTH_SESSION_TTL_HOURS")

    rabbitmq_host: str = Field(default="rabbitmq", alias="RABBITMQ_HOST")
    rabbitmq_port: int = Field(default=5672, alias="RABBITMQ_PORT")
    rabbitmq_user: str = Field(default="omnicall", alias="RABBITMQ_USER")
    rabbitmq_password: str = Field(default="change-me", alias="RABBITMQ_PASSWORD")
    processing_reconciliation_interval_seconds: int = Field(
        default=60,
        alias="PROCESSING_RECONCILIATION_INTERVAL_SECONDS",
    )
    processing_reconciliation_stale_seconds: int = Field(
        default=120,
        alias="PROCESSING_RECONCILIATION_STALE_SECONDS",
    )
    processing_reconciliation_batch_size: int = Field(
        default=100,
        alias="PROCESSING_RECONCILIATION_BATCH_SIZE",
    )

    minio_host: str = Field(default="minio", alias="MINIO_HOST")
    minio_port: int = Field(default=9000, alias="MINIO_PORT")
    minio_root_user: str = Field(default="omnicall", alias="MINIO_ROOT_USER")
    minio_root_password: str = Field(default="change-me", alias="MINIO_ROOT_PASSWORD")
    minio_bucket: str = Field(default="omnicall-meetings", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    upload_max_bytes: int = Field(default=524288000, alias="UPLOAD_MAX_BYTES")
    upload_allowed_extensions: list[str] = Field(
        default_factory=lambda: [".aac", ".m4a", ".mp3", ".mp4", ".wav", ".webm"],
        alias="UPLOAD_ALLOWED_EXTENSIONS",
    )
    upload_allowed_content_types: list[str] = Field(
        default_factory=lambda: [
            "audio/aac",
            "audio/m4a",
            "audio/mpeg",
            "audio/mp4",
            "audio/wav",
            "audio/webm",
            "video/mp4",
            "video/webm",
        ],
        alias="UPLOAD_ALLOWED_CONTENT_TYPES",
    )

    vad_min_speech_ms: int = Field(default=300, alias="VAD_MIN_SPEECH_MS")
    vad_silence_gap_ms: int = Field(default=500, alias="VAD_SILENCE_GAP_MS")
    vad_energy_threshold: float = Field(default=0.012, alias="VAD_ENERGY_THRESHOLD")
    asr_timeout_seconds: float = Field(default=120.0, alias="ASR_TIMEOUT_SECONDS")
    asr_timeout_realtime_factor: float = Field(default=1.0, alias="ASR_TIMEOUT_REALTIME_FACTOR")
    asr_model: str = Field(default="whisper-medium", alias="ASR_MODEL")
    asr_compute_type: str = Field(default="int8", alias="ASR_COMPUTE_TYPE")
    asr_beam_size: int = Field(default=5, alias="ASR_BEAM_SIZE")
    asr_language: str = Field(default="auto", alias="ASR_LANGUAGE")
    embedding_model: str = Field(default="nomic-embed-text", alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=768, alias="EMBEDDING_DIMENSIONS")
    embedding_timeout_seconds: float = Field(default=30.0, alias="EMBEDDING_TIMEOUT_SECONDS")
    embedding_batch_size: int = Field(default=16, alias="EMBEDDING_BATCH_SIZE")
    embedding_max_retries: int = Field(default=2, alias="EMBEDDING_MAX_RETRIES")
    embedding_retry_backoff_seconds: float = Field(default=0.2, alias="EMBEDDING_RETRY_BACKOFF_SECONDS")
    embedding_contract_version: str = Field(default="v1", alias="EMBEDDING_CONTRACT_VERSION")
    rerank_top_k: int = Field(default=12, alias="RERANK_TOP_K")
    rerank_output_k: int = Field(default=6, alias="RERANK_OUTPUT_K")
    rerank_timeout_seconds: float = Field(default=30.0, alias="RERANK_TIMEOUT_SECONDS")
    retrieval_fallback_candidate_limit: int = Field(default=48, alias="RETRIEVAL_FALLBACK_CANDIDATE_LIMIT")
    retrieval_trigram_threshold: float = Field(default=0.12, alias="RETRIEVAL_TRIGRAM_THRESHOLD")
    guardrail_model: str = Field(default="llama-guard3:1b", alias="GUARDRAIL_MODEL")
    guardrail_timeout_seconds: float = Field(default=20.0, alias="GUARDRAIL_TIMEOUT_SECONDS")
    guardrail_max_retries: int = Field(default=1, alias="GUARDRAIL_MAX_RETRIES")
    guardrail_input_enabled: bool = Field(default=True, alias="GUARDRAIL_INPUT_ENABLED")
    guardrail_output_enabled: bool = Field(default=True, alias="GUARDRAIL_OUTPUT_ENABLED")
    guardrail_strict_mode: bool = Field(default=False, alias="GUARDRAIL_STRICT_MODE")
    guardrail_pii_redaction_enabled: bool = Field(default=True, alias="GUARDRAIL_PII_REDACTION_ENABLED")
    vector_provider: str = Field(default="milvus", alias="VECTOR_PROVIDER")
    milvus_host: str = Field(default="milvus", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, alias="MILVUS_PORT")
    milvus_collection: str = Field(default="meeting_chunks", alias="MILVUS_COLLECTION")

    llm_provider: str = Field(default="endpoint", alias="LLM_PROVIDER")
    llm_api_base_url: str = Field(default="http://localhost:8001/v1", alias="LLM_API_BASE_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    llm_endpoint_compatibility: str = Field(default="openai", alias="LLM_ENDPOINT_COMPATIBILITY")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=1, alias="LLM_MAX_RETRIES")
    llm_retry_backoff_seconds: float = Field(default=0.2, alias="LLM_RETRY_BACKOFF_SECONDS")
    llm_fallback_provider: str = Field(default="ollama", alias="LLM_FALLBACK_PROVIDER")
    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:1.5b", alias="OLLAMA_MODEL")
    ollama_llm_timeout_seconds: float = Field(default=600.0, alias="OLLAMA_LLM_TIMEOUT_SECONDS")
    ollama_context_length: int = Field(default=8192, alias="OLLAMA_CONTEXT_LENGTH")
    extraction_window_target_tokens: int = Field(default=2000, alias="EXTRACTION_WINDOW_TARGET_TOKENS")
    extraction_window_hard_limit_tokens: int = Field(default=2800, alias="EXTRACTION_WINDOW_HARD_LIMIT_TOKENS")
    extraction_window_overlap_segments: int = Field(default=1, alias="EXTRACTION_WINDOW_OVERLAP_SEGMENTS")
    extraction_window_max_workers: int = Field(default=4, alias="EXTRACTION_WINDOW_MAX_WORKERS")
    prometheus_url: str = Field(default="http://prometheus:9090", alias="PROMETHEUS_URL")

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_auth_per_minute: int = Field(default=20, alias="RATE_LIMIT_AUTH_PER_MINUTE")
    rate_limit_meetings_per_minute: int = Field(default=300, alias="RATE_LIMIT_MEETINGS_PER_MINUTE")
    rate_limit_admin_per_minute: int = Field(default=180, alias="RATE_LIMIT_ADMIN_PER_MINUTE")
    rate_limit_public_per_minute: int = Field(default=10, alias="RATE_LIMIT_PUBLIC_PER_MINUTE")

    # Concurrency limiting
    concurrency_limit_per_account: int = Field(default=5, alias="CONCURRENCY_LIMIT_PER_ACCOUNT")
    concurrency_limit_meetings: int = Field(default=5, alias="CONCURRENCY_LIMIT_MEETINGS")
    concurrency_limit_admin: int = Field(default=3, alias="CONCURRENCY_LIMIT_ADMIN")
    concurrency_limit_auth: int = Field(default=3, alias="CONCURRENCY_LIMIT_AUTH")

    # Task guard
    task_limit_per_meeting: int = Field(default=2, alias="TASK_LIMIT_PER_MEETING")
    task_limit_per_user: int = Field(default=5, alias="TASK_LIMIT_PER_USER")

    # Circuit breaker
    circuit_breaker_enabled: bool = Field(default=True, alias="CIRCUIT_BREAKER_ENABLED")
    circuit_breaker_failure_threshold: int = Field(default=5, alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    circuit_breaker_recovery_seconds: int = Field(default=30, alias="CIRCUIT_BREAKER_RECOVERY_SECONDS")

    # Agentic RAG
    agentic_rag_max_iterations: int = Field(default=2, alias="AGENTIC_RAG_MAX_ITERATIONS")
    agentic_rag_max_replans: int = Field(default=1, alias="AGENTIC_RAG_MAX_REPLANS")
    agentic_rag_max_tool_calls_per_iteration: int = Field(default=4, alias="AGENTIC_RAG_MAX_TOOL_CALLS_PER_ITERATION")
    agentic_rag_max_chunks_per_tool: int = Field(default=5, alias="AGENTIC_RAG_MAX_CHUNKS_PER_TOOL")
    agentic_rag_max_total_chunks: int = Field(default=12, alias="AGENTIC_RAG_MAX_TOTAL_CHUNKS")
    agentic_rag_iteration_timeout_seconds: float = Field(default=30.0, alias="AGENTIC_RAG_ITERATION_TIMEOUT_SECONDS")
    agentic_rag_total_timeout_seconds: float = Field(default=60.0, alias="AGENTIC_RAG_TOTAL_TIMEOUT_SECONDS")
    agentic_rag_max_context_tokens: int = Field(default=4000, alias="AGENTIC_RAG_MAX_CONTEXT_TOKENS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @computed_field
    @property
    def database_url(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def rabbitmq_url(self) -> str:
        user = quote_plus(self.rabbitmq_user)
        password = quote_plus(self.rabbitmq_password)
        return f"amqp://{user}:{password}@{self.rabbitmq_host}:{self.rabbitmq_port}//"

    @computed_field
    @property
    def redis_url(self) -> str:
        password = quote_plus(self.redis_password)
        return f"redis://:{password}@{self.redis_host}:{self.redis_port}/0"

    @computed_field
    @property
    def minio_endpoint(self) -> str:
        return f"{self.minio_host}:{self.minio_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
