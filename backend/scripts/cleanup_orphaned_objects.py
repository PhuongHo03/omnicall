import argparse

from minio import Minio
from sqlalchemy import select

from backend.configs.database import SessionLocal
from backend.configs.settings import get_settings
from backend.models.meeting_models import MeetingAsset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find MinIO objects that are not referenced by meeting_assets."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete detected orphaned objects. Without this flag the command only reports them.",
    )
    args = parser.parse_args()

    settings = get_settings()
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_secure,
    )
    with SessionLocal() as session:
        referenced_keys = set(session.scalars(select(MeetingAsset.object_key)).all())

    objects = [
        item.object_name
        for item in client.list_objects(settings.minio_bucket, recursive=True)
        if item.object_name not in referenced_keys
    ]

    print(f"bucket={settings.minio_bucket}")
    print(f"orphaned_objects={len(objects)}")
    print(f"mode={'apply' if args.apply else 'dry-run'}")
    for object_key in objects:
        print(object_key)

    if args.apply:
        for object_key in objects:
            client.remove_object(settings.minio_bucket, object_key)
        print(f"deleted_objects={len(objects)}")


if __name__ == "__main__":
    main()
