#!/usr/bin/env python3
"""Build the deterministic submission ZIP for the FictionForge Stage 4 submission.

Runs ``validate_submission.validate`` first; the ZIP is only written when the
manifest passes all rules (R1-R7).  Entries are stored at the archive root with
a fixed timestamp so the same tree always produces the same ZIP bytes and the
same SHA-256 checksum (``<output>.sha256``, sha256sum format).

No network, no LLM, no randomness.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_submission import validate, format_report

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_MODE = 0o644 << 16


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_zip(root: Path, files: list[str], tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            info = zipfile.ZipInfo(rel, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ZIP_MODE
            info.create_system = 0
            zf.writestr(info, (root / rel).read_bytes())


def _verify_zip(zip_path: Path, root: Path, files: list[str]) -> str | None:
    """Return an error message, or None if the archive round-trips correctly."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return f"zip integrity check failed at {bad}"
            names = zf.namelist()
            if names != files:
                return f"zip namelist does not match packaged files ({len(names)} != {len(files)})"
            for rel in files:
                zipped = hashlib.sha256(zf.read(rel)).hexdigest()
                disk = _sha256_file(root / rel)
                if zipped != disk:
                    return f"SHA-256 mismatch for {rel}: zip {zipped} != disk {disk}"
    except zipfile.BadZipFile as exc:
        return f"output is not a valid zip: {exc}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="submission root (default: repo root)")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="zip output path (default: <root.parent>/fictionforge_stage4_submission.zip)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = (args.output or root.parent / "fictionforge_stage4_submission.zip").resolve()

    report = validate(root)
    if not report.ok:
        print(format_report(report))
        return 1

    files = report.package_files
    output.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent)
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
        _build_zip(root, files, tmp_path)
        os.replace(tmp_path, output)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    problem = _verify_zip(output, root, files)
    if problem:
        print(f"Verification failed: {problem}", file=sys.stderr)
        output.unlink(missing_ok=True)
        return 1

    digest = _sha256_file(output)
    sha_path = output.parent / (output.name + ".sha256")
    sha_path.write_text(f"{digest}  {output.name}\n", encoding="utf-8")

    size = output.stat().st_size
    print(f"Packaged {len(files)} files")
    print(f"ZIP:      {output}")
    print(f"Size:     {size} bytes")
    print(f"SHA-256:  {digest}")
    print(f"Checksum: {sha_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
