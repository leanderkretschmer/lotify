from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, List
from sqlmodel import SQLModel, Field, Session, create_engine, select
import os
import uuid
from fastapi.responses import FileResponse
import asyncio
import time
from fastapi import Header
from datetime import datetime
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
from fastapi import Form, Response, status
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

DB_FILE = "lotify.db"
engine = create_engine(f"sqlite:///{DB_FILE}", echo=False)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CREDENTIALS_FILE = "credentials.json"
SECRET_KEY = os.environ.get("LOTFIY_SESSION_SECRET", "lotify_secret_key")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

admin_users = {}

class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_key: str = Field(index=True, unique=True)
    api_key: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = Field(default=True)

class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id")
    header: str
    content: str
    cdn_id: Optional[str] = None
    delivered: bool = False

class RegisterRequest(BaseModel):
    public_key: str

class SendRequest(BaseModel):
    public_key: str  # Zielgerät
    header: str
    content: str
    cdn_id: Optional[str] = None

class CDNFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cdn_id: str = Field(index=True, unique=True)
    device_id: int = Field(foreign_key="device.id")
    filename: str
    size: int
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    if not os.path.exists(CDN_DIR):
        os.makedirs(CDN_DIR)
    # Credentials laden und Datei löschen
    global admin_users
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            admin_users = json.load(f)
        os.remove(CREDENTIALS_FILE)
    else:
        admin_users = {}

# Dependency für DB-Session
def get_session():
    with Session(engine) as session:
        yield session

# Rate-Limit Speicher (RAM, pro Public Key)
rate_limit: dict = {}
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60  # Sekunden

def check_rate_limit(api_key: str):
    now = int(time.time())
    window = now // RATE_LIMIT_WINDOW
    key = f"{api_key}:{window}"
    count = rate_limit.get(key, 0)
    if count >= RATE_LIMIT_MAX:
        return False
    rate_limit[key] = count + 1
    return True

@app.post("/register")
def register_device(req: RegisterRequest, session: Session = Depends(get_session)):
    device = session.exec(select(Device).where(Device.public_key == req.public_key)).first()
    if device:
        return {"status": "already_registered", "api_key": device.api_key}
    import secrets
    api_key = secrets.token_urlsafe(32)
    device = Device(public_key=req.public_key, api_key=api_key)
    session.add(device)
    session.commit()
    session.refresh(device)
    return {"status": "registered", "api_key": api_key}

@app.post("/send")
def send_message(req: SendRequest, session: Session = Depends(get_session), x_api_key: str = Header(None)):
    device = session.exec(select(Device).where(Device.public_key == req.public_key)).first()
    if not device:
        raise HTTPException(status_code=404, detail="Public key not registered")
    if not x_api_key or x_api_key != device.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not check_rate_limit(x_api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    msg = Message(device_id=device.id, header=req.header, content=req.content, cdn_id=req.cdn_id)
    session.add(msg)
    session.commit()
    return {"status": "message_queued"}

@app.get("/messages/{public_key}")
def get_messages(public_key: str, session: Session = Depends(get_session)):
    device = session.exec(select(Device).where(Device.public_key == public_key)).first()
    if not device:
        raise HTTPException(status_code=404, detail="No device for this key")
    msgs = session.exec(select(Message).where(Message.device_id == device.id)).all()
    return {"messages": [
        {"header": m.header, "content": m.content, "cdn_id": m.cdn_id, "delivered": m.delivered} for m in msgs
    ]}

@app.post("/cdn/upload")
def upload_file(file: UploadFile = File(...), x_api_key: str = Header(None), session: Session = Depends(get_session)):
    device = session.exec(select(Device).where(Device.api_key == x_api_key)).first()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid API key")
    ext = os.path.splitext(file.filename)[1]
    cdn_id = str(uuid.uuid4()) + ext
    file_path = os.path.join(CDN_DIR, cdn_id)
    content = file.file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    cdn_file = CDNFile(cdn_id=cdn_id, device_id=device.id, filename=file.filename, size=len(content))
    session.add(cdn_file)
    session.commit()
    return {"cdn_id": cdn_id}

@app.get("/cdn/{cdn_id}")
def get_file(cdn_id: str):
    file_path = os.path.join(CDN_DIR, cdn_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@app.get("/admin/devices")
def admin_devices(session: Session = Depends(get_session)):
    devices = session.exec(select(Device)).all()
    # Datenverbrauch berechnen
    result = []
    for d in devices:
        # Nachrichten-Größe
        msg_bytes = sum(len(m.content.encode("utf-8")) for m in session.exec(select(Message).where(Message.device_id == d.id)))
        # CDN-Größe
        cdn_bytes = sum(f.size for f in session.exec(select(CDNFile).where(CDNFile.device_id == d.id)))
        data_usage_mb = round((msg_bytes + cdn_bytes) / 1024 / 1024, 2)
        result.append({
            "id": d.id,
            "public_key": d.public_key,
            "api_key": d.api_key,
            "created_at": d.created_at,
            "active": d.active,
            "data_usage_mb": data_usage_mb
        })
    return {"devices": result}

@app.post("/admin/devices/{device_id}/deactivate")
def deactivate_device(device_id: int, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.active = False
    session.add(device)
    session.commit()
    return {"status": "deactivated"}

@app.post("/admin/devices/{device_id}/activate")
def activate_device(device_id: int, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.active = True
    session.add(device)
    session.commit()
    return {"status": "activated"}

active_connections = {}

@app.websocket("/ws/{public_key}")
async def websocket_endpoint(websocket: WebSocket, public_key: str):
    await websocket.accept()
    active_connections[public_key] = websocket
    try:
        while True:
            # Prüfe auf neue, nicht zugestellte Nachrichten
            with Session(engine) as session:
                device = session.exec(select(Device).where(Device.public_key == public_key)).first()
                if not device:
                    await asyncio.sleep(2)
                    continue
                msgs = session.exec(select(Message).where((Message.device_id == device.id) & (Message.delivered == False))).all()
                for m in msgs:
                    await websocket.send_json({
                        "header": m.header,
                        "content": m.content,
                        "cdn_id": m.cdn_id
                    })
                    m.delivered = True
                    session.add(m)
                session.commit()
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        active_connections.pop(public_key, None)

# Hilfsfunktion: Login-Status prüfen
def is_logged_in(request: Request):
    return request.session.get("logged_in") is True

def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=302)

@app.get("/admin/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/admin/login", response_class=HTMLResponse)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username in admin_users and admin_users[username] == password:
        request.session["logged_in"] = True
        return RedirectResponse("/admin/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Login fehlgeschlagen"})

@app.get("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)

# Angepasste Admin-Routen mit Login-Check
@app.get("/admin/", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/admin/devices", response_class=HTMLResponse)
def admin_devices_html(request: Request, session: Session = Depends(get_session)):
    if not is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=302)
    devices = session.exec(select(Device)).all()
    result = []
    for d in devices:
        msg_bytes = sum(len(m.content.encode("utf-8")) for m in session.exec(select(Message).where(Message.device_id == d.id)))
        cdn_bytes = sum(f.size for f in session.exec(select(CDNFile).where(CDNFile.device_id == d.id)))
        data_usage_mb = round((msg_bytes + cdn_bytes) / 1024 / 1024, 2)
        result.append({
            "id": d.id,
            "public_key": d.public_key,
            "api_key": d.api_key,
            "created_at": d.created_at,
            "active": d.active,
            "data_usage_mb": data_usage_mb
        })
    return templates.TemplateResponse("devices.html", {"request": request, "devices": result}) 