"""Verify processable local meetings, v2 results, and derived chunk consistency."""

from sqlalchemy import select

from backend.configs.database import SessionLocal
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import Meeting, MeetingAsset, MeetingChunkRecord, MeetingIntelligenceResult


def main() -> None:
    with SessionLocal() as session:
        meetings = list(session.scalars(select(Meeting).order_by(Meeting.created_at.asc())).all())
        assets = {asset.meeting_id for asset in session.scalars(select(MeetingAsset)).all() if asset.meeting_id}
        results = list(session.scalars(select(MeetingIntelligenceResult)).all())
        chunks = list(session.scalars(select(MeetingChunkRecord)).all())
        by_meeting = {result.meeting_id: result for result in results}
        processable = [meeting for meeting in meetings if meeting.id in assets]
        failures = []
        identity_relationships = 0
        for meeting in processable:
            result = by_meeting.get(meeting.id)
            if meeting.status != MeetingStatus.READY or result is None or result.schema_version != "meeting-intelligence-result.v2":
                failures.append(f"{meeting.id}: status={meeting.status} schema={getattr(result, 'schema_version', None)}")
                continue
            payload = result.result_json or {}
            records = {
                record.get("id")
                for record in payload.get("knowledge", {}).get("records", [])
                if isinstance(record, dict)
            }
            for relationship in payload.get("knowledge", {}).get("relationships", []):
                if not isinstance(relationship, dict):
                    failures.append(f"{meeting.id}: non-object relationship")
                    continue
                if relationship.get("subtype") == "identity_resolution":
                    identity_relationships += 1
                for endpoint_name in ("from", "to"):
                    endpoint = relationship.get(endpoint_name)
                    if not isinstance(endpoint, dict) or endpoint.get("id") not in records:
                        failures.append(f"{meeting.id}: invalid relationship {relationship.get('id')}")
        result_ids = {result.id for result in results}
        orphan_chunks = [chunk.chunk_id for chunk in chunks if chunk.intelligence_result_id not in result_ids]
        print({"meetings": len(meetings), "processable": len(processable), "v2Results": len(results), "chunks": len(chunks), "identityRelationships": identity_relationships, "orphanChunks": orphan_chunks, "failures": failures})
        if failures or orphan_chunks:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
