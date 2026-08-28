from __future__ import annotations

import shutil
import stat
import subprocess
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from .constants import (
    DATASET_REPOSITORY,
    DATASET_REVISION,
    SUPPORT_ASSET_NAME,
    SUPPORT_ASSET_SHA256,
    SUPPORT_INDEX_SHA256,
    SUPPORT_RELEASE_TAG,
)
from .core.source import load_native_source_pin
from .jsonio import read_json, sha256_file

DISTRIBUTION_REPOSITORY = "neilashton/autocfd5-aiml-submission"


class FetchError(ValueError):
    """Raised when immutable input material cannot be fetched exactly."""


def _run(arguments: list[str]) -> None:
    executable = shutil.which(arguments[0])
    if executable is None:
        raise FetchError(f"required command is unavailable: {arguments[0]}")
    try:
        subprocess.run([executable, *arguments[1:]], check=True)
    except subprocess.CalledProcessError as error:
        raise FetchError(f"command failed with exit code {error.returncode}") from error


def _member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in name
    ):
        raise FetchError(f"support archive has an unsafe path: {name!r}")
    return path


def fetch_support(destination: Path | str, *, archive: Path | str | None = None) -> Path:
    root = Path(destination).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FetchError(f"support destination is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    downloaded = (
        Path(archive).expanduser().resolve() if archive else root.parent / SUPPORT_ASSET_NAME
    )
    if archive is None:
        if downloaded.exists():
            raise FetchError(f"refusing to overwrite existing archive: {downloaded}")
        _run(
            [
                "gh",
                "release",
                "download",
                SUPPORT_RELEASE_TAG,
                "--repo",
                DISTRIBUTION_REPOSITORY,
                "--pattern",
                SUPPORT_ASSET_NAME,
                "--dir",
                str(root.parent),
            ]
        )
    if SUPPORT_ASSET_SHA256.startswith("__") or sha256_file(downloaded) != SUPPORT_ASSET_SHA256:
        raise FetchError("profile-support archive differs from this evaluator build")
    with zipfile.ZipFile(downloaded, "r") as bundle:
        for info in bundle.infolist():
            relative = _member_path(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise FetchError("profile-support archive contains a symbolic link")
            target = root.joinpath(*relative.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info, "r") as source, target.open("xb") as sink:
                shutil.copyfileobj(source, sink, length=8 * 1024 * 1024)
    if sha256_file(root / "index.json") != SUPPORT_INDEX_SHA256:
        raise FetchError("extracted profile-support index differs")
    return root


def fetch_dataset_split(
    *,
    split_path: Path | str,
    native_source_pin: Path | str,
    destination: Path | str,
    dry_run: bool = False,
) -> None:
    split = read_json(split_path)
    case_ids = split.get("test_case_ids")
    if not isinstance(case_ids, list) or not case_ids:
        raise FetchError("split has no test cases")
    fetch_dataset_cases(
        case_ids=case_ids,
        native_source_pin=native_source_pin,
        destination=destination,
        dry_run=dry_run,
    )


def fetch_dataset_cases(
    *,
    case_ids: Sequence[str],
    native_source_pin: Path | str,
    destination: Path | str,
    dry_run: bool = False,
) -> None:
    if (
        not case_ids
        or any(not isinstance(case_id, str) for case_id in case_ids)
        or len(case_ids) != len(set(case_ids))
    ):
        raise FetchError("test case IDs must be a non-empty unique sequence")
    pin = load_native_source_pin(native_source_pin)
    filenames = ["force_mom_constref_all.csv"]
    for case_id in case_ids:
        case = pin.case(case_id)
        filenames.extend(
            [
                case.boundary.path.as_posix(),
                case.surface_cell_area.path.as_posix(),
                *(part.path.as_posix() for part in case.volume_parts),
            ]
        )
    arguments = [
        "hf",
        "download",
        DATASET_REPOSITORY,
        *filenames,
        "--type",
        "dataset",
        "--revision",
        DATASET_REVISION,
        "--local-dir",
        str(Path(destination).expanduser().resolve()),
    ]
    if dry_run:
        arguments.append("--dry-run")
    _run(arguments)


__all__ = ["FetchError", "fetch_dataset_cases", "fetch_dataset_split", "fetch_support"]
