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
    "Lavadora": [{"nombre": "Puerta", "medida": True}, {"nombre": "Motor", "medida": False}, {"nombre": "Placa", "medida": False}],
    "Frigorífico": [{"nombre": "Placa", "medida": False}, {"nombre": "Bandeja", "medida": True}],
    "Arcón frigorífico": [{"nombre": "Tapa", "medida": True}, {"nombre": "Motor", "medida": False}],
    "Lavadora-Secadora": [{"nombre": "Puerta", "medida": True}, {"nombre": "Placa", "medida": False}],
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

@app.get("/imagenes/{item_id}", response_class=HTMLResponse)
def ver_imagenes(item_id: str, request: Request, db: Session = Depends(get_db)):
    fotos = db.query(Imagen).filter(Imagen.item_id == item_id).order_by(Imagen.orden).all()
    return templates.TemplateResponse(request=request, name="imagenes.html", context={"request": request, "fotos": fotos, "item_id": item_id})

@app.post("/subir_imagen/{item_id}")
async def subir_imagen(item_id: str, files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    fotos_existentes = db.query(Imagen).filter(Imagen.item_id == item_id).count()
    for file in files:
        if fotos_existentes >= 5: break
        filename = f"{item_id}_{fotos_existentes+1}.jpg"
        contenido = await file.read()
        comprimido = optimizar_imagen(contenido)
        url = f"{SUPABASE_URL}/storage/v1/object/imagenes/{filename}"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "image/jpeg"}
        requests.put(url, headers=headers, data=comprimido)
        img_db = Imagen(item_id=item_id, url=f"{SUPABASE_URL}/storage/v1/object/public/imagenes/{filename}", orden=fotos_existentes+1)
        db.add(img_db)
        db.commit()
        fotos_existentes += 1
    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.post("/actualizar_diagnostico/{item_id}")
def actualizar_diagnostico(item_id: str, diagnostico: str = Form(...), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    db.add(HistorialDiagnostico(item_id=item_id, diagnostico=diagnostico))
    item.diagnostico_inicial = diagnostico
    db.commit()
    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.get("/buscar_aparatos", response_class=HTMLResponse)
def buscar_aparatos(request: Request, q: str = "", familia_id: int = None, estado: str = "", db: Session = Depends(get_db)):
    query = db.query(Item).filter(Item.parent_id == None)
    if q: query = query.filter(or_(Item.id.ilike(f"%{q}%"), Item.marca.ilike(f"%{q}%"), Item.modelo.ilike(f"%{q}%")))
    if familia_id: query = query.filter(Item.familia_id == familia_id)
    if estado: query = query.filter(Item.estado_actual == estado)
    aparatos = query.all()
    familias = db.query(Familia).all()
    return templates.TemplateResponse(request=request, name="buscar_aparatos.html", context={"request": request, "aparatos": aparatos, "familias": familias})

@app.get("/buscar_piezas", response_class=HTMLResponse)
def buscar_piezas(request: Request, q: str = "", marca: str = "", modelo: str = "", nombre_pieza: str = "", db: Session = Depends(get_db)):
    query = db.query(Item).filter(Item.parent_id != None)
    if q: query = query.filter(or_(Item.id.ilike(f"%{q}%"), Item.marca.ilike(f"%{q}%"), Item.modelo.ilike(f"%{q}%"), Item.nombre_pieza.ilike(f"%{q}%")))
    if marca: query = query.filter(Item.marca.ilike(f"%{marca}%"))
    if modelo: query = query.filter(Item.modelo.ilike(f"%{modelo}%"))
    if nombre_pieza: query = query.filter(Item.nombre_pieza.ilike(f"%{nombre_pieza}%"))
    piezas = query.all()
    return templates.TemplateResponse(request=request, name="buscar_piezas.html", context={"request": request, "piezas": piezas})

@app.get("/qr/{item_id}")
def generar_qr(item_id: str, request: Request):
    img = qrcode.make(f"{request.base_url}item/{item_id}")
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/etiqueta_aparato/{item_id}", response_class=HTMLResponse)
def etiqueta_aparato(item_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    return templates.TemplateResponse(request=request, name="etiqueta_aparato.html", context={"request": request, "item": item})

@app.get("/etiqueta_pieza/{item_id}", response_class=HTMLResponse)
def etiqueta_pieza(item_id: str, request: Request, db: Session = Depends(get_db)):
    pieza = db.query(Item).filter(Item.id == item_id).first()
    return templates.TemplateResponse(request=request, name="etiqueta_pieza.html", context={"request": request, "pieza": pieza})

@app.get("/procesar_camion_2")
async def procesar_camion_2(request: Request, db: Session = Depends(get_db)):
    path = "Copia de ELECTRO ILLUECA 2.xlsx"
    if not os.path.exists(path): return HTMLResponse("Error: Excel no encontrado")
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet = wb.active
    mapa = {'lavadora secadora': 12, 'lavadora': 1, 'frigo': 2, 'secadora': 3, 'lavav': 4, 'horno': 5, 'arcon': 11}
    prefijos = {1:"LAV", 2:"FRI", 3:"SEC", 4:"LAVV", 5:"HOR", 11:"ARC", 12:"LSEC"}
    headers = [str(cell.value).upper() for cell in sheet[1]]
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
            elif 'frigo' in val_tipo or 'combi' in val_tipo or 'vinoteca' in val_tipo: fid = 2
            elif 'lavav' in val_tipo: fid = 4
            elif 'horno' in val_tipo: fid = 5
            elif 'arcon' in val_tipo or 'congelador' in val_tipo: fid = 11
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
    if any(request.url.path.startswith(r) for r in ["/login", "/static", "/qr", "/imagenes", "/etiqueta"]): return await call_next(request)
    if request.cookies.get("auth") != "ok": return RedirectResponse("/login")
    return await call_next(request)
