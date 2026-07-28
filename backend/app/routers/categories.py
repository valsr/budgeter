from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError, ValidationError
from app.models.category import Category
from app.schemas.category import (
    CategoryCreate,
    CategoryRead,
    CategoryReorderRequest,
    CategoryResolvePathRequest,
    CategoryUpdate,
)
from app.services import categories as categories_service
from app.services.color import hash_color

router = APIRouter(
    prefix="/api/categories", tags=["categories"], dependencies=[Depends(require_api_key)]
)


def _to_read(category: Category, include_archived: bool = False) -> CategoryRead:
    children = category.children
    if not include_archived:
        children = [c for c in children if c.archived_at is None]
    return CategoryRead(
        id=category.id,
        name=category.name,
        parent_id=category.parent_id,
        color=category.color or hash_color(category.id),
        sort_order=category.sort_order,
        archived_at=category.archived_at,
        children=[_to_read(c, include_archived) for c in children],
    )


@router.get("", response_model=list[CategoryRead])
def list_categories(include_archived: bool = False, db: Session = Depends(get_db)):
    roots = categories_service.list_categories(db, include_archived=include_archived)
    return [_to_read(c, include_archived) for c in roots]


@router.post("", response_model=CategoryRead, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    try:
        category = categories_service.create_category(
            db, name=payload.name, parent_id=payload.parent_id, color=payload.color
        )
        return _to_read(category)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/resolve", response_model=CategoryRead)
def resolve_category_path(payload: CategoryResolvePathRequest, db: Session = Depends(get_db)):
    try:
        category = categories_service.resolve_category_path(db, payload.path)
        return _to_read(category)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: int, db: Session = Depends(get_db)):
    try:
        return _to_read(categories_service.get_category(db, category_id))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)):
    parent_id = ...
    if payload.move_to_root:
        parent_id = None
    elif "parent_id" in payload.model_fields_set:
        parent_id = payload.parent_id

    try:
        category = categories_service.update_category(
            db,
            category_id,
            name=payload.name,
            color=payload.color,
            parent_id=parent_id,
        )
        return _to_read(category)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/{category_id}/archive", response_model=CategoryRead)
def archive_category(category_id: int, db: Session = Depends(get_db)):
    try:
        category = categories_service.archive_category(db, category_id)
        return _to_read(category, include_archived=True)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/reorder", response_model=list[CategoryRead])
def reorder_categories(payload: CategoryReorderRequest, db: Session = Depends(get_db)):
    try:
        categories = categories_service.reorder_categories(
            db, payload.parent_id, payload.ordered_ids
        )
        return [_to_read(c) for c in categories]
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
