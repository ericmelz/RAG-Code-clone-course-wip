from app.indexing.indexers.github import GithubIndexer
from app.indexing.indexers.financial import FinancialIndexer
from app.indexing.documents import Document
from app.chat.agents.quality_control_agent.state import QCChatAgentState


class Retriever:
    async def search(self, state: QCChatAgentState) -> list[Document]:
        if state.index_type == "financial":
            indexer = FinancialIndexer(namespace=state.namespace)
        else:
            indexer = GithubIndexer(namespace=state.namespace)
        last_user_message = state.chat_messages[-1]["content"]
        return await indexer.search(
            last_user_message,
            max_results=10,
            with_filters=False,
            with_rerank=False,
        )

    async def __call__(self, state: QCChatAgentState) -> QCChatAgentState:
        state.retrieved_documents = await self.search(state)
        return state


retriever = Retriever()
