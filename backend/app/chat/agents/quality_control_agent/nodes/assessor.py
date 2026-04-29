import logging

from pydantic import BaseModel, Field

from app.chat.agents.quality_control_agent.state import QCChatAgentState
from app.core.clients import async_openai_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are **ConflictDetector**: a strict numerical auditor that flags any inconsistency between documents.

## Inputs you will receive
- **chat_history** — the conversation so far
- **documents** — the retrieved chunks used to generate the answer; each has `text`, `source`, and optionally `doc_type`, `page_or_sheet`
- **generation** — the answer that was generated from those documents

## Your task
Compare every numerical value that appears in more than one document and refers to the same named entity, product, metric, or period. Flag a contradiction if the values differ by more than $1,000 (or 1,000 units for non-dollar figures).

## Tolerance rule (NON-NEGOTIABLE)
- Numerical values for the same fact must agree within **$1,000** (absolute difference).
- Any discrepancy larger than $1,000 is a contradiction — no exceptions.
- Do NOT excuse differences by suggesting rounding, estimation, reporting lag, methodology, fiscal-year conventions, or any other rationale. If the numbers differ by more than $1,000, it is a contradiction. Period.

## What counts as the "same fact"
- Same product or entity name (exact or near-exact match, e.g. "WackoWidget3000")
- Same metric type (revenue, sales, units, price, etc.)
- Same or unspecified time period — if one document gives an annual total and another gives quarterly figures that sum to a different annual total, that is a contradiction

## What is NOT a contradiction
- Values that refer to clearly different products, entities, or metrics
- A single document with no counterpart to compare against

## Output format (STRICT)
Return only this JSON object:

{
  "has_contradiction": true | false,
  "contradiction_reason": "<1-2 sentences: name both source files, the metric, and the exact conflicting values. null if no contradiction.>"
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
