import logging

from pydantic import BaseModel, Field

from app.chat.agents.quality_control_agent.state import QCChatAgentState
from app.core.clients import async_openai_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are **ConflictDetector**: a precise assessor that examines a set of retrieved documents for contradictory factual claims.

## Inputs you will receive
- **chat_history** — the conversation so far
- **documents** — the retrieved chunks used to generate the answer; each has `text`, `source`, and optionally `doc_type`, `page_or_sheet`
- **generation** — the answer that was generated from those documents

## Your task
Examine the *documents* for factual contradictions. A contradiction exists when two or more documents make incompatible claims about the **same** entity, metric, or event.

## Common contradiction patterns
- Two documents report different numerical values for the same metric (revenue, units sold, price, date, percentage)
- One document states X while another states Y for the same named fact
- A spreadsheet total disagrees with a figure cited in a report for the same product/period

## Decision rules
- **Only flag contradictions clearly supported by the document text** — do not speculate
- Ignore differences that are explicitly for different time periods, products, or scopes
- A contradiction requires **at least two documents** with incompatible claims about the **same** fact
- If documents are consistent (or only one document is present), set has_contradiction to false

## Output format (STRICT)
Return only this JSON object:

{
  "has_contradiction": true | false,
  "contradiction_reason": "<1-2 sentences naming both sources and the conflicting values, or null if no contradiction>"
}
"""


class Assessment(BaseModel):
    """Quality control assessment of retrieved documents for contradictions.

    Attributes:
        has_contradiction: True if two or more documents contain conflicting factual claims.
        contradiction_reason: Short description of the conflict (sources and values), or null.
    """
    has_contradiction: bool = Field(
        ...,
        description="True if the retrieved documents contain contradictory factual claims.",
    )
    contradiction_reason: str | None = Field(
        None,
        description="1-2 sentence description naming the conflicting sources and values; null if no contradiction.",
    )


class Assessor:
    """Examines retrieved documents for factual contradictions after generation."""

    async def assess(self, state: QCChatAgentState) -> Assessment:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": "### Chat History ###"},
        ]
        messages.extend(state.chat_messages[-10:])

        documents = "\n".join(
            [doc.model_dump_json(indent=2, exclude_none=True) for doc in state.retrieved_documents]
        )
        messages.append({"role": "user", "content": f"### Documents ###\n\n{documents}"})
        messages.append({"role": "user", "content": f"### Generation ###\n\n{state.generation}"})

        try:
            response = await async_openai_client.responses.parse(
                model="gpt-4.1-mini",
                input=messages,
                temperature=0.1,
                text_format=Assessment,
            )
        except Exception as e:
            logger.error(f"Assessor LLM call failed: {e}")
            return Assessment(has_contradiction=False, contradiction_reason=None)

        return response.output_parsed

    async def __call__(self, state: QCChatAgentState) -> QCChatAgentState:
        assessment = await self.assess(state)
        state.has_contradiction = assessment.has_contradiction
        state.contradiction_reason = assessment.contradiction_reason
        return state


assessor = Assessor()
