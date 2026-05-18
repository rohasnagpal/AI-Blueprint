import hashlib
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".md", ".json", ".html", ".htm"}


async def store_upload(file: UploadFile, *, max_bytes: int) -> dict:
    original_name = file.filename or "upload.bin"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not supported",
        )

    temp_name = f".tmp-{uuid.uuid4().hex}{ext}"
    root = get_settings().uploads_dir
    root.mkdir(parents=True, exist_ok=True)
    temp_path = root / temp_name
    size_bytes = 0
    digest = hashlib.sha256()

    try:
        with open(temp_path, "wb") as out:
            while chunk := await file.read(1024 * 64):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds upload limit")
                digest.update(chunk)
                out.write(chunk)

        content_hash = digest.hexdigest()
        final_rel = Path(content_hash[:2]) / f"{content_hash}{ext}"
        final_path = root / final_rel
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if final_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            os.replace(temp_path, final_path)
        return {
            "original_name": original_name,
            "storage_key": final_rel.as_posix(),
            "content_hash": content_hash,
            "mime_type": file.content_type,
            "size_bytes": size_bytes,
        }
    except HTTPException:
        temp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not store upload: {exc}")


def stored_path(storage_key: str) -> Path:
    return get_settings().uploads_dir / storage_key
