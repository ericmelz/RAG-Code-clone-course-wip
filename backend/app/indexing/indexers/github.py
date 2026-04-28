from pydantic import BaseModel, Field
from typing import Literal

from app.core.clients import async_openai_client
from app.indexing.documents import CodeElement, Document
from app.indexing.indexers.base import BaseIndexer

SUMMARIZE_PROMPT = """
**Role & goal**
You are **ChunkDescriber**: a precise, non-speculative summarizer for RAG indexing. You receive a chunk of content that is either **code** or **documentation** and must return a concise, factual description. The summary will be embedded, so keep it dense, informative, and free of fluff.

## Inputs (variables)
- **KIND** — `".py"` or `".md"`.
- **TEXT** — exact chunk text.
- **PATH** — repo-relative file path.
- **HEADER** — optional context (imports/front-matter/breadcrumbs); may be empty.

## Primary task
- If **KIND = ".py"**: describe what the code does **at runtime**.
  Focus on: purpose; inputs/outputs; side effects (filesystem/network/db/stdout/logging/random/time/env/global state/concurrency); external APIs/libraries; notable control flow (retry/caching/memoization/error handling); invariants/constraints.
  If tests, summarize the behavior/spec asserted. If partial, say so and describe only what's visible.

- If **KIND = ".md"**: describe what the text explains or specifies.
  Focus on: purpose & audience; key topics/sections; procedures/steps or workflows; commands/API endpoints/config flags/parameters; expected outcomes; prerequisites/assumptions; notable links/anchors; important tables or code fences (languages).
  Describe only what's visible.

## Strict rules
- **No speculation.** Only claim facts visible in TEXT/HEADER/TITLE. If unknown, say "unknown" or omit.
- **No line-by-line narration** or pseudocode. Prefer compact, declarative summaries.
- **Do not invent** types, effects, or claims not evidenced in the chunk.
- **No chain-of-thought.** Provide conclusions only.
- Keep the **summary ≤ 200 words** (up to 250 if unusually complex).
- Use domain terms as written (e.g., *S3*, *SQLAlchemy*, *requests*, *NumPy*, *kubectl*).

## Tone and style
Neutral, technical, terse. No marketing language. No hypotheticals beyond what the code shows.
"""

FILTER_SYSTEM_PROMPT = """
You are **FilterSelector**, a strict router that sets `DocumentType.type` to choose the best file-type filter for retrieval.

## Goal
Given a user query, return exactly one of:
- **'code'** → prioritize Python source files (maps to ['.py'])
- **'doc'**  → prioritize Markdown docs (maps to ['.md'])
- **'both'** → include both when the query likely needs code and docs, or is ambiguous (maps to ['.py', '.md'])

## Decision rules
1) Choose **'code'** when the query strongly targets implementation details or APIs.
2) Choose **'doc'** for conceptual/usage/overview/installation material.
3) Choose **'both'** when the query mixes concept + implementation, or is ambiguous.

## Output format (STRICT)
Return **only** a JSON object: {"type": "code" | "doc" | "both"}
No extra fields, no prose, no code fences.
"""


class DocumentType(BaseModel):
    type: Literal["code", "doc", "both"] = Field(
        ...,
        description="Picker for Pinecone file-type filtering.",
    )


class GithubIndexer(BaseIndexer):
    """Indexer for GitHub repository code and documentation."""

    SUMMARIZE_PROMPT = SUMMARIZE_PROMPT

    def __init__(self, owner=None, repo=None, ref=None, namespace=None) -> None:
        ns = namespace or (f"{owner}-{repo}-{ref}" if ref else f"{owner}-{repo}")
        super().__init__(namespace=ns)

    async def _build_search_filter(self, query: str) -> dict:
        messages = [
            {"role": "system", "content": FILTER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Query: {query}"},
        ]
        try:
            response = await async_openai_client.responses.parse(
                model="gpt-4.1-nano",
                input=messages,
                temperature=0.1,
                timeout=30.0,
                text_format=DocumentType,
            )
            doc_type = response.output_parsed.type
        except Exception:
            doc_type = "both"

        ext_map = {"code": [".py"], "doc": [".md"], "both": [".py", ".md"]}
        return {"extension": {"$in": ext_map.get(doc_type, [".py", ".md"])}}

    def _reconstruct_document(self, fields: dict) -> CodeElement:
        return CodeElement.model_validate(fields)


# Keep old name as alias so all existing `from app.indexing.indexer import Indexer` keep working
Indexer = GithubIndexer
