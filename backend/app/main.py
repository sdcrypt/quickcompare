from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="QuickCompare API")

app.include_router(router, prefix="/api")

@app.get("/")
def root():
    return {"message": "QuickCompare API is running"}