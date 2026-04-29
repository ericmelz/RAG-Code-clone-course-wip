from pydantic import BaseModel
from app.indexing.documents import Document


class QCChatAgentState(BaseModel):
    chat_messages: list[dict[str, str]] = []
    namespace: str | None = None
    index_type: str | None = None  # "github" or "financial"
    generation: str | None = None
    retrieved_documents: list[Document] = []
    has_contradiction: bool | None = None
    contradiction_reason: str | None = None