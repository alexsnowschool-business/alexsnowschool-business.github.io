import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="apikey")


def require_api_key(key: str = Security(api_key_header)) -> None:
    if key != os.environ["API_KEY"]:
        raise HTTPException(status_code=401, detail="Invalid API key")
