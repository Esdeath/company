from company_api.models import Base


def test_company_and_document_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {"companies", "documents"}
    columns = Base.metadata.tables["documents"].c
    assert set(columns.keys()) == {
        "id",
        "company_id",
        "title",
        "format",
        "source_path",
        "rendered_path",
        "original_filename",
        "uploaded_at",
    }
