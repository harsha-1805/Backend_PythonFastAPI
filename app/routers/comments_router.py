"""Comments routes — discussion threads on Bugs/Tasks/SubTasks."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import Comment, User
from app.schemas import CommentCreate, CommentOut
from app.services import comment_service

router = APIRouter(prefix="/api/v1/comments", tags=["Comments"])


@router.get("", response_model=list[CommentOut])
def list_comments(
    entity_type: str = Query(...),
    entity_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("comments.view")),
):
    comment_service.assert_entity_access(db, user=current_user, entity_type=entity_type, entity_id=entity_id)
    comments = comment_service.list_comments(db, entity_type=entity_type, entity_id=entity_id)
    return [CommentOut.model_validate(c) for c in comments]


@router.post("", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def create_comment(
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("comments.create")),
):
    comment_service.assert_entity_access(
        db, user=current_user, entity_type=payload.entity_type, entity_id=payload.entity_id
    )
    comment = comment_service.create_comment(
        db,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        author=current_user,
        body=payload.body,
    )
    return CommentOut.model_validate(comment)


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("comments.view")),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    comment_service.assert_entity_access(
        db, user=current_user, entity_type=comment.entity_type, entity_id=comment.entity_id
    )
    comment_service.delete_comment(db, comment=comment, actor=current_user)
