"""Single external entry point; no SQL or domain decisions in HTTP layer."""
from fastapi import FastAPI
from ariadne.asgi import GraphQL
from sqlalchemy import text
from app.gateway.schema import schema
from app.transport.mock_ports import ports
from app.core.db import engine

app = FastAPI(title="Tutoring Platform — Lab 3, Variant 27", version="3.0")


async def context_value(request, data=None):
    authorization = request.headers.get("authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    return {"actor": ports.ValidateSession(token)}


@app.get("/health")
def health():
    return {"status": "ok", "laboratory": 3, "variant": 27}


@app.get("/ready")
def ready():
    """Readiness checks all seven independent physical databases."""
    result = {}
    for owner in "atlprnx":
        try:
            with engine(owner).connect() as conn:
                conn.execute(text("SELECT 1"))
            result[owner] = "ok"
        except Exception:
            result[owner] = "unavailable"
    from fastapi import HTTPException
    if any(value != "ok" for value in result.values()):
        raise HTTPException(status_code=503, detail=result)
    return {"status": "ready", "databases": result}


app.mount("/graphql", GraphQL(schema, debug=False, context_value=context_value))
