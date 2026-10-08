#!/usr/bin/env python3
"""Validate a read-only database and create a task-local KaryoScope registry."""

import argparse
import shutil
from pathlib import Path

from karyoscope.installed import InstalledRecord, now_iso, record_install
from karyoscope.manifest import validate_database_layout


def prepare_database(source: Path, root: Path, db_id: str, features: list[str]) -> None:
    source = source.resolve(strict=True)
    manifest = validate_database_layout(source)
    if manifest.id != db_id:
        raise ValueError(f"Requested database {db_id!r}, but manifest declares {manifest.id!r}.")
    missing = set(features) - set(manifest.feature_sets)
    if missing:
        raise ValueError(f"Feature sets absent from {db_id}: {', '.join(sorted(missing))}.")

    root.mkdir()
    # register resolves symlinks and requires physical containment. Use KaryoScope's
    # registry API so tasks can read a shared index without copying or modifying it.
    (root / db_id).symlink_to(source, target_is_directory=True)
    record_install(
        root,
        db_id,
        InstalledRecord(
            version=manifest.version,
            installed_at=now_iso(),
            source_url="local",
            source_sha256="",
            directory=db_id,
        ),
    )
    shutil.copyfile(source / "manifest.yaml", "database_manifest.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--feature-set", action="append", default=[])
    args = parser.parse_args()
    prepare_database(args.source, args.root, args.db, args.feature_set)


if __name__ == "__main__":
    main()
