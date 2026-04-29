import logging

from app.chat.agents.quality_control_agent.state import QCChatAgentState

logger = logging.getLogger(__name__)


class ConflictHandler:
    """Handles detected contradictions between retrieved documents."""

    async def __call__(self, state: QCChatAgentState) -> QCChatAgentState:
        msg = (
            f"[QC CONFLICT] namespace='{state.namespace}' — "
            f"{state.contradiction_reason}"
        )
        logger.warning(msg)
        print(f"\n{'='*60}\nCONFLICT DETECTED: {state.contradiction_reason}\n{'='*60}\n")
        return state


conflict_handler = ConflictHandler()
