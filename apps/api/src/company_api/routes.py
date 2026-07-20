"""FastAPI routes for the company document library."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from company_api.library_service import (
    CompanyNotEmpty,
    CompanyNotFound,
    DocumentNotFound,
    LibraryOperations,
    UploadInput,
)
from company_api.schemas import (
    CompanyCreate,
    CompanyRead,
    DocumentRead,
    DocumentRename,
    UploadBatchResponse,
)

router = APIRouter(prefix="/api/v1")


def get_library_service(request: Request) -> LibraryOperations:
    return request.app.state.library_service  # type: ignore[no-any-return]


LibraryServiceDependency = Annotated[LibraryOperations, Depends(get_library_service)]


@router.get("/companies", response_model=list[CompanyRead])
async def list_companies(service: LibraryServiceDependency) -> list[CompanyRead]:
    return await service.list_companies()


@router.post("/companies", response_model=CompanyRead, status_code=201)
async def create_company(
    data: CompanyCreate,
    service: LibraryServiceDependency,
) -> CompanyRead:
    return await service.create_company(data)


@router.delete("/companies/{company_id}", status_code=204)
async def delete_company(company_id: UUID, service: LibraryServiceDependency) -> Response:
    try:
        await service.delete_company(company_id)
    except CompanyNotFound as error:
        raise HTTPException(status_code=404, detail="公司不存在") from error
    except CompanyNotEmpty as error:
        raise HTTPException(status_code=409, detail="公司仍有资料，无法删除") from error
    return Response(status_code=204)


@router.get("/companies/{company_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    company_id: UUID,
    service: LibraryServiceDependency,
) -> list[DocumentRead]:
    try:
        return await service.list_documents(company_id)
    except CompanyNotFound as error:
        raise HTTPException(status_code=404, detail="公司不存在") from error


@router.post(
    "/companies/{company_id}/documents",
    response_model=UploadBatchResponse,
)
async def upload_documents(
    company_id: UUID,
    files: Annotated[list[UploadFile], File()],
    service: LibraryServiceDependency,
) -> UploadBatchResponse:
    uploads = [
        UploadInput(filename=file.filename or "upload", content=await file.read()) for file in files
    ]
    try:
        return await service.upload_documents(company_id, uploads)
    except CompanyNotFound as error:
        raise HTTPException(status_code=404, detail="公司不存在") from error


@router.patch("/documents/{document_id}", response_model=DocumentRead)
async def rename_document(
    document_id: UUID,
    data: DocumentRename,
    service: LibraryServiceDependency,
) -> DocumentRead:
    try:
        return await service.rename_document(document_id, data.title)
    except DocumentNotFound as error:
        raise HTTPException(status_code=404, detail="资料不存在") from error


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: UUID, service: LibraryServiceDependency) -> Response:
    try:
        await service.delete_document(document_id)
    except DocumentNotFound as error:
        raise HTTPException(status_code=404, detail="资料不存在") from error
    return Response(status_code=204)


@router.get("/documents/{document_id}/content", response_class=FileResponse)
@router.head(
    "/documents/{document_id}/content",
    response_class=FileResponse,
    include_in_schema=False,
)
async def document_content(
    document_id: UUID,
    service: LibraryServiceDependency,
) -> FileResponse:
    try:
        content_path = await service.content_path(document_id)
    except DocumentNotFound as error:
        raise HTTPException(status_code=404, detail="资料不存在") from error
    return FileResponse(
        content_path,
        media_type="text/html; charset=utf-8",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-cache",
        },
    )
