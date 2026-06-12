from uuid import uuid4

from redis import Redis

from backend.configs.settings import Settings, get_settings


class RedisLockProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)

    def acquire(self, key: str, ttl_seconds: int | None = None) -> str | None:
        token = str(uuid4())
        locked = self.client.set(
            key,
            token,
            nx=True,
            ex=ttl_seconds or self.settings.redis_processing_lock_ttl_seconds,
        )
        return token if locked else None

    def release(self, key: str, token: str) -> None:
        release_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.client.eval(release_script, 1, key, token)


def get_redis_lock_provider() -> RedisLockProvider:
    return RedisLockProvider(get_settings())
