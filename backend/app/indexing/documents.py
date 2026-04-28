from pydantic import BaseModel


class Document(BaseModel):
    text: str
    source: str
    description: str | None = None


class CodeElement(Document):
    header: str | None = None
    extension: str


class FinancialDocument(Document):
    doc_type: str                    # "pdf", "spreadsheet", "csv"
    page_or_sheet: str | None = None # e.g. "page 3" or "Sheet1"
    fiscal_period: str | None = None # e.g. "Q3 2024"
