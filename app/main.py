from fastapi import FastAPI, Request, Depends, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi import Header
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, or_
import csv, io, datetime, uuid, qrcode, os, requests, openpyxl
from typing import List
from PIL import Image
from .database import SessionLocal, engine
from .models import Base, Item, Familia, Imagen, HistorialDiagnostico

# --- CONFIG ---
SUPABASE_URL = "https://vmwetkguivvuiehchuax.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZtd2V0a2d1aXZ2dWllaGNodWF4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MjMwNTE1MiwiZXhwIjoyMDg3ODgxMTUyfQ.J1tSVIgoDLOcKD0wj0SFua6UiNJfNH1LAPX3d_DHkPs"

FAMILIAS_PREDEFINIDAS = [
    "Lavadora", "Frigorífico", "Secadora", "Lavavajillas", "Horno",
    "Microondas", "Aire acondicionado", "Termo eléctrico", "Vitroceramica",
    "Placa de Induccion", "Campana extractora", "Arcón frigorífico", "Lavadora-Secadora"
]

PIEZAS_POR_FAMILIA = {
    "Lavadora": [{"nombre": "Puerta", "medida": True}, {"nombre": "Motor", "medida": False}],
    "Frigorífico": [{"nombre": "Placa", "medida": False}, {"nombre": "Bandeja", "medida": True}],
    "Arcón frigorífico": [{"nombre": "Tapa", "medida": True}],
    "Lavadora-Secadora": [{"nombre": "Puerta", "medida": True}],
}

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def optimizar_imagen(imagen_bytes):
    img = Image.open(io.BytesIO(imagen_bytes))
    if img.mode != "RGB": img = img.convert("RGB")
    img.thumbnail((800, 800))
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=60, optimize=True)
    return output.getvalue()

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return RedirectResponse("/panel")

@app.get("/panel", response_class=HTMLResponse)
def panel(request: Request, db: Session = Depends(get_db)):
    familias = db.query(Familia).all()
    return templates.TemplateResponse(request=request, name="panel.html", context={"request": request, "familias": familias})

@app.get("/nuevo", response_class=HTMLResponse)
def nuevo_form(request: Request, db: Session = Depends(get_db)):
    familias = db.query(Familia).all()
    return templates.TemplateResponse(request=request, name="nuevo.html", context={"request": request, "familias": familias})

@app.get("/stock_view", response_class=HTMLResponse)
def stock_view(request: Request, db: Session = Depends(get_db)):
    items = db.query(Item).filter(Item.en_stock == True).all()
    return templates.TemplateResponse(request=request, name="stock.html", context={"request": request, "items": items})

@app.get("/item/{item_id}", response_class=HTMLResponse)
def ver_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: return HTMLResponse("Item no encontrado")
    hijos = db.query(Item).filter(Item.parent_id == item_id).all()
    historial = db.query(HistorialDiagnostico).filter(HistorialDiagnostico.item_id == item_id).order_by(HistorialDiagnostico.fecha.desc()).all()
    return templates.TemplateResponse(request=request, name="item.html", context={"request": request, "item": item, "hijos": hijos, "historial": historial})

@app.post("/importar_amazon")
async def procesar_amazon(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    sheet = wb.active
    mapa = {'lavadora secadora': 12, 'lavadora': 1, 'frigo': 2, 'secadora': 3, 'lavav': 4, 'horno': 5, 'arcon': 11}
    prefijos = {1:"LAV", 2:"FRI", 3:"SEC", 4:"LAVV", 5:"HOR", 11:"ARC", 12:"LSEC"}
    
    # FORMA SEGURA DE LEER CABECERAS
    headers = []
    for cell in sheet[1]:
        val = str(cell.value).upper() if cell.value else ""
        headers.append(val)
    
    idx_tipo = headers.index('TIPO') if 'TIPO' in headers else -1
    items = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row[2]: continue
        fid = None
        if idx_tipo != -1 and row[idx_tipo]:
            val_tipo = str(row[idx_tipo]).lower()
            if 'lavasecadora' in val_tipo or ('lavadora' in val_tipo and 'secadora' in val_tipo): fid = 12
            elif 'lavadora' in val_tipo: fid = 1
            elif 'secadora' in val_tipo: fid = 3
            elif 'frigo' in val_tipo or 'combi' in val_tipo: fid = 2
            elif 'lavav' in val_tipo: fid = 4
            elif 'horno' in val_tipo: fid = 5
            elif 'arcon' in val_tipo: fid = 11
        
        if fid is None:
            desc = str(row[2]).lower()
            fid = next((v for k,v in mapa.items() if k in desc), None)
            
        id_gen = f"{prefijos.get(fid, 'AMZ')}-{str(uuid.uuid4())[:4].upper()}"
        item = Item(id=id_gen, familia_id=fid, nombre_pieza=str(row[2])[:100], numero_serie=str(row[3]), estado_actual="PENDIENTE_CLASIFICAR", origen="AMAZON", camion=2)
        db.add(item)
        items.append(item)
        qr = qrcode.make(f"{request.base_url}item/{id_gen}")
        qr.save(f"app/static/{id_gen}.png")
    db.commit()
    return templates.TemplateResponse(request=request, name="etiquetas_lote.html", context={"request": request, "items": items})

@app.get("/procesar_camion_2")
async def procesar_camion_2(request: Request, db: Session = Depends(get_db)):
    path = "Copia de ELECTRO ILLUECA 2.xlsx"
    if not os.path.exists(path): return HTMLResponse("Error: Excel no encontrado")
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet = wb.active
    mapa = {'lavadora secadora': 12, 'lavadora': 1, 'frigo': 2, 'secadora': 3, 'lavav': 4, 'horno': 5, 'arcon': 11}
    prefijos = {1:"LAV", 2:"FRI", 3:"SEC", 4:"LAVV", 5:"HOR", 11:"ARC", 12:"LSEC"}
    
    headers = []
    for cell in sheet[1]:
        val = str(cell.value).upper() if cell.value else ""
        headers.append(val)
        
    idx_tipo = headers.index('TIPO') if 'TIPO' in headers else -1
    items = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row[2]: continue
        fid = None
        if idx_tipo != -1 and row[idx_tipo]:
            val_tipo = str(row[idx_tipo]).lower()
            if 'lavasecadora' in val_tipo or ('lavadora' in val_tipo and 'secadora' in val_tipo): fid = 12
            elif 'lavadora' in val_tipo: fid = 1
            elif 'secadora' in val_tipo: fid = 3
            elif 'frigo' in val_tipo or 'combi' in val_tipo: fid = 2
            elif 'lavav' in val_tipo: fid = 4
            elif 'horno' in val_tipo: fid = 5
            elif 'arcon' in val_tipo: fid = 11
            
        if fid is None:
            desc = str(row[2]).lower()
            fid = next((v for k,v in mapa.items() if k in desc), None)
            
        id_gen = f"{prefijos.get(fid, 'AMZ')}-{str(uuid.uuid4())[:4].upper()}"
        item = Item(id=id_gen, familia_id=fid, nombre_pieza=str(row[2])[:100], numero_serie=str(row[3]), estado_actual="PENDIENTE_CLASIFICAR", origen="AMAZON", camion=2)
        db.add(item)
        items.append(item)
        qr = qrcode.make(f"{request.base_url}item/{id_gen}")
        qr.save(f"app/static/{id_gen}.png")
    db.commit()
    return templates.TemplateResponse(request=request, name="etiquetas_lote.html", context={"request": request, "items": items})

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == "1234":
        res = RedirectResponse("/panel", status_code=303)
        res.set_cookie(key="auth", value="ok", httponly=True)
        return res
    return HTMLResponse("Login incorrecto")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if any(request.url.path.startswith(r) for r in ["/login", "/static", "/qr"]): return await call_next(request)
    if request.cookies.get("auth") != "ok": return RedirectResponse("/login")
    return await call_next(request)
