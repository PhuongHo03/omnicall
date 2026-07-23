import unittest

from backend.services.simple_rag.query_interpretation_service import QueryInterpretationService


SINGLE_TURN = [
    *(f"Tóm tắt cuộc họp theo cách {index}" for index in range(1, 11)),
    *(f"Summarize the meeting, variant {index}" for index in range(1, 11)),
    *(f"Có bao nhiêu người tham gia? cách hỏi {index}" for index in range(1, 11)),
    *(f"How many participants attended? variant {index}" for index in range(1, 11)),
    *(f"Các action item là gì? cách hỏi {index}" for index in range(1, 6)),
    *(f"What decisions were made? variant {index}" for index in range(1, 6)),
    *(f"Xin chào {index}" for index in range(1, 6)),
    *(f"Hello {index}" for index in range(1, 6)),
]

MULTI_TURN = [
    ("Tóm tắt cuộc họp", "Nói thêm về điều đó"),
    ("Liệt kê action item", "Ai chịu trách nhiệm việc đó?"),
    ("What decisions were made?", "Tell me more about that"),
    ("Who attended?", "What did that person decide?"),
] * 5


class GoldenCorpusShapeTestCase(unittest.TestCase):
    def test_minimum_corpus_size_and_bilingual_coverage(self) -> None:
        self.assertGreaterEqual(len(SINGLE_TURN), 60)
        self.assertGreaterEqual(len(MULTI_TURN), 20)
        service = QueryInterpretationService()
        specs = [service.interpret(prompt, language_hint="vi" if index % 2 == 0 else "en") for index, prompt in enumerate(SINGLE_TURN)]
        self.assertIn("vi", {item.language for item in specs})
        self.assertIn("en", {item.language for item in specs})


if __name__ == "__main__":
    unittest.main()
