from pydantic import BaseModel
from app.indexing.github_parsing import CodeElement


class ChatAgentState(BaseModel):
    need_rag: bool = False
    query_vector_db: str | None = None