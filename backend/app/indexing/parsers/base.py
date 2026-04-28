from typing import Protocol
from app.indexing.documents import Document


class BaseParser(Protocol):
    def parse(self) -> list[Document]: ...
