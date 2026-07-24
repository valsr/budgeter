from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    accounts,
    ai,
    backup,
    budgets,
    categories,
    health,
    imports,
    overview,
    rules,
    transactions,
)

app = FastAPI(title="Budgeter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(imports.router)
app.include_router(rules.router)
app.include_router(ai.router)
app.include_router(budgets.router)
app.include_router(backup.router)
app.include_router(overview.router)
