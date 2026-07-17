from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_URL = (
    "https://browse.wf/"
    "warframe-public-export-plus/"
    "ExportWeapons.json"
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "ExportWeapons.json"
DEFAULT_BACKUP = PROJECT_ROOT / "data" / "raw" / "backups"


class WeaponDataDownloadError(RuntimeError):
    """Raised when the weapon dataset cannot be downloaded or validated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _validate_weapon_export(data: object) -> int:
    if not isinstance(data, dict):
        raise WeaponDataDownloadError(
            "ExportWeapons.json must contain a JSON object at its root."
        )

    if not data:
        raise WeaponDataDownloadError(
            "ExportWeapons.json was downloaded, but it is empty."
        )

    weapon_like_entries = 0

    for value in data.values():
        if not isinstance(value, dict):
            continue

        if any(
            key in value
            for key in (
                "uniqueName",
                "name",
                "productCategory",
                "behaviours",
            )
        ):
            weapon_like_entries += 1

    if weapon_like_entries == 0:
        raise WeaponDataDownloadError(
            "The JSON is valid, but no weapon-like entries were detected."
        )

    return weapon_like_entries


def _create_backup(output_path: Path, backup_directory: Path) -> Path | None:
    if not output_path.exists():
        return None

    backup_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_directory / f"ExportWeapons_{timestamp}.json"

    shutil.copy2(output_path, backup_path)
    return backup_path


def download_weapon_export(
    *,
    url: str = DEFAULT_URL,
    output_path: Path = DEFAULT_OUTPUT,
    backup_directory: Path = DEFAULT_BACKUP,
    timeout_seconds: int = 60,
    keep_backup: bool = True,
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = output_path.with_suffix(".json.tmp")

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Warframe-Weapon-Optimization-Assistant/"
                "weapon-data-downloader"
            )
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except HTTPError as error:
        raise WeaponDataDownloadError(
            f"Server returned HTTP {error.code} while downloading {url}"
        ) from error
    except URLError as error:
        raise WeaponDataDownloadError(
            f"Could not connect to the weapon data source: {error.reason}"
        ) from error
    except TimeoutError as error:
        raise WeaponDataDownloadError(
            f"Download exceeded the {timeout_seconds}-second timeout."
        ) from error

    try:
        decoded = payload.decode("utf-8")
        data = json.loads(decoded)
    except UnicodeDecodeError as error:
        raise WeaponDataDownloadError(
            "The downloaded file is not valid UTF-8."
        ) from error
    except json.JSONDecodeError as error:
        raise WeaponDataDownloadError(
            "The downloaded file is not valid JSON."
        ) from error

    weapon_like_entries = _validate_weapon_export(data)

    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    new_hash = _sha256(temporary_path)
    old_hash = _sha256(output_path) if output_path.exists() else None

    if old_hash == new_hash:
        temporary_path.unlink(missing_ok=True)

        return {
            "status": "unchanged",
            "output_path": str(output_path),
            "weapon_like_entries": weapon_like_entries,
            "sha256": new_hash,
            "backup_path": None,
        }

    backup_path = None

    if keep_backup:
        backup_path = _create_backup(output_path, backup_directory)

    temporary_path.replace(output_path)

    metadata = {
        "source_url": url,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_path": str(output_path),
        "weapon_like_entries": weapon_like_entries,
        "sha256": new_hash,
        "previous_sha256": old_hash,
        "backup_path": str(backup_path) if backup_path else None,
    }

    metadata_path = output_path.with_name("ExportWeapons.metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "status": "updated" if old_hash else "downloaded",
        **metadata,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download and validate Warframe ExportWeapons.json "
            "for later normalization."
        )
    )

    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Source URL for ExportWeapons.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination path for the raw JSON file.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP,
        help="Directory used for previous-version backups.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Download timeout in seconds.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Replace an existing dataset without preserving a backup.",
    )

    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        result = download_weapon_export(
            url=args.url,
            output_path=args.output,
            backup_directory=args.backup_dir,
            timeout_seconds=args.timeout,
            keep_backup=not args.no_backup,
        )
    except WeaponDataDownloadError as error:
        print(f"Weapon data download failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
