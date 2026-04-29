import logging
import os
from datetime import datetime, timezone

import httpx

from app.chat.agents.quality_control_agent.state import QCChatAgentState

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_CONFLICT_WEBHOOK_URL", "")


def _build_slack_payload(state: QCChatAgentState) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    user_question = state.chat_messages[-1]["content"] if state.chat_messages else "(unknown)"

    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":warning:  Data Conflict Detected",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Namespace:*\n`{state.namespace}`"},
                    {"type": "mrkdwn", "text": f"*Detected at:*\n{ts}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*User question:*\n>{user_question}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Conflict:*\n{state.contradiction_reason}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Sources involved:*\n"
                    + "\n".join(
                        f"• `{doc.source}`"
                        for doc in state.retrieved_documents
                        if doc.source
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "RAG Quality Control Agent | AcmeWackoWidgets Financial RAG",
                    }
                ],
            },
        ]
    }


async def _post_to_slack(payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(SLACK_WEBHOOK_URL, json=payload)
        if response.status_code != 200:
            logger.warning(
                f"Slack webhook returned {response.status_code}: {response.text}"
            )
        else:
            logger.info("Conflict notification posted to Slack.")


class ConflictHandler:
    """Logs detected document contradictions and posts a Slack alert."""

    async def __call__(self, state: QCChatAgentState) -> QCChatAgentState:
        msg = (
            f"[QC CONFLICT] namespace='{state.namespace}' — "
            f"{state.contradiction_reason}"
        )
        logger.warning(msg)
        print(f"\n{'='*60}\nCONFLICT DETECTED: {state.contradiction_reason}\n{'='*60}\n")

        try:
            logger.info("Posting Slack alert.")
            print("Posting Slack alert.")
            payload = _build_slack_payload(state)
            await _post_to_slack(payload)
            print("Slack alert posted.")
            logger.info(f"Slack alert posted: {payload}")
        except Exception as e:
            logger.error(f"Failed to post conflict to Slack: {e}")

        return state


conflict_handler = ConflictHandler()
