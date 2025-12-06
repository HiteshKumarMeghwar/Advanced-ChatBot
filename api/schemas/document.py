from pydantic import BaseModel, UUID4

class DocumentRead(BaseModel):
    id: int
    file_name: str
    file_path: str

    class Config:
        from_attributes = True

class DocumentUploadReq(BaseModel):
    thread_id: UUID4   # or int if you use serial PK