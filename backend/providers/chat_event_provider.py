import json
from typing import Any

from redis import Redis, RedisError

from backend.configs.settings import Settings, get_settings


class ChatEventProvider:
    def publish(self, channel: str, event: dict[str, Any]) -> None:
        raise NotImplementedError

    def subscribe(self, channel: str) -> Any:
        raise NotImplementedError


class RedisChatEventProvider(ChatEventProvider):
    def __init__(self, settings: Settings) -> None:
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        try:
            self.client.publish(channel, json.dumps(event))
        except RedisError:
            pass

    def subscribe(self, channel: str) -> Any:
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        return pubsub


def get_chat_event_provider() -> ChatEventProvider:
    return RedisChatEventProvider(get_settings())
