"""Tests for zip and wheel safe archive extraction."""

import io
import stat
import zipfile
from pathlib import Path

import pytest

from app.archives.errors import ArchiveLimitExceededError, UnsafeArchiveError
from app.archives.extract import ExtractionLimits, extract_archive
from app.archives.models import EntryKind


def make_zip(entries: dict[str, bytes | None], filename: str = "sample-1.0.0.whl") -> bytes:
    """Create an in-memory zip/whl file with the given entries.

    If an entry value is None, it is treated as a directory.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, data in entries.items():
            if data is None:
                # Directory entry
                dir_path = path.rstrip("/") + "/"
                zf.writestr(dir_path, "")
            else:
                zf.writestr(path, data)
    return buffer.getvalue()


def test_extract_wheel_archive(tmp_path: Path):
    dest = tmp_path / "extracted"
    archive_path = tmp_path / "mypkg-0.1.0-py3-none-any.whl"

    archive_content = make_zip(
        {
            "mypkg/__init__.py": b"# init\n__version__ = '0.1.0'\n",
            "mypkg/core.py": b"def hello():\n    return 'world'\n",
            "mypkg-0.1.0.dist-info/METADATA": (
                b"Metadata-Version: 2.1\nName: mypkg\nVersion: 0.1.0\n"
            ),
        }
    )
    archive_path.write_bytes(archive_content)

    inventory = extract_archive(archive_path, dest)

    assert inventory.archive_size_bytes == len(archive_content)
    assert len(inventory.entries) == 3
    paths = {e.path for e in inventory.entries}
    assert "mypkg/__init__.py" in paths
    assert "mypkg/core.py" in paths
    assert "mypkg-0.1.0.dist-info/METADATA" in paths

    # Verify extracted file exists and permissions are private non-executable (0600)
    core_file = dest / "mypkg" / "core.py"
    assert core_file.exists()
    assert core_file.read_bytes() == b"def hello():\n    return 'world'\n"
    assert stat.S_IMODE(core_file.stat().st_mode) == 0o600

    # Ensure all are REGULAR kind
    for e in inventory.entries:
        assert e.kind == EntryKind.REGULAR


def test_extract_zip_with_common_root(tmp_path: Path):
    dest = tmp_path / "extracted"
    archive_path = tmp_path / "mypkg-0.1.0.zip"

    archive_content = make_zip(
        {
            "mypkg-0.1.0/": None,
            "mypkg-0.1.0/setup.py": b"# setup",
            "mypkg-0.1.0/mypkg/core.py": b"# core",
        }
    )
    archive_path.write_bytes(archive_content)

    inventory = extract_archive(archive_path, dest)
    assert inventory.archive_root == "mypkg-0.1.0"
    paths = {e.path for e in inventory.entries}
    assert "setup.py" in paths
    assert "mypkg/core.py" in paths
    assert (dest / "setup.py").exists()


def test_reject_zip_path_traversal(tmp_path: Path):
    dest = tmp_path / "extracted"
    archive_path = tmp_path / "traversal.whl"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("../../etc/passwd", b"root:x:0:0")
    archive_path.write_bytes(buffer.getvalue())

    with pytest.raises(UnsafeArchiveError, match=r"parent reference"):
        extract_archive(archive_path, dest)


def test_reject_zip_absolute_path(tmp_path: Path):
    dest = tmp_path / "extracted"
    archive_path = tmp_path / "abs.whl"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("/root/secret.txt", b"secret")
    archive_path.write_bytes(buffer.getvalue())

    with pytest.raises(UnsafeArchiveError, match=r"absolute|unsafe"):
        extract_archive(archive_path, dest)


def test_reject_zip_duplicate_entries(tmp_path: Path):
    dest = tmp_path / "extracted"
    archive_path = tmp_path / "dup.whl"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("pkg/module.py", b"first")
        zf.writestr("pkg/module.py", b"second")
    archive_path.write_bytes(buffer.getvalue())

    with pytest.raises(UnsafeArchiveError, match=r"Duplicate entry"):
        extract_archive(archive_path, dest)


def test_reject_zip_entry_count_limit(tmp_path: Path):
    dest = tmp_path / "extracted"
    archive_path = tmp_path / "many.whl"

    archive_content = make_zip({f"file_{i}.txt": b"ok" for i in range(15)})
    archive_path.write_bytes(archive_content)

    limits = ExtractionLimits(max_entries=10)
    with pytest.raises(ArchiveLimitExceededError, match=r"Archive has more than"):
        extract_archive(archive_path, dest, limits=limits)


def test_reject_zip_file_size_limit(tmp_path: Path):
    dest = tmp_path / "extracted"
    archive_path = tmp_path / "large.whl"

    archive_content = make_zip({"large.bin": b"x" * 200})
    archive_path.write_bytes(archive_content)

    limits = ExtractionLimits(max_file_bytes=100)
    with pytest.raises(ArchiveLimitExceededError, match=r"File exceeds"):
        extract_archive(archive_path, dest, limits=limits)


def test_reject_zip_total_bytes_limit(tmp_path: Path):
    dest = tmp_path / "extracted"
    archive_path = tmp_path / "totallarge.whl"

    archive_content = make_zip(
        {
            "file1.bin": b"x" * 60,
            "file2.bin": b"y" * 60,
        }
    )
    archive_path.write_bytes(archive_content)

    limits = ExtractionLimits(max_total_bytes=100)
    with pytest.raises(ArchiveLimitExceededError, match=r"Files exceed"):
        extract_archive(archive_path, dest, limits=limits)
