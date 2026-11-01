import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response

from app.reports.json_exporter import generate_json_report
from app.reports.pdf_exporter import generate_pdf_report
from app.scans.manager import (
    ScanNotFoundError,
    ScanNotReadyError,
    get_scan_manager,
)
from app.schemas.common import ErrorResponse
from app.schemas.scans import (
    FileDiffItem,
    ReleaseComparisonResponse,
    ScanDiffsResponse,
    ScanFilesResponse,
    ScanFindingsResponse,
    ScanReportResponse,
    ScanRequest,
    ScanResponse,
    ScanStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ScanResponse,
    responses={422: {"model": ErrorResponse}},
)
async def create_scan(request: ScanRequest) -> ScanResponse:
    """Validate and initiate a package integrity scan."""
    record = await get_scan_manager().create_scan(request)
    return ScanResponse(
        scan_id=record.scan_id,
        status="accepted",
        ecosystem=record.ecosystem,
        package_name=record.package_name,
        version=record.version,
    )


@router.get(
    "/compare",
    response_model=ReleaseComparisonResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def compare_releases_by_scan_id(
    head_scan_id: Annotated[UUID, Query(description="The primary / newer scan ID to compare")],
    base_scan_id: Annotated[UUID | None, Query(description="The baseline / older scan ID")] = None,
) -> ReleaseComparisonResponse:
    """Compare two completed scans to identify newly introduced changes."""
    try:
        return get_scan_manager().compare_two_scans(head_scan_id, base_scan_id)
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{scan_id}",
    response_model=ScanStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_scan_status(scan_id: UUID) -> ScanStatusResponse:
    """Get the current status and progress of a scan."""
    try:
        return get_scan_manager().get_status(scan_id)
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{scan_id}/report",
    response_model=ScanReportResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def get_scan_report(scan_id: UUID) -> ScanReportResponse:
    """Get the complete integrity analysis report."""
    try:
        return get_scan_manager().get_report(scan_id)
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{scan_id}/findings",
    response_model=ScanFindingsResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def get_scan_findings(scan_id: UUID) -> ScanFindingsResponse:
    """Get security findings, gaps, and AI investigation explanations."""
    try:
        return get_scan_manager().get_findings(scan_id)
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{scan_id}/files",
    response_model=ScanFilesResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def get_scan_files(scan_id: UUID) -> ScanFilesResponse:
    """Get file inventory and source comparison classifications."""
    try:
        return get_scan_manager().get_files(scan_id)
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{scan_id}/files/{file_id:path}/diff",
    response_model=FileDiffItem,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def get_scan_file_diff(scan_id: UUID, file_id: str) -> FileDiffItem:
    """Get file diff for a specific file by file index or path."""
    try:
        return get_scan_manager().get_file_diff(scan_id, file_id)
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{scan_id}/diffs",
    response_model=ScanDiffsResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def get_scan_diffs(
    scan_id: UUID,
    path: Annotated[str | None, Query()] = None,
) -> ScanDiffsResponse:
    """Get file diffs between package and source repository."""
    try:
        return get_scan_manager().get_diffs(scan_id, path=path)
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{scan_id}/export/json",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def export_scan_json(scan_id: UUID) -> JSONResponse:
    """Download package integrity report as structured JSON."""
    try:
        report = get_scan_manager().get_report(scan_id)
        data = generate_json_report(report)
        filename = f"veritor-report-{report.ecosystem}-{report.package_name}-{report.version}.json"
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{scan_id}/export/pdf",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def export_scan_pdf(scan_id: UUID) -> Response:
    """Download package integrity report as a PDF."""
    try:
        report = get_scan_manager().get_report(scan_id)
        pdf_bytes = generate_pdf_report(report)
        filename = f"veritor-report-{report.ecosystem}-{report.package_name}-{report.version}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{scan_id}/compare-previous",
    response_model=ReleaseComparisonResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def compare_scan_with_previous(scan_id: UUID) -> ReleaseComparisonResponse:
    """Compare a scan report with the previous completed release of the same package."""
    try:
        return get_scan_manager().compare_scan_with_previous(scan_id)
    except ScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScanNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
