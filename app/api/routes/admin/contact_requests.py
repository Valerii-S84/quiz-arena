from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.sql.elements import ColumnElement

from app.api.routes.admin.audit import write_admin_audit
from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.api.routes.admin.pagination import build_pagination
from app.db.models.contact_requests import ContactRequest
from app.db.session import SessionLocal

router = APIRouter(prefix="/admin/contact-requests", tags=["admin-contact-requests"])


class ContactRequestItem(BaseModel):
    id: int
    type: str
    status: str
    name: str
    contact: str
    payload: dict[str, object]
    created_at: datetime
    updated_at: datetime


class ContactRequestsResponse(BaseModel):
    items: list[ContactRequestItem]
    total: int
    page: int
    pages: int


class ContactRequestStatusUpdate(BaseModel):
    status: str = Field(pattern="^(NEW|IN_PROGRESS|DONE|SPAM)$")


@router.get("", response_model=ContactRequestsResponse)
async def list_contact_requests(
    response: Response,
    request_type: str | None = Query(default=None, alias="type", pattern="^(student|partner)$"),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern="^(NEW|IN_PROGRESS|DONE|SPAM)$",
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> ContactRequestsResponse:
    add_admin_noindex_header(response)

    filters: list[ColumnElement[bool]] = []
    if request_type:
        filters.append(ContactRequest.request_type == request_type)
    if status_filter:
        filters.append(ContactRequest.status == status_filter)

    where_clause: ColumnElement[bool] | None = and_(*filters) if filters else None

    async with SessionLocal.begin() as session:
        total_stmt = select(func.count(ContactRequest.id))
        if where_clause is not None:
            total_stmt = total_stmt.where(where_clause)
        total = int((await session.execute(total_stmt)).scalar_one() or 0)

        data_stmt = select(ContactRequest).order_by(
            ContactRequest.created_at.desc(), ContactRequest.id.desc()
        )
        if where_clause is not None:
            data_stmt = data_stmt.where(where_clause)
        rows = (await session.execute(data_stmt.offset((page - 1) * limit).limit(limit))).scalars()
        items = list(rows)

    pagination = build_pagination(total=total, page=page, limit=limit)
    return ContactRequestsResponse(
        items=[
            ContactRequestItem(
                id=int(item.id),
                type=item.request_type,
                status=item.status,
                name=item.name,
                contact=item.contact,
                payload=item.payload,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ],
        total=pagination["total"],
        page=pagination["page"],
        pages=pagination["pages"],
    )


@router.post("/{request_id}/status")
async def update_contact_request_status(
    request_id: int,
    payload: ContactRequestStatusUpdate,
    response: Response,
    admin: AdminPrincipal = Depends(get_current_admin),
) -> dict[str, object]:
    add_admin_noindex_header(response)

    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        request_row = await session.get(ContactRequest, request_id)
        if request_row is None:
            raise HTTPException(status_code=404, detail={"code": "E_CONTACT_REQUEST_NOT_FOUND"})

        request_row.status = payload.status
        request_row.updated_at = now_utc

        await write_admin_audit(
            session,
            admin_email=admin.email,
            action="contact_request_status_update",
            target_type="contact_request",
            target_id=str(request_id),
            payload={"status": payload.status, "at": now_utc.isoformat()},
            ip=admin.client_ip,
        )

    return {"ok": True, "id": request_id, "status": payload.status}
