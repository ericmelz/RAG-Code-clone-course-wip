# Backwards-compatibility shim.
# Indexer now lives in app.indexing.indexers.github.
# Existing imports of the form:
#   from app.indexing.indexer import Indexer
# continue to work without modification.
from app.indexing.indexers.github import GithubIndexer, Indexer  # noqa: F401
