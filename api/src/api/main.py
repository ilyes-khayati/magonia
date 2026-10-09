import engine
from fastapi import FastAPI

app = FastAPI(title="Agri Workbench API", version="0.0.1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": engine.__version__}
