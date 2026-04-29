from pydantic import BaseModel, Field

from app.chat.agents.quality_control_agent.state import QCChatAgentState
from app.core.clients import async_openai_client, async_openai_client_obs
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the answer-generator in a financial-document RAG pipeline."
    " You answer questions about internal financial reports, spreadsheets, and data files.\n"
    "\n"
    "## Inputs you will receive\n"
    "- **chat_history** -- the full ordered list of prior messages;"
    " the latest user turn contains the question.\n"
    "- **documents** -- retrieved chunks from financial documents; each has:\n"
    "    - `text`          : the raw chunk content\n"
    "    - `source`        : file path (suffix infers type: .pdf = report, .xlsx/.csv = structured data)\n"
    "    - `doc_type`      : pdf, spreadsheet, or csv\n"
    "    - `page_or_sheet` : page number or sheet/row range\n"
    "    - `description`   : brief summary of the chunk\n"
    "\n"
    "## Core behavior\n"
    "1. **Answer the question** from the latest user turn using the provided documents.\n"
    "2. **Report numbers exactly as they appear** in the source"
    " -- do not round, estimate, or interpolate.\n"
    "3. **Source precedence**: structured data (.xlsx, .csv) is the authoritative record"
    " for individual figures; narrative reports (.pdf) provide context and summary figures."
    " When they conflict, report both values and flag the discrepancy clearly.\n"
    "4. **Flag conflicts explicitly**: if two documents contain different values for the"
    " same metric, state both values and both sources directly in the answer."
    " Do not resolve the conflict -- surface it.\n"
    "\n"
    "## Answering rules\n"
    "- Quote numerical figures verbatim from the document text.\n"
    "- Keep the answer concise and factual; markdown tables are encouraged"
    " for multi-value comparisons.\n"
    "- If the documents do not contain the requested information, say so plainly.\n"
    "- **Never fabricate or infer figures** not present in the documents.\n"
    "\n"
    "## Response format (STRICT)\n"
    "Return **only** a JSON object with exactly these two keys:\n"
    "\n"
    "{\n"
    '  "answer": "<your prose answer; no file paths or citations in the text>",\n'
    '  "sources": ["<verbatim source path 1>", "<verbatim source path 2>"]\n'
    "}\n"
    "\n"
    "- `answer`: markdown allowed; no inline file paths or bracketed citations.\n"
    "- `sources`: verbatim `source` values from the supplied documents, unique, no URLs.\n"
    '- Return `"sources": []` if no document facts were used.\n'
    "- No extra keys, no code fences around the JSON.\n"
)


class GeneratedAnswer(BaseModel):
    answer: str = Field(
        ...,
        description="Assistant reply grounded in the retrieved documents; concise, factual, markdown allowed.",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Verbatim source paths from supplied documents; unique, no URLs.",
    )


class Generator:
    async def generate(self, state: QCChatAgentState) -> GeneratedAnswer:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": "### Chat History ###"},
        ]
        messages.extend(state.chat_messages[-10:])
        documents = "\n".join(
            [doc.model_dump_json(indent=2, exclude_none=True) for doc in state.retrieved_documents]
        )
        messages.append({"role": "user", "content": f"### Documents ###\n\n{documents}"})

        try:
            response = await async_openai_client_obs.responses.parse(
                model="gpt-4.1-mini",
                input=messages,
                temperature=0.1,
                text_format=GeneratedAnswer,
            )
        except Exception as e:
            logger.error(str(e))
            raise ConnectionError(f"OpenAI call failed: {e}")

        return response.output_parsed

    async def __call__(self, state: QCChatAgentState) -> QCChatAgentState:
        answer = await self.generate(state)
        state.generation = f"{answer.answer}\n\nSources:\n" + "\n".join(answer.sources)
        return state


generator = Generator()
