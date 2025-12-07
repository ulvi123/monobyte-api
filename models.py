from sqlalchemy import Column,Integer,String,Text,ForeignKey,DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer,primary_key=True)
    name = Column(String, nullable=False)
    repo_url = Column(String,nullable=True)
    created_at = Column(DateTime,default = datetime.utcnow)

    files = relationship("File", back_populates = "project")


class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    path = Column(String, nullable=False)  
    content = Column(Text, nullable=True)
    language = Column(String, nullable=True) 
    
    project = relationship("Project", back_populates="files")