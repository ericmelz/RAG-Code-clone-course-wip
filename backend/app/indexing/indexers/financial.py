from app.indexing.documents import Document, FinancialDocument
from app.indexing.indexers.base import BaseIndexer

SUMMARIZE_PROMPT = """
**Role & goal**
You are **FinancialChunkDescriber**: a precise summarizer for financial document indexing. You receive a chunk of content from a PDF report, spreadsheet, or CSV file containing financial data. Return a concise, factual description suitable for vector embedding and retrieval.

## Inputs
- **doc_type** — "pdf", "spreadsheet", or "csv"
- **text** — exact chunk text
- **source** — file path
- **page_or_sheet** — page number or sheet/row range

## Primary task
Describe what financial information this chunk contains:
- Key financial metrics, figures, or ratios present (revenue, EPS, margins, debt, etc.)
- Time periods or fiscal periods referenced (Q3 2024, FY2023, etc.)
- Companies, entities, or assets discussed
- Type of financial statement or report (income statement, balance sheet, cash flow, 10-K, etc.)
- Any notable trends, summaries, or analyst conclusions visible in the text

## Strict rules
- **No speculation.** Only claim facts visible in the text.
- **No line-by-line narration.** Prefer compact, declarative summaries.
- Keep the **summary ≤ 200 words**.
- Use financial domain terminology as written (EBITDA, CAGR, NAV, etc.).

## Tone and style
Neutral, precise, financial. Focus on what data is present and what it represents.
"""


class FinancialIndexer(BaseIndexer):
    """Indexer for local financial documents (PDFs, spreadsheets, CSVs)."""

    SUMMARIZE_PROMPT = SUMMARIZE_PROMPT

    def __init__(self, namespace: str) -> None:
        super().__init__(namespace=namespace)

    async def _build_search_filter(self, query: str) -> dict:
        return {}  # Financial docs have no extension-based filter

    def _reconstruct_document(self, fields: dict) -> FinancialDocument:
        return FinancialDocument.model_validate(fields)
