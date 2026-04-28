from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.indexing.api import router as indexing_router
from app.chat.api import router as chat_router 
from app.core.db import run_migrations_async, engine
from app.indexing.admin import IndexedRepoAdmin, IndexedFinancialCollectionAdmin
from app.chat.admin import UserAdmin, MessageAdmin
from sqladmin import Admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    admin = Admin(app, engine, title="Admin")
    admin.add_view(IndexedRepoAdmin)
    admin.add_view(IndexedFinancialCollectionAdmin)
    admin.add_view(UserAdmin)
    admin.add_view(MessageAdmin)
    await run_migrations_async()
    yield


app = FastAPI(
    debug=True,
    title="RAG App",
    lifespan=lifespan,
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(indexing_router, prefix="/indexing")
app.include_router(chat_router, prefix="/chat")
