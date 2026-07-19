"""Atomic filesystem storage for uploaded company documents."""

import os
import shutil
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from company_api.models import DocumentFormat
from company_api.rendering import extract_html_title, render_markdown

_SOURCE_FILENAMES = {
    DocumentFormat.HTML: "source.html",
    DocumentFormat.MARKDOWN: "source.md",
}
_RENDERED_FILENAME = "rendered.html"
_EXTENSION_FORMATS = {
    ".html": DocumentFormat.HTML,
    ".md": DocumentFormat.MARKDOWN,
}


class UnsupportedDocumentType(ValueError):
    """Raised when an upload filename has no supported document extension."""


@dataclass(frozen=True)
class PreparedDocument:
    title: str
    format: DocumentFormat
    original_filename: str
    staging_directory: Path
    final_directory: Path
    source_relative_path: str
    rendered_relative_path: str | None


@dataclass(frozen=True)
class StoredDocument:
    title: str
    format: DocumentFormat
    original_filename: str
    directory: Path
    source_path: Path
    rendered_path: Path | None
    source_relative_path: str
    rendered_relative_path: str | None


class ContentStore:
    """Prepare documents off-path, then move complete directories into place."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def prepare(
        self,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        source: bytes,
    ) -> PreparedDocument:
        document_format = self._document_format(filename)
        source_filename = _SOURCE_FILENAMES[document_format]
        fallback_title = Path(filename).stem or filename
        rendered_bytes: bytes | None = None

        if document_format is DocumentFormat.HTML:
            title = extract_html_title(source, fallback_title)
        else:
            rendered = render_markdown(source.decode("utf-8"), fallback_title)
            title = rendered.title
            rendered_bytes = rendered.html.encode("utf-8")

        staging_directory = self.root / ".staging" / str(document_id)
        final_directory = self.root / "companies" / str(company_id) / str(document_id)
        self._require_under_root(staging_directory)
        self._require_under_root(final_directory)

        source_path = final_directory / source_filename
        rendered_path = final_directory / _RENDERED_FILENAME if rendered_bytes is not None else None
        source_relative_path = source_path.relative_to(self.root).as_posix()
        rendered_relative_path = (
            rendered_path.relative_to(self.root).as_posix() if rendered_path is not None else None
        )
        prepared = PreparedDocument(
            title=title,
            format=document_format,
            original_filename=filename,
            staging_directory=staging_directory,
            final_directory=final_directory,
            source_relative_path=source_relative_path,
            rendered_relative_path=rendered_relative_path,
        )

        staging_directory.parent.mkdir(parents=True, exist_ok=True)
        try:
            staging_directory.mkdir()
        except BaseException:
            self._remove_empty_directory(staging_directory.parent)
            raise

        try:
            self._require_under_root(staging_directory)
            (staging_directory / source_filename).write_bytes(source)
            if rendered_bytes is not None:
                (staging_directory / _RENDERED_FILENAME).write_bytes(rendered_bytes)
        except BaseException:
            self._remove_tree_if_canonical(staging_directory)
            self._remove_empty_directory(staging_directory.parent)
            raise

        return prepared

    def commit(self, prepared: PreparedDocument) -> StoredDocument:
        self._validate_prepared(prepared)
        try:
            prepared.final_directory.parent.mkdir(parents=True, exist_ok=True)
            self._require_under_root(prepared.final_directory)
            if os.path.lexists(prepared.final_directory):
                raise FileExistsError(
                    f"document directory already exists: {prepared.final_directory}"
                )
            os.replace(prepared.staging_directory, prepared.final_directory)
        except BaseException:
            self._remove_empty_final_parents(prepared.final_directory)
            raise
        self._remove_empty_directory(prepared.staging_directory.parent)

        source_path = prepared.final_directory / _SOURCE_FILENAMES[prepared.format]
        rendered_path = (
            prepared.final_directory / _RENDERED_FILENAME
            if prepared.rendered_relative_path is not None
            else None
        )
        return StoredDocument(
            title=prepared.title,
            format=prepared.format,
            original_filename=prepared.original_filename,
            directory=prepared.final_directory,
            source_path=source_path,
            rendered_path=rendered_path,
            source_relative_path=prepared.source_relative_path,
            rendered_relative_path=prepared.rendered_relative_path,
        )

    def discard(self, prepared: PreparedDocument) -> None:
        self._validate_prepared(prepared)
        with suppress(FileNotFoundError):
            shutil.rmtree(prepared.staging_directory)
        self._remove_empty_directory(prepared.staging_directory.parent)

    def delete(self, stored: StoredDocument) -> None:
        """Stage a reversible deletion in the root's trash directory."""
        self._validate_stored(stored)
        trash_directory = self._trash_directory(stored)
        try:
            trash_directory.parent.mkdir(parents=True, exist_ok=True)
            self._require_under_root(trash_directory)
            if os.path.lexists(trash_directory):
                raise FileExistsError(f"trash directory already exists: {trash_directory}")
            os.replace(stored.directory, trash_directory)
        except BaseException:
            self._remove_empty_trash_parents(trash_directory)
            raise
        self._remove_empty_final_parents(stored.directory)

    def restore_deleted(self, stored: StoredDocument) -> None:
        """Restore a staged deletion when its database operation is rolled back."""
        self._validate_stored(stored)
        trash_directory = self._trash_directory(stored)
        if os.path.lexists(stored.directory):
            raise FileExistsError(f"document directory already exists: {stored.directory}")

        try:
            stored.directory.parent.mkdir(parents=True, exist_ok=True)
            self._require_under_root(stored.directory)
            self._require_under_root(trash_directory)
            os.replace(trash_directory, stored.directory)
        except BaseException:
            self._remove_empty_final_parents(stored.directory)
            self._remove_empty_trash_parents(trash_directory)
            raise
        self._remove_empty_trash_parents(trash_directory)

    def purge_deleted(self, stored: StoredDocument) -> None:
        """Permanently remove a staged deletion after its database commit."""
        self._validate_stored(stored)
        trash_directory = self._trash_directory(stored)
        with suppress(FileNotFoundError):
            shutil.rmtree(trash_directory)
        self._remove_empty_trash_parents(trash_directory)

    @staticmethod
    def _document_format(filename: str) -> DocumentFormat:
        extension = Path(filename).suffix.lower()
        try:
            return _EXTENSION_FORMATS[extension]
        except KeyError as error:
            raise UnsupportedDocumentType(
                f"unsupported document extension: {extension or '<none>'}"
            ) from error

    def _validate_prepared(self, prepared: PreparedDocument) -> None:
        _, document_id = self._validate_document_directory(prepared.final_directory)
        expected_staging_directory = self.root / ".staging" / str(document_id)
        if prepared.staging_directory != expected_staging_directory:
            raise ValueError("staging directory does not match the document UUID")
        self._require_under_root(prepared.staging_directory)

        try:
            source_filename = _SOURCE_FILENAMES[prepared.format]
        except KeyError as error:
            raise ValueError("unsupported prepared document format") from error
        expected_source = (
            (prepared.final_directory / source_filename).relative_to(self.root).as_posix()
        )
        expected_rendered = (
            (prepared.final_directory / _RENDERED_FILENAME).relative_to(self.root).as_posix()
            if prepared.format is DocumentFormat.MARKDOWN
            else None
        )
        if prepared.source_relative_path != expected_source:
            raise ValueError("source path does not match the prepared document directory")
        if prepared.rendered_relative_path != expected_rendered:
            raise ValueError("rendered path does not match the prepared document format")

    def _validate_stored(self, stored: StoredDocument) -> None:
        self._validate_document_directory(stored.directory)
        try:
            source_filename = _SOURCE_FILENAMES[stored.format]
        except KeyError as error:
            raise ValueError("unsupported stored document format") from error

        expected_source_path = stored.directory / source_filename
        expected_rendered_path = (
            stored.directory / _RENDERED_FILENAME
            if stored.format is DocumentFormat.MARKDOWN
            else None
        )
        if stored.source_path != expected_source_path:
            raise ValueError("source path does not match the stored document directory")
        if stored.rendered_path != expected_rendered_path:
            raise ValueError("rendered path does not match the stored document format")

        expected_source_relative_path = expected_source_path.relative_to(self.root).as_posix()
        expected_rendered_relative_path = (
            expected_rendered_path.relative_to(self.root).as_posix()
            if expected_rendered_path is not None
            else None
        )
        if stored.source_relative_path != expected_source_relative_path:
            raise ValueError("source relative path does not match the stored document path")
        if stored.rendered_relative_path != expected_rendered_relative_path:
            raise ValueError("rendered relative path does not match the stored document path")

        self._require_under_root(stored.source_path)
        if stored.rendered_path is not None:
            self._require_under_root(stored.rendered_path)

    def _validate_document_directory(self, directory: Path) -> tuple[uuid.UUID, uuid.UUID]:
        self._require_under_root(directory)
        try:
            relative_directory = directory.relative_to(self.root)
        except ValueError as error:
            raise ValueError("document directory is outside the content root") from error
        if len(relative_directory.parts) != 3 or relative_directory.parts[0] != "companies":
            raise ValueError("document directory is not UUID-derived")

        company_part, document_part = relative_directory.parts[1:]
        try:
            company_id = uuid.UUID(company_part)
            document_id = uuid.UUID(document_part)
        except ValueError as error:
            raise ValueError("document directory is not UUID-derived") from error
        if str(company_id) != company_part or str(document_id) != document_part:
            raise ValueError("document directory is not canonically UUID-derived")
        return company_id, document_id

    def _trash_directory(self, stored: StoredDocument) -> Path:
        company_id, document_id = self._validate_document_directory(stored.directory)
        trash_directory = self.root / ".trash" / str(company_id) / str(document_id)
        self._require_under_root(trash_directory)
        return trash_directory

    def _require_under_root(self, path: Path) -> None:
        try:
            relative_path = path.relative_to(self.root)
        except ValueError as error:
            raise ValueError(f"content path escapes configured root: {path}") from error

        current = self.root
        for part in relative_path.parts:
            current /= part
            if current.is_symlink():
                raise ValueError(f"content path contains a symlink component: {current}")

        try:
            path.resolve().relative_to(self.root)
        except ValueError as error:
            raise ValueError(f"content path escapes configured root: {path}") from error

    @staticmethod
    def _remove_empty_directory(path: Path) -> None:
        with suppress(OSError):
            path.rmdir()

    def _remove_empty_final_parents(self, document_directory: Path) -> None:
        try:
            self._require_under_root(document_directory.parent)
        except ValueError:
            return
        self._remove_empty_directory(document_directory.parent)
        self._remove_empty_directory(self.root / "companies")

    def _remove_empty_trash_parents(self, trash_directory: Path) -> None:
        try:
            self._require_under_root(trash_directory.parent)
        except ValueError:
            return
        self._remove_empty_directory(trash_directory.parent)
        self._remove_empty_directory(self.root / ".trash")

    def _remove_tree_if_canonical(self, path: Path) -> None:
        try:
            self._require_under_root(path)
        except ValueError:
            return
        shutil.rmtree(path, ignore_errors=True)
