import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.configs.settings import Settings
from backend.providers.rerank_provider import LocalModelRerankProvider, RerankProviderError


class RerankProviderTestCase(unittest.TestCase):
    def test_local_model_reranker_reads_ranked_ids_from_command_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            script_path = Path(tmp_dir) / "fake_rerank.py"
            script_path.write_text(
                "import json, sys\n"
                "payload = json.load(sys.stdin)\n"
                "ids = [item['chunkId'] for item in payload['chunks']]\n"
                "print(json.dumps({'rankedChunkIds': list(reversed(ids))}))\n",
                encoding="utf-8",
            )
            provider = LocalModelRerankProvider(
                Settings(),
                command_template=f"{sys.executable} {script_path}",
                model_name="fake-bge-reranker",
            )
            transcript = _item("transcript-001", "deadline follow up", priority=400, score=0.95)
            structured = _item("analysis.actionItems-001", "deadline follow up", priority=50, score=0.91)

            results = provider.rerank(
                query="deadline follow up",
                chunks=[transcript, structured],
                output_k=2,
            )

        self.assertEqual([item.record.chunk_id for item in results], ["analysis.actionItems-001", "transcript-001"])
        self.assertEqual(provider.model_name, "fake-bge-reranker")

    def test_local_model_reranker_reports_command_failure(self) -> None:
        provider = LocalModelRerankProvider(Settings(), command_template="missing-rerank-command")

        with self.assertRaisesRegex(RerankProviderError, "could not start"):
            provider.rerank(
                query="risk owner",
                chunks=[_item("analysis.risks-001", "risk owner", priority=50, score=0.91)],
                output_k=1,
            )

    def test_local_model_reranker_converts_timeout_to_fallback_error(self) -> None:
        provider = LocalModelRerankProvider(Settings())

        with patch(
            "backend.providers.rerank_provider.subprocess.run",
            side_effect=subprocess.TimeoutExpired("rerank", timeout=30),
        ):
            with self.assertRaisesRegex(RerankProviderError, "timed out"):
                provider.rerank(
                    query="price",
                    chunks=[_item("fact-price", "monthly cost is $83", priority=30, score=0.9)],
                    output_k=1,
                )


def _item(chunk_id: str, text: str, *, priority: int, score: float):
    return SimpleNamespace(
        score=score,
        record=SimpleNamespace(
            chunk_id=chunk_id,
            text=text,
            source_type="structured" if chunk_id.startswith("analysis.") else "transcript",
            section_type=chunk_id.rsplit("-", 1)[0],
            metadata_json={"priority": priority},
        ),
    )


if __name__ == "__main__":
    unittest.main()
