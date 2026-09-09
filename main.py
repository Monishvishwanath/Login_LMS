import hashlib
from io import BytesIO
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, File, HTTPException, UploadFile, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, LargeBinary, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
import pandas as pd
import os
from pathlib import Path


# DATABASE CONFIGURATION
DATABASE_URL = "sqlite:///./lms_database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# DATABASE MODELS

class UploadedFileDB(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_hash = Column(String, unique=True, index=True, nullable=False)
    file_data = Column(LargeBinary, nullable=True)  # Stores original Excel binary
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    leads = relationship("LeadDB", back_populates="file", cascade="all, delete-orphan")


class LeadDB(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=False)
    name = Column(String, nullable=True)
    owner = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    campaign = Column(String, nullable=True)
    date = Column(String, nullable=True)
    email = Column(String, nullable=True)
    stage = Column(String, default="New")

    file = relationship("UploadedFileDB", back_populates="leads")


class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default="employee")


Base.metadata.create_all(bind=engine)


# FASTAPI APP SETUP
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def seed_default_users():
    db = SessionLocal()
    try:
        admin_user = db.query(UserDB).filter(UserDB.username == "admin").first()
        if not admin_user:
            db.add(UserDB(name="Manager Admin", username="admin", password="admin123", role="manager"))
        
        employee_user = db.query(UserDB).filter(UserDB.username == "john").first()
        if not employee_user:
            db.add(UserDB(name="John Doe", username="john", password="john123", role="employee"))
            
        db.commit()
    finally:
        db.close()


# PYDANTIC SCHEMAS

class StageUpdateSchema(BaseModel):
    stage: str

class LoginSchema(BaseModel):
    username: str
    password: str

class SignUpSchema(BaseModel):
    name: str
    username: str
    password: str
    role: Optional[str] = "employee"


# ROUTES

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/signup")
def signup(data: SignUpSchema, db: Session = Depends(get_db)):
    existing_user = db.query(UserDB).filter(UserDB.username == data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists.")

    user = UserDB(name=data.name, username=data.username, password=data.password, role=data.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Account created successfully", "user": {"name": user.name, "username": user.username, "role": user.role}}


@app.post("/api/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == data.username, UserDB.password == data.password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    return {"user": {"name": user.name, "username": user.username, "role": user.role}}


@app.post("/api/upload-excel")
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Invalid file type. Only Excel files (.xlsx, .xls) are allowed.")

    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    existing_file = db.query(UploadedFileDB).filter(UploadedFileDB.file_hash == file_hash).first()
    if existing_file:
        existing_leads = db.query(LeadDB).filter(LeadDB.file_id == existing_file.id).all()
        return {
            "message": f"File '{existing_file.filename}' already exists in the database. Loading existing records.",
            "file_id": existing_file.id,
            "leads": [
                {
                    "id": l.id, "file_id": l.file_id, "name": l.name, "owner": l.owner,
                    "phone": l.phone, "campaign": l.campaign, "date": l.date, "email": l.email, "stage": l.stage
                }
                for l in existing_leads
            ]
        }

    try:
        df = pd.read_excel(BytesIO(file_bytes))
        df.columns = [str(col).strip().lower() for col in df.columns]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read Excel file: {str(e)}")

    uploaded_file_record = UploadedFileDB(filename=file.filename, file_hash=file_hash, file_data=file_bytes)
    db.add(uploaded_file_record)
    db.commit()
    db.refresh(uploaded_file_record)

    new_leads = []
    for _, row in df.iterrows():
        lead = LeadDB(
            file_id=uploaded_file_record.id,
            name=str(row.get("registered name") or row.get("name") or "N/A"),
            owner=str(row.get("lead owner") or row.get("owner") or "Unassigned"),
            phone=str(row.get("mobile") or row.get("phone") or "N/A"),
            campaign=str(row.get("campaign") or row.get("source") or "Direct/Organic"),
            date=str(row.get("registration date") or row.get("date") or "N/A"),
            email=str(row.get("email") or "N/A"),
            stage=str(row.get("stage") or "New")
        )
        new_leads.append(lead)

    db.bulk_save_objects(new_leads)
    db.commit()

    return {
        "message": f"Successfully saved '{file.filename}' to database with {len(new_leads)} lead records.",
        "file_id": uploaded_file_record.id
    }


@app.get("/api/uploaded-files")
def get_uploaded_files(db: Session = Depends(get_db)):
    files = db.query(UploadedFileDB).order_by(UploadedFileDB.uploaded_at.desc()).all()
    return {
        "files": [
            {
                "id": f.id,
                "filename": f.filename,
                "uploaded_at": f.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                "lead_count": len(f.leads)
            }
            for f in files
        ]
    }


@app.get("/api/uploaded-files/{file_id}/leads")
def get_leads_by_file(file_id: int, db: Session = Depends(get_db)):
    file_record = db.query(UploadedFileDB).filter(UploadedFileDB.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File record not found.")

    leads = db.query(LeadDB).filter(LeadDB.file_id == file_id).all()
    return {
        "file": {"id": file_record.id, "filename": file_record.filename},
        "leads": [
            {
                "id": lead.id,
                "file_id": lead.file_id,
                "name": lead.name,
                "owner": lead.owner,
                "phone": lead.phone,
                "campaign": lead.campaign,
                "date": lead.date,
                "email": lead.email,
                "stage": lead.stage,
            }
            for lead in leads
        ]
    }


@app.get("/api/uploaded-files/{file_id}/download")
def download_uploaded_file(file_id: int, db: Session = Depends(get_db)):
    file_record = db.query(UploadedFileDB).filter(UploadedFileDB.id == file_id).first()
    if not file_record or not file_record.file_data:
        raise HTTPException(status_code=404, detail="File data not found in database.")

    return Response(
        content=file_record.file_data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={file_record.filename}"}
    )


@app.delete("/api/uploaded-files/{file_id}")
def delete_uploaded_file(file_id: int, db: Session = Depends(get_db)):
    file_record = db.query(UploadedFileDB).filter(UploadedFileDB.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File record not found.")

    db.delete(file_record)
    db.commit()
    return {"message": f"Successfully deleted '{file_record.filename}' and its associated leads."}


@app.get("/api/leads")
def get_leads(db: Session = Depends(get_db)):
    leads = db.query(LeadDB).all()
    return {
        "leads": [
            {
                "id": lead.id,
                "file_id": lead.file_id,
                "name": lead.name,
                "owner": lead.owner,
                "phone": lead.phone,
                "campaign": lead.campaign,
                "date": lead.date,
                "email": lead.email,
                "stage": lead.stage,
            }
            for lead in leads
        ]
    }


@app.patch("/api/leads/{lead_id}/stage")
def update_lead_stage(lead_id: int, payload: StageUpdateSchema, db: Session = Depends(get_db)):
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    lead.stage = payload.stage
    db.commit()
    return {"message": "Stage updated successfully", "lead_id": lead_id, "new_stage": lead.stage}


# ADDED ENDPOINT: Aggregated lead & file statistics
@app.get("/api/leads/summary")
def get_leads_summary(db: Session = Depends(get_db)):
    total_leads = db.query(func.count(LeadDB.id)).scalar() or 0
    total_files = db.query(func.count(UploadedFileDB.id)).scalar() or 0
    
    stage_counts = db.query(LeadDB.stage, func.count(LeadDB.id)).group_by(LeadDB.stage).all()
    stages = {stage: count for stage, count in stage_counts}

    return {
        "total_leads": total_leads,
        "total_files": total_files,
        "stages": stages
    }