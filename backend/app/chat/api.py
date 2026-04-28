import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.agents.basic_rag.agent import basic_chat_agent
from app.chat.agents.basic_rag.state import BasicChatAgentState
from app.chat.agents.chat_agent.agent import chat_agent
from app.chat.agents.chat_agent.state import ChatAgentState
from app.chat.crud import get_chat_history, save_user_message, save_assistant_message
from app.chat.schemas import ChatRequest, ChatResponse
from app.core.db import get_db
from app.indexing.crud import get_indexed_repo_by_namespace
from app.indexing.models import IndexType

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/message", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    try:
        await save_user_message(db, request.username, request.message)

        chat_messages = await get_chat_history(db, request.username)
        source = await get_indexed_repo_by_namespace(db, request.namespace)

        if source.index_type == IndexType.FINANCIAL:
            initial_state = BasicChatAgentState(
                namespace=source.namespace,
                index_type=str(source.index_type),
                chat_messages=chat_messages,
            )
            result = await basic_chat_agent.ainvoke(initial_state)
            final_state = BasicChatAgentState(**result)
        else:
            initial_state = ChatAgentState(
                namespace=source.namespace,
                chat_messages=chat_messages,
            )
            result = await chat_agent.ainvoke(initial_state, debug=True)
            final_state = ChatAgentState(**result)

        response_text = final_state.generation or "I'm sorry, I couldn't generate a response."
        await save_assistant_message(db, request.username, response_text)

        return ChatResponse(response=response_text)

    except Exception as e:
        logger.error(f"Chat agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
