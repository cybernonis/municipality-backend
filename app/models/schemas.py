from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# --- AUTH ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

# --- REPORTS ---
class ReportCreate(BaseModel):
    description: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None

class ReportUpdate(BaseModel):
    status: Optional[str] = None
    department_id: Optional[str] = None
    assigned_to: Optional[str] = None
    comment: Optional[str] = None

class ReportResponse(BaseModel):
    id: str
    description: Optional[str]
    image_url: str
    latitude: float
    longitude: float
    address: Optional[str]
    category: Optional[str]
    severity: Optional[str]
    status: str
    ai_confidence: Optional[float]
    created_at: datetime

# --- AI ---
class AIClassificationResult(BaseModel):
    category: str
    severity: str
    department: str
    confidence: float
    reasoning: Optional[str] = None

# --- DEPARTMENTS ---
class DepartmentResponse(BaseModel):
    id: str
    name: str
    slug: str
    contact_email: Optional[str]

# --- ANNOUNCEMENTS ---
class AnnouncementCreate(BaseModel):
    title: str
    body: str
    category: Optional[str] = "general"
    admin_id: Optional[str] = None

class AnnouncementResponse(BaseModel):
    id: str
    title: str
    body: str
    category: Optional[str]
    admin_id: Optional[str]
    created_at: datetime

# --- APPOINTMENTS ---
class AppointmentCreate(BaseModel):
    citizen_id: str
    department_id: str
    scheduled_at: datetime
    reason: Optional[str] = None
    notes: Optional[str] = None

class AppointmentResponse(BaseModel):
    id: str
    citizen_id: str
    department_id: str
    scheduled_at: datetime
    reason: Optional[str]
    notes: Optional[str]
    status: str
    created_at: datetime