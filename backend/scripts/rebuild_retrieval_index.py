import argparse

from sqlalchemy import delete, select

from backend.configs.database import SessionLocal
from backend.models.meeting_models import ChatMessage, MeetingIntelligenceResult
from backend.services.retrieval.index_service import RetrievalIndexService


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild meeting retrieval chunks and vectors from processed JSON results.")
    parser.add_argument("--meeting-id", help="Only rebuild one meeting.")
    parser.add_argument("--clear-chat", action="store_true", help="Delete chat messages that may cite stale chunk IDs.")
    args = parser.parse_args()

    with SessionLocal() as session:
        statement = select(MeetingIntelligenceResult).order_by(MeetingIntelligenceResult.created_at.asc())
        if args.meeting_id:
            statement = statement.where(MeetingIntelligenceResult.meeting_id == args.meeting_id)
        results = list(session.scalars(statement).all())

        if args.clear_chat:
            chat_delete = delete(ChatMessage)
            if args.meeting_id:
                chat_delete = chat_delete.where(ChatMessage.meeting_id == args.meeting_id)
            session.execute(chat_delete)
            session.commit()

        service = RetrievalIndexService(session)
        rebuilt = 0
        chunks = 0
        for result in results:
            if not _is_rag_first_schema(result.result_json):
                raise SystemExit(
                    "obsolete_intelligence_schema: reprocess meetings before rebuilding Phase 22 retrieval indexes"
                )
            indexed = service.rebuild_for_result(result)
            chunks += len(indexed)
            rebuilt += 1
            session.commit()

    print(f"rebuilt_results={rebuilt} rebuilt_chunks={chunks} clear_chat={args.clear_chat}")


def _is_rag_first_schema(result_json: dict) -> bool:
    if isinstance(result_json.get("knowledge"), dict):
        return all(key in result_json for key in ("evidence", "speakers", "summaries", "transcript"))
    return all(key in result_json for key in ("evidence", "speakers", "summaries", "facts", "events", "relationships"))


if __name__ == "__main__":
    main()
