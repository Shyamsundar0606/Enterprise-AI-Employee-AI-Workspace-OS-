from __future__ import annotations

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db_session
from app.models.user import User
from app.schemas.chat import (
    ConversationCreate,
    ConversationListResponse,
    ConversationOut,
    ConversationUpdate,
    DeleteResponse,
    MessageCreate,
    MessageListResponse,
    MessageOut,
)
from app.services.auth import decode_token, get_user_by_id
from app.services.chat import ChatService

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@router.post(
    "/chat/conversations", status_code=status.HTTP_201_CREATED, response_model=ConversationOut
)
async def create_conversation(
    payload: ConversationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConversationOut:
    conversation = await ChatService(session).create_conversation(
        user_id=current_user.id, title=payload.title
    )
    return ConversationOut.model_validate(conversation)


@router.get("/chat/conversations", response_model=ConversationListResponse)
async def list_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationListResponse:
    conversations, total = await ChatService(session).list_conversations(
        user_id=current_user.id, page=page, page_size=page_size
    )
    return ConversationListResponse(
        items=[ConversationOut.model_validate(item) for item in conversations],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/chat/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> ConversationOut:
    conversation = await ChatService(session).get_conversation(
        conversation_id=conversation_id, user_id=current_user.id
    )
    return ConversationOut.model_validate(conversation)


@router.patch("/chat/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> ConversationOut:
    conversation = await ChatService(session).update_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        fields=payload.model_dump(exclude_unset=True),
    )
    return ConversationOut.model_validate(conversation)


@router.delete("/chat/conversations/{conversation_id}", response_model=DeleteResponse)
async def delete_conversation(
    conversation_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> DeleteResponse:
    deleted = await ChatService(session).delete_conversation(
        conversation_id=conversation_id, user_id=current_user.id
    )
    return DeleteResponse(deleted=deleted, id=conversation_id)


@router.post("/chat/messages", status_code=status.HTTP_201_CREATED, response_model=MessageOut)
async def create_message(
    payload: MessageCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> MessageOut:
    message = await ChatService(session).create_message(
        conversation_id=payload.conversation_id,
        user_id=current_user.id,
        role=payload.role,
        content=payload.content,
        metadata=payload.metadata,
        token_count=payload.token_count,
    )
    return MessageOut.model_validate(
        {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "metadata": message.payload_metadata,
            "token_count": message.token_count,
            "created_at": message.created_at,
        }
    )


@router.get("/chat/messages/{conversation_id}", response_model=MessageListResponse)
async def list_messages(
    conversation_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> MessageListResponse:
    messages, total = await ChatService(session).list_messages(
        conversation_id=conversation_id, user_id=current_user.id, page=page, page_size=page_size
    )
    return MessageListResponse(
        items=[
            MessageOut.model_validate(
                {
                    "id": item.id,
                    "conversation_id": item.conversation_id,
                    "role": item.role,
                    "content": item.content,
                    "metadata": item.payload_metadata,
                    "token_count": item.token_count,
                    "created_at": item.created_at,
                }
            )
            for item in messages
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def authenticate_websocket_user(websocket: WebSocket, session: AsyncSession) -> User:
    authorization = websocket.headers.get("Authorization") or websocket.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise WebSocketException(code=1008, reason="Authentication required")

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception as exc:  # pragma: no cover - websocket auth guard
        raise WebSocketException(code=1008, reason="Invalid token") from exc

    if payload.get("token_type") != "access":
        raise WebSocketException(code=1008, reason="Invalid token type")

    user = await get_user_by_id(session, int(payload["sub"]))
    if user is None or not user.is_active:
        raise WebSocketException(code=1008, reason="User not found")
    return user


async def chat_websocket_handler(websocket: WebSocket) -> None:
    from app.database.session import AsyncSessionFactory

    await websocket.accept()
    async with AsyncSessionFactory() as session:
        try:
            await authenticate_websocket_user(websocket, session)
        except WebSocketException:
            await websocket.close(code=1008)
            return

        logger.info("WebSocket connected")
        try:
            while True:
                message = await websocket.receive_text()
                await websocket.send_text(message)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as exc:
            logger.exception("WebSocket error: %s", exc)
            raise
