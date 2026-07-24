from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import accounts, categories, health, imports, transactions

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
