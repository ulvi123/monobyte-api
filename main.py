from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
import multiprocessing
import os
import shutil
from pathlib import Path

# Your existing imports
from database import init_db, get_db
from models import Project, File
from schemas import ProjectCreate, FileCreate, FileUpdate

# Git import
try:
    import git
except ImportError:
    print("WARNING: GitPython not installed. Run: pip install gitpython")
    git = None


app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================
# SCHEMAS
# ============================================
class CloneRequest(BaseModel):
    repo_url: str


# ============================================
# BASIC ENDPOINTS
# ============================================
@app.get("/")
async def root():
    return {"message": "CoFrame API is live!"}


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}


# ============================================
# PROJECT ENDPOINTS
# ============================================
@app.post("/projects")
async def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "name": project.name}


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


# ============================================
# GIT CLONE ENDPOINT
# ============================================
@app.post("/projects/{project_id}/clone")
async def clone_repo(project_id: int, payload: CloneRequest, db: Session = Depends(get_db)):
    """
    Clone a GitHub repository and import all text files into the database
    """
    if git is None:
        return {"error": "GitPython not installed. Run: pip install gitpython"}
    
    # Check if project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": "Project not found"}
    
    # Setup clone directory
    clone_path = f"/tmp/coframe_{project_id}"
    
    # Remove existing clone if it exists
    if os.path.exists(clone_path):
        try:
            shutil.rmtree(clone_path)
            print(f"Removed existing clone at {clone_path}")
        except Exception as e:
            return {"error": f"Failed to clean existing clone: {str(e)}"}
    
    # Clone the repository
    try:
        print(f"Cloning {payload.repo_url} to {clone_path}...")
        repo = git.Repo.clone_from(payload.repo_url, clone_path)
        print(f"Clone successful!")
    except git.GitCommandError as e:
        return {"error": f"Git clone failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to clone repository: {str(e)}"}
    
    # Delete existing files for this project (fresh import)
    try:
        db.query(File).filter(File.project_id == project_id).delete()
        db.commit()
        print(f"Cleared existing files for project {project_id}")
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to clear existing files: {str(e)}"}
    
    files_imported = 0
    files_skipped = 0
    
    # Walk through all files in the cloned repo
    for root, dirs, files in os.walk(clone_path):
        # Skip .git directory
        if '.git' in root:
            continue
        
        # Skip node_modules and other common large directories
        dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', '.next', 'dist', 'build', '.venv', 'venv']]
        
        for file_name in files:
            file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(file_path, clone_path)
            
            # Skip large files (> 1MB)
            try:
                file_size = os.path.getsize(file_path)
                if file_size > 1_000_000:
                    print(f"Skipping large file: {relative_path} ({file_size} bytes)")
                    files_skipped += 1
                    continue
            except:
                files_skipped += 1
                continue
            
            # Try to read as text file
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Detect language from extension
                ext = Path(file_name).suffix.lower()
                language_map = {
                    '.js': 'javascript',
                    '.jsx': 'javascript',
                    '.ts': 'typescript',
                    '.tsx': 'typescript',
                    '.py': 'python',
                    '.html': 'html',
                    '.css': 'css',
                    '.scss': 'scss',
                    '.json': 'json',
                    '.md': 'markdown',
                    '.txt': 'plaintext',
                    '.sh': 'shell',
                    '.bash': 'shell',
                    '.yml': 'yaml',
                    '.yaml': 'yaml',
                    '.xml': 'xml',
                    '.sql': 'sql',
                    '.go': 'go',
                    '.rs': 'rust',
                    '.java': 'java',
                    '.c': 'c',
                    '.cpp': 'cpp',
                    '.h': 'c',
                    '.hpp': 'cpp',
                }
                language = language_map.get(ext, 'plaintext')
                
                # Create database record
                db_file = File(
                    project_id=project_id,
                    path=relative_path,
                    content=content,
                    language=language
                )
                db.add(db_file)
                files_imported += 1
                
                # Commit every 50 files to avoid memory issues
                if files_imported % 50 == 0:
                    db.commit()
                    print(f"Imported {files_imported} files so far...")
                
            except UnicodeDecodeError:
                # Binary file, skip it
                files_skipped += 1
                continue
            except Exception as e:
                print(f"Error reading {relative_path}: {e}")
                files_skipped += 1
                continue
    
    # Final commit
    try:
        db.commit()
        print(f"Final commit: {files_imported} files imported")
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to save files to database: {str(e)}"}
    
    # Update project with repo URL
    try:
        project.repo_url = payload.repo_url
        db.commit()
    except Exception as e:
        print(f"Warning: Failed to update project repo_url: {e}")
    
    # Cleanup: remove cloned directory
    try:
        shutil.rmtree(clone_path)
        print(f"Cleaned up temporary clone directory")
    except Exception as e:
        print(f"Warning: Failed to cleanup {clone_path}: {e}")
    
    return {
        "message": f"Successfully cloned {payload.repo_url}",
        "files_imported": files_imported,
        "files_skipped": files_skipped
    }


# ============================================
# FILE ENDPOINTS
# ============================================
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


@app.patch("/files/{file_id}")
async def update_file(file_id: int, update: FileUpdate, db: Session = Depends(get_db)):
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        return {"error": "File not found"}
    
    file.content = update.content
    db.commit()
    db.refresh(file)
    
    return {"status": "ok", "id": file.id}


# ============================================
# STARTUP EVENT
# ============================================
@app.on_event("startup")
def startup():
    if multiprocessing.current_process().name == "MainProcess":
        init_db()
        print("✅ Database initialized")
        print("✅ CoFrame API ready!")