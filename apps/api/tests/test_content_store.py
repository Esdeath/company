import uuid
from dataclasses import replace
from pathlib import Path

import pytest

import company_api.content_store as content_store_module
from company_api.content_store import ContentStore, UnsupportedDocumentType
from company_api.models import DocumentFormat

COMPANY_ID = uuid.UUID("fef2857a-8794-42b6-98c2-d5697d877632")
DOCUMENT_ID = uuid.UUID("5cc11f7f-23bd-4a5c-9dc7-a28058ac5ae2")


def test_html_is_saved_byte_for_byte(tmp_path: Path) -> None:
    source = b"<!doctype html><title>CEO speech</title><p>\xff</p>"
    store = ContentStore(tmp_path)

    prepared = store.prepare(COMPANY_ID, DOCUMENT_ID, "speech.HTML", source)
    stored = store.commit(prepared)

    assert stored.source_path.read_bytes() == source
    assert stored.rendered_path is None
    assert stored.title == "CEO speech"
    assert stored.format is DocumentFormat.HTML


def test_markdown_keeps_source_and_writes_rendered_html(tmp_path: Path) -> None:
    source = "# 访谈\n\n> 原话".encode()
    store = ContentStore(tmp_path)

    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "talk.md", source))

    assert stored.source_path.read_bytes() == source
    assert stored.rendered_path is not None
    assert "<blockquote>" in stored.rendered_path.read_text()
    assert stored.title == "访谈"
    assert stored.format is DocumentFormat.MARKDOWN


@pytest.mark.parametrize(
    ("filename", "expected_format"),
    [
        ("report.hTmL", DocumentFormat.HTML),
        ("report.Md", DocumentFormat.MARKDOWN),
    ],
)
def test_supported_extensions_are_case_insensitive(
    tmp_path: Path,
    filename: str,
    expected_format: DocumentFormat,
) -> None:
    store = ContentStore(tmp_path)

    prepared = store.prepare(COMPANY_ID, DOCUMENT_ID, filename, b"plain")

    assert prepared.format is expected_format


def test_unsupported_extension_leaves_no_files(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)

    with pytest.raises(UnsupportedDocumentType):
        store.prepare(COMPANY_ID, DOCUMENT_ID, "notes.pdf", b"pdf")

    assert list(tmp_path.rglob("*")) == []


def test_failed_markdown_decode_leaves_no_files(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)

    with pytest.raises(UnicodeDecodeError):
        store.prepare(COMPANY_ID, DOCUMENT_ID, "notes.md", b"\xff")

    assert list(tmp_path.rglob("*")) == []


def test_failed_markdown_render_leaves_no_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_render(source: str, fallback_title: str) -> None:
        del source, fallback_title
        raise RuntimeError("render failed")

    monkeypatch.setattr(content_store_module, "render_markdown", fail_render)
    store = ContentStore(tmp_path)

    with pytest.raises(RuntimeError, match="render failed"):
        store.prepare(COMPANY_ID, DOCUMENT_ID, "notes.md", b"valid")

    assert list(tmp_path.rglob("*")) == []


def test_uuid_directories_and_constant_filenames_ignore_upload_name(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)

    prepared = store.prepare(
        COMPANY_ID,
        DOCUMENT_ID,
        "../../arbitrary name.MD",
        b"content",
    )

    assert prepared.staging_directory == tmp_path / ".staging" / str(DOCUMENT_ID)
    assert prepared.final_directory == (tmp_path / "companies" / str(COMPANY_ID) / str(DOCUMENT_ID))
    assert prepared.source_relative_path == (f"companies/{COMPANY_ID}/{DOCUMENT_ID}/source.md")
    assert prepared.rendered_relative_path == (
        f"companies/{COMPANY_ID}/{DOCUMENT_ID}/rendered.html"
    )
    assert {path.name for path in prepared.staging_directory.iterdir()} == {
        "source.md",
        "rendered.html",
    }


def test_commit_collision_preserves_existing_document_and_staging(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    original = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "original.html", b"original"))
    replacement = store.prepare(COMPANY_ID, DOCUMENT_ID, "replacement.html", b"replacement")

    with pytest.raises(FileExistsError):
        store.commit(replacement)

    assert original.source_path.read_bytes() == b"original"
    assert replacement.staging_directory.is_dir()


def test_commit_collision_preserves_dangling_destination_symlink(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    prepared = store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source")
    prepared.final_directory.parent.mkdir(parents=True)
    prepared.final_directory.symlink_to(tmp_path / "missing-document", target_is_directory=True)

    with pytest.raises(FileExistsError):
        store.commit(prepared)

    assert prepared.final_directory.is_symlink()
    assert prepared.staging_directory.is_dir()


def test_prepare_collision_preserves_existing_staging(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    existing = store.prepare(COMPANY_ID, DOCUMENT_ID, "original.html", b"original")

    with pytest.raises(FileExistsError):
        store.prepare(COMPANY_ID, DOCUMENT_ID, "replacement.html", b"replacement")

    assert (existing.staging_directory / "source.html").read_bytes() == b"original"


def test_discard_is_idempotent(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    prepared = store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source")

    assert store.discard(prepared) is None
    assert store.discard(prepared) is None

    assert not prepared.staging_directory.exists()
    assert list(tmp_path.rglob("*")) == []


def test_discard_rejects_forged_staging_directory(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    prepared = store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("keep")

    with pytest.raises(ValueError, match="staging directory"):
        store.discard(replace(prepared, staging_directory=unrelated))

    assert (unrelated / "keep.txt").read_text() == "keep"


def test_failed_commit_removes_empty_destination_parents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ContentStore(tmp_path)
    prepared = store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source")

    def fail_replace(source: Path, destination: Path) -> None:
        del source, destination
        raise OSError("rename failed")

    monkeypatch.setattr(content_store_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="rename failed"):
        store.commit(prepared)

    assert prepared.staging_directory.is_dir()
    assert not (tmp_path / "companies").exists()


def test_delete_and_restore_compensate_with_reversible_rename(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source"))
    trash_directory = tmp_path / ".trash" / str(DOCUMENT_ID)

    assert store.delete(stored) is None
    assert not stored.directory.exists()
    assert (trash_directory / "source.html").read_bytes() == b"source"

    assert store.restore_deleted(stored) is None
    assert stored.source_path.read_bytes() == b"source"
    assert not trash_directory.exists()


def test_delete_rejects_forged_stored_paths(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source"))
    unrelated = tmp_path / "unrelated" / str(DOCUMENT_ID)
    unrelated.mkdir(parents=True)
    unrelated_source = unrelated / "source.html"
    unrelated_source.write_bytes(b"keep")

    forged = replace(
        stored,
        directory=unrelated,
        source_path=unrelated_source,
        source_relative_path=unrelated_source.relative_to(tmp_path).as_posix(),
    )
    with pytest.raises(ValueError, match="document directory"):
        store.delete(forged)

    assert unrelated_source.read_bytes() == b"keep"
    assert stored.source_path.read_bytes() == b"source"


def test_delete_collision_preserves_dangling_trash_symlink(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source"))
    trash_directory = tmp_path / ".trash" / str(DOCUMENT_ID)
    trash_directory.parent.mkdir()
    trash_directory.symlink_to(tmp_path / "missing-trash", target_is_directory=True)

    with pytest.raises(FileExistsError):
        store.delete(stored)

    assert trash_directory.is_symlink()
    assert stored.source_path.read_bytes() == b"source"


def test_restore_collision_preserves_dangling_destination_symlink(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source"))
    store.delete(stored)
    stored.directory.parent.mkdir(parents=True)
    stored.directory.symlink_to(tmp_path / "missing-document", target_is_directory=True)

    with pytest.raises(FileExistsError):
        store.restore_deleted(stored)

    assert stored.directory.is_symlink()
    assert (tmp_path / ".trash" / str(DOCUMENT_ID) / "source.html").read_bytes() == b"source"


def test_failed_restore_removes_empty_destination_parents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source"))
    store.delete(stored)
    trash_directory = tmp_path / ".trash" / str(DOCUMENT_ID)

    def fail_replace(source: Path, destination: Path) -> None:
        del source, destination
        raise OSError("restore failed")

    monkeypatch.setattr(content_store_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="restore failed"):
        store.restore_deleted(stored)

    assert (trash_directory / "source.html").read_bytes() == b"source"
    assert not (tmp_path / "companies").exists()


def test_purge_deleted_removes_staged_deletion(tmp_path: Path) -> None:
    store = ContentStore(tmp_path)
    stored = store.commit(store.prepare(COMPANY_ID, DOCUMENT_ID, "report.html", b"source"))
    store.delete(stored)

    assert store.purge_deleted(stored) is None

    assert list(tmp_path.rglob("*")) == []
