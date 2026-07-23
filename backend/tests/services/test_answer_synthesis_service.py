import unittest

from backend.configs.settings import Settings
from backend.providers.contracts.llm import LLMProviderError
from backend.services.simple_rag.answer_synthesis_service import AnswerSynthesisService
from backend.services.simple_rag.contracts import GoalSpec, SynthesisContract


class SequenceProvider:
    provider_name = "sequence"
    model_name = "test-model"

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0
        self.calls_kwargs = []

    def generate_json(self, **_kwargs):
        self.calls += 1
        self.calls_kwargs.append(_kwargs)
        value = self.payloads.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _settings() -> Settings:
    return Settings(_env_file=None, CHAT_TURN_LEASE_SECONDS=300, RAG_SYNTHESIS_CONTRACT_RETRIES=1)


class AnswerSynthesisServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        from backend.providers.llm.provider import _LLM_BREAKERS

        _LLM_BREAKERS.clear()

    def test_contract_failure_retries_exactly_once(self) -> None:
        provider = SequenceProvider([
            {"answer": "", "claims": []},
            {"answer": "Xin chào!", "claims": []},
        ])
        contract = SynthesisContract(
            "vi",
            "short",
            (GoalSpec("goal-1", "direct", "greeting"),),
            (),
            (),
            (),
            direct_intent="greeting",
        )

        payload, verification, _snapshot, attempts = AnswerSynthesisService(provider, _settings()).synthesize(contract)

        self.assertEqual(payload["answer"], "Xin chào!")
        self.assertTrue(verification.passed)
        self.assertEqual(attempts, 2)
        self.assertEqual(provider.calls, 2)

    def test_transport_failure_does_not_consume_contract_retry(self) -> None:
        provider = SequenceProvider([LLMProviderError("offline")])
        contract = SynthesisContract(
            "en",
            "short",
            (GoalSpec("goal-1", "direct", "greeting"),),
            (),
            (),
            (),
            direct_intent="greeting",
        )

        with self.assertRaises(LLMProviderError):
            AnswerSynthesisService(provider, _settings()).synthesize(contract)

        self.assertEqual(provider.calls, 1)

    def test_direct_contract_forbids_meeting_claims_in_the_prompt(self) -> None:
        provider = SequenceProvider([{"answer": "Xin chào!", "claims": []}])
        contract = SynthesisContract(
            "vi", "short", (GoalSpec("goal-1", "direct", "greeting"),), (), (), (), direct_intent="greeting"
        )

        AnswerSynthesisService(provider, _settings()).synthesize(contract)

        self.assertIn("exactly an empty claims array", provider.calls_kwargs[0]["system_prompt"])
        self.assertIn("Vietnamese only", provider.calls_kwargs[0]["system_prompt"])

    def test_prompt_keeps_citation_ids_out_of_model_contract(self) -> None:
        provider = SequenceProvider([{"answer": "Xin chào!", "claims": []}])
        contract = SynthesisContract(
            "vi", "short", (GoalSpec("goal-1", "direct", "greeting"),), (), (), ("cite-001",), direct_intent="greeting"
        )

        AnswerSynthesisService(provider, _settings()).synthesize(contract)

        self.assertNotIn("allowedRefs", provider.calls_kwargs[0]["user_prompt"])
        self.assertIn("Do not return citation IDs", provider.calls_kwargs[0]["system_prompt"])

    def test_language_mismatch_retries_with_explicit_script_instruction(self) -> None:
        provider = SequenceProvider([
            {"answer": "你好", "claims": []},
            {"answer": "Xin chào!", "claims": []},
        ])
        contract = SynthesisContract(
            "vi", "short", (GoalSpec("goal-1", "direct", "greeting"),), (), (), (), direct_intent="greeting"
        )

        _payload, verification, _snapshot, attempts = AnswerSynthesisService(provider, _settings()).synthesize(contract)

        self.assertTrue(verification.passed)
        self.assertEqual(attempts, 2)
        self.assertIn("normal writing system", provider.calls_kwargs[1]["system_prompt"])


if __name__ == "__main__":
    unittest.main()
