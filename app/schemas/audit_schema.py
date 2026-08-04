"""
Pydantic schemas for the Audit Log module.

Kept in its own file for the same reason admin_schema.py / bug_schema.py
are — one concern per file, re-exported from schemas/__init__.py.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    entity_type: str
    entity_id: int
    entity_name: Optional[str] = None
    action: str
    field_changed: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    project_id: Optional[int] = None
    description: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AuditLogOut]
