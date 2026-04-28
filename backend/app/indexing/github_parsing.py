# Backwards-compatibility shim.
# GitHubParser now lives in app.indexing.parsers.github.
# Existing imports of the form:
#   from app.indexing.github_parsing import GitHubParser
#   from app.indexing.github_parsing import CodeElement
# continue to work without modification.
from app.indexing.parsers.github import GitHubParser  # noqa: F401
from app.indexing.documents import CodeElement  # noqa: F401
