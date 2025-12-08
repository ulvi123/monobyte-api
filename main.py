from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db,get_db
from fastapi import Depends
from sqlalchemy.orm import Session
from models import Project,File
from schemas import ProjectCreate, FileCreate
import multiprocessing


app = FastAPI()

#Allowing front end to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["http://localhost:5173"],
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"]
)


@app.get("/")
async def root():
    return {"message":"CoFrame API is live!"}

@app.get("/health")
async def helath():
    return {"status" : "healthy", "version":"0.1.0"}


@app.post("/projects")
async def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id":project.id, "name": project.name}


@app.get("/projects/{project_id}/files")
async def get_files(project_id: int, db: Session = Depends(get_db)):
    files = db.query(File).filter(File.project_id == project_id).all()
    return [
        {
            "id": f.id,
            "path": f.path,
            "language": f.language,
            "content": f.content
        }
        for f in files
    ]

@app.get("/projects")
async def get_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "repo_url": p.repo_url,
            "created_at": p.created_at
        }
        for p in projects
    ]



@app.post("/projects/{project_id}/files")
async def create_file(project_id: int, payload: FileCreate, db: Session = Depends(get_db)):
    file = File(
        project_id=project_id,
        path=payload.path,
        content=payload.content
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return {"id": file.id, "path": file.path, "content": file.content}



@app.get("/files/{file_id}")
async def get_file(file_id: int, db: Session = Depends(get_db)):
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        return {"error": "File not found"}
    return {
        "id": file.id,
        "path": file.path,
        "content": file.content,
        "language": file.language,
    }




@app.on_event("startup")
def startup():
    if multiprocessing.current_process().name == "MainPricess":
        init_db()
        print("Database initialized")


