"""
Pydantic schemas for Comments (bugs/tasks/subtasks discussion threads).
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["Bug", "Task", "SubTask"]


class CommentCreate(BaseModel):
    entity_type: EntityType
    entity_id: int
    body: str = Field(min_length=1, max_length=3000)


class CommentOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    author_id: Optional[int] = None
    author_name: Optional[str] = None
    body: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
