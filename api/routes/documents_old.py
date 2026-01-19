from fastapi import APIRouter, UploadFile, Depends, HTTPException, status, Form, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from core.database import get_db
from db.models import Document, Thread, User, DocumentChunk
from services.ingestion import DocumentIngestor
from services.vector_db_faiss import FAISSVectorDB
from langchain_core.documents import Document as LCDocument
from pathlib import Path
from pydantic import UUID4
import hashlib, os, shutil                   # your FAISS wrapper
from sqlalchemy import select, delete
from core.config import UPLOAD_DIR, ALLOWED_EXT, MAX_SIZE, MIME_MAP    
from api.dependencies import get_current_user
from typing import List
import logging

logger = logging.getLogger(__name__)


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
    user_id_value = thread_row.user_id
    thread_id_value = thread_row.id
   
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

        # ------ Insert Document Row ------
        file_type = MIME_MAP.get(ext, "unknown")

        # ------ Duplicate Check BEFORE adding ------
        existing_doc = (
            await db.execute(
                select(Document).where(
                    Document.sha256_hash == sha256_hash,
                    Document.thread_id == thread_id_value,
                    Document.user_id == user_id_value
                )
            )
        ).scalar_one_or_none()

        if existing_doc:
            processed_docs.append({
                "file_name": file.filename,
                "status": "duplicate_skipped",
                "document_id": existing_doc.id
            })
            continue

        # ------ Add Document ------
        doc = Document(
            user_id=user_id_value,
            thread_id=thread_id_value,
            file_name=file.filename,
            file_path=str(file_path),
            file_type=file_type,
            sha256_hash=sha256_hash,
        )
        db.add(doc)

        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            
            # Check if duplicate exists in current thread
            existing_doc = (
                await db.execute(
                    select(Document).where(
                        Document.thread_id == thread_id_value,
                        Document.sha256_hash == sha256_hash,
                        Document.user_id == user_id_value
                    )
                )
            ).scalar_one_or_none()

            if existing_doc:
                # Duplicate in the same thread -> skip normally
                processed_docs.append({
                    "file_name": file.filename,
                    "status": "duplicate_skipped",
                    "document_id": existing_doc.id
                })
                continue
            else:
                # Duplicate in another thread -> show user friendly message
                processed_docs.append({
                    "file_name": file.filename,
                    "status": "duplicate_in_other_thread",
                    "thread_id": str(existing_doc.thread_id) if existing_doc else "unknown"
                })
                continue

        await db.refresh(doc)
        document_id = doc.id
        document_path = doc.file_path
        document_name = doc.file_name


        # ------ Ingest into VectorDB ------
        ingestor = DocumentIngestor(db=db)
        chunks = await ingestor.ingest_document(
            document_id=document_id,
            document_path=document_path,
            document_name=document_name,
            thread_id=thread_id_value,
            vector_db=vector_db,
        )

        processed_docs.append({
            "document_id": document_id,
            "file_name": document_name,
            "chunks": chunks,
            "status": "processed"
        })


    # 2. DTO
    return {
        "thread_id": thread_id_value,
        "total": len(files),
        "uploaded": sum(1 for d in processed_docs if d["status"] == "processed"),
        "skipped": sum(1 for d in processed_docs if d["status"] == "duplicate_skipped"),
        "processed": processed_docs
    }



@router.delete("/delete/{thread_id}/{doc_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    thread_id: UUID4,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    vector_db: FAISSVectorDB = Depends(FAISSVectorDB.get_instance),
    user: User = Depends(get_current_user),
):
        try:
            # 1️⃣ Fetch document safely
            stmt = select(Document).where(
                Document.id == doc_id,
                Document.thread_id == str(thread_id),
                Document.user_id == user.id
            )
            doc = (await db.execute(stmt)).scalar_one_or_none()

            if not doc:
                # Document already deleted → idempotent success
                return {
                    "status": "already_deleted",
                    "doc_id": doc_id,
                    "thread_id": str(thread_id),
                }
            
            # fetch remaining chunks (excluding deleted document)
            stmt = select(DocumentChunk).join(Document).where(
                Document.thread_id == str(thread_id),
                Document.user_id == user.id,
                Document.id != doc.id,   # exclude deleted document
            )
            remaining_chunks = (await db.execute(stmt)).scalars().all()

            # rebuild FAISS index
            if remaining_chunks:
                langchain_docs = [
                    LCDocument(
                        page_content=chunk.text,
                        metadata={
                            "document_id": chunk.document_id,
                            "chunk_id": chunk.id,
                            "chunk_index": chunk.chunk_index,
                        }
                    )
                    for chunk in remaining_chunks
                ]

                await vector_db.rebuild_thread_index(
                    thread_id=str(thread_id),
                    documents=langchain_docs,
                )
                index_removed = False
            else:
                if await vector_db.exists(str(thread_id)):
                    await vector_db.delete_thread_index(str(thread_id))
                index_removed = True


            # 2️⃣ Delete physical file (non-blocking safety)
            try:
                Path(doc.file_path).unlink(missing_ok=True)
            except Exception as exc:
                logger.warning(
                    "File delete failed %s: %s",
                    doc.file_path,
                    exc
                )
                

            # 4️⃣ Delete DB row
            await db.delete(doc)
            await db.commit()

            # 5️⃣ Return structured response
            return {
                "status": "deleted",
                "vector_index_removed": index_removed,
                "doc_id": doc.id,
                "thread_id": str(thread_id),
                "file_name": doc.file_name,
            }

        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.exception("Delete document failed")
            raise HTTPException(
                status_code=500,
                detail="Failed to delete document"
            )
