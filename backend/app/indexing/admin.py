from sqladmin import ModelView
from app.indexing.models import IndexedGithubRepo, IndexedFinancialCollection


class IndexedRepoAdmin(ModelView, model=IndexedGithubRepo):
    column_list = [
        IndexedGithubRepo.id,
        IndexedGithubRepo.github_url,
        IndexedGithubRepo.namespace,
        IndexedGithubRepo.indexed_at,
        IndexedGithubRepo.updated_at,
    ]
    column_searchable_list = [IndexedGithubRepo.github_url]
    column_sortable_list = [IndexedGithubRepo.indexed_at]


class IndexedFinancialCollectionAdmin(ModelView, model=IndexedFinancialCollection):
    column_list = [
        IndexedFinancialCollection.id,
        IndexedFinancialCollection.local_path,
        IndexedFinancialCollection.description,
        IndexedFinancialCollection.namespace,
        IndexedFinancialCollection.indexed_at,
        IndexedFinancialCollection.updated_at,
    ]
    column_searchable_list = [IndexedFinancialCollection.local_path]
    column_sortable_list = [IndexedFinancialCollection.indexed_at]
