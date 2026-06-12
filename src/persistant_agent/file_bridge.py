import base64
import hashlib
from pathlib import Path

from fastapi import HTTPException, status

from persistant_agent.docker_registry import AgentRecord


def write_repo_file(agent: AgentRecord, path: str, content_base64: str) -> dict:
    if agent.repo_path is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent has no repo path label")
    raw = Path(path)
    if raw.is_absolute() or ".." in raw.parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File paths must be repo-relative")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 content") from exc
    repo = Path(agent.repo_path).resolve()
    destination = (repo / raw).resolve()
    if destination != repo and repo not in destination.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File path escapes repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return {"path": str(destination.relative_to(repo)), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
