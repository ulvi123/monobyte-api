from pydantic import BaseModel

class ProjectCreate(BaseModel):
    name: str

class FileCreate(BaseModel):
    path: str
    content: str

class FileUpdate(BaseModel):
    content: str
