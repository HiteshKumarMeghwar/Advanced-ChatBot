from fastapi import APIRouter, UploadFile, Depends, HTTPException, status, Form, File
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from db.models import Document, Thread, User
from services.ingestion import DocumentIngestor
from services.vector_db_faiss import FAISSVectorDB
from pathlib import Path
from pydantic import UUID4
import hashlib, os, shutil                   # your FAISS wrapper
from sqlalchemy import select
from core.config import UPLOAD_DIR, ALLOWED_EXT, MAX_SIZE, MIME_MAP    
from api.dependencies import get_current_user
from typing import List


router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    files: List[UploadFile] = File(...),
    thread_id: UUID4 = Form(...),              # ← client supplies
    db: AsyncSession = Depends(get_db),
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),  # ← instance
    user: User = Depends(get_current_user),    # ← JWT (demo fallback)
):
    
    # 1. ------ Validate thread ownership ------
    thread_row = (
        await db.execute(
            select(Thread).where(
                Thread.id == str(thread_id),
                Thread.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if not thread_row:
        raise HTTPException(404, "Thread not found or not yours")
   
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    processed_docs = []

    for file in files:
        ext = Path(file.filename).suffix.lower()

        # ------ Validation ------
        if ext not in ALLOWED_EXT:
            raise HTTPException(422, f"Unsupported file type: {file.filename}")
        if file.size and file.size > MAX_SIZE:
            raise HTTPException(413, f"File too large: {file.filename}")

        # ------ Save physical file ------
        hashed_name = hashlib.sha256(file.filename.encode()).hexdigest()
        file_path = Path(UPLOAD_DIR) / f"{hashed_name}{ext}"

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # ------ Real SHA256 ------
        sha256_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

        # ------ Duplicate Check ------
        existing_doc = (
            await db.execute(select(Document).where(Document.sha256_hash == sha256_hash))
        ).scalar_one_or_none()

        if existing_doc:
            # Skip duplicates instead of failing the whole batch
            processed_docs.append({
                "file_name": file.filename,
                "status": "duplicate_skipped",
                "document_id": existing_doc.id
            })
            continue

        # ------ Insert Document Row ------
        file_type = MIME_MAP.get(ext, "unknown")

        doc = Document(
            user_id=user.id,
            thread_id=thread_row.id,
            file_name=file.filename,
            file_path=str(file_path),
            file_type=file_type,
            sha256_hash=sha256_hash,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # ------ Ingest into VectorDB ------
        ingestor = DocumentIngestor(db=db)
        chunks = await ingestor.ingest_document(doc, vector_db=vector_db)

        processed_docs.append({
            "document_id": doc.id,
            "file_name": doc.file_name,
            "chunks": chunks,
            "status": "processed"
        })


    # 2. DTO
    return {
        "thread_id": thread_row.id,
        "total": len(files),
        "processed": processed_docs
    }