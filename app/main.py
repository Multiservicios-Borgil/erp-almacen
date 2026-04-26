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
    "Lavadora": [
        {"nombre": "Puerta", "medida": True}, {"nombre": "Placa electronica", "medida": False},
        {"nombre": "Motor", "medida": False}, {"nombre": "Bomba desague", "medida": False},
        {"nombre": "Cajon detergente", "medida": False}, {"nombre": "Resistencia", "medida": False},
        {"nombre": "Blocapuertas", "medida": False},
    ],
    "Frigorífico": [
        {"nombre": "Placa", "medida": False}, {"nombre": "Motor-Compresor", "medida": False},
        {"nombre": "Bandeja", "medida": True}, {"nombre": "Cajon frutas", "medida": True},
        {"nombre": "Estante cristal", "medida": True},
    ],
    "Arcón frigorífico": [
        {"nombre": "Motor-Compresor", "medida": False}, {"nombre": "Termostato", "medida": False},
        {"nombre": "Tapa", "medida": True}, {"nombre": "Cesta interior", "medida": True},
    ],
    "Lavadora-Secadora": [
        {"nombre": "Puerta", "medida": True}, {"nombre": "Placa electronica", "medida": False},
        {"nombre": "Motor", "medida": False}, {"nombre": "Resistencia secado", "medida": False},
    ],
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
    return templates.TemplateResponse(request=request, name="panel.html", context={"familias": familias})

@app.get("/nuevo", response_class=HTMLResponse)
def nuevo_form(request: Request, db: Session = Depends(get_db)):
    familias = db.query(Familia).all()
    return templates.TemplateResponse(request=request, name="nuevo.html", context={"familias": familias})

@app.post("/crear_item_web")
def crear_item_web(request: Request, familia_id: int = Form(...), numero_serie: str = Form(...), 
                   marca: str = Form(...), modelo: str = Form(None), origen: str = Form(...), 
                   diagnostico_inicial: str = Form(None), db: Session = Depends(get_db)):
    prefijos = {1: "LAV", 2: "FRI", 3: "SEC", 4: "LAVV", 5: "HOR", 6: "MIC", 7: "AIRE", 8: "TER", 9: "VIT", 10: "CAM", 11: "ARC", 12: "LSEC"}
    nuevo_id = f"{prefijos.get(familia_id, 'ART')}-{str(uuid.uuid4())[:4].upper()}"
    item = Item(id=nuevo_id, familia_id=familia_id, numero_serie=numero_serie, marca=marca, modelo=modelo, 
                estado_actual="REGISTRADO", origen=origen, diagnostico_inicial=diagnostico_inicial)
    db.add(item)
    db.commit()
    qr = qrcode.make(f"{request.base_url}item/{nuevo_id}")
    os.makedirs("app/static", exist_ok=True)
    qr.save(f"app/static/{nuevo_id}.png")
    return RedirectResponse(f"/item/{nuevo_id}", status_code=303)

@app.get("/item/{item_id}", response_class=HTMLResponse)
def ver_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: return HTMLResponse("Item no encontrado")
    hijos = db.query(Item).filter(Item.parent_id == item_id).all()
    historial = db.query(HistorialDiagnostico).filter(HistorialDiagnostico.item_id == item_id).order_by(HistorialDiagnostico.fecha.desc()).all()
    return templates.TemplateResponse(request=request, name="item.html", context={"item": item, "hijos": hijos, "historial": historial})

@app.get("/stock_view", response_class=HTMLResponse)
def stock_view(request: Request, db: Session = Depends(get_db)):
    items = db.query(Item).filter(Item.en_stock == True).all()
    return templates.TemplateResponse(request=request, name="stock.html", context={"items": items})

@app.get("/scan", response_class=HTMLResponse)
def scan_page(request: Request):
    return templates.TemplateResponse(request=request, name="scan.html")

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

@app.get("/vender/{item_id}", response_class=HTMLResponse)
def vender_form(item_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    return templates.TemplateResponse(request=request, name="vender.html", context={"item": item})

@app.post("/vender/{item_id}")
def procesar_venta(item_id: str, numero_factura: str = Form(None), tipo_venta: str = Form(...), precio: float = Form(...), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    item.estado_actual, item.en_stock = "VENDIDO", False
    item.numero_factura, item.tipo_venta, item.precio_venta = numero_factura, tipo_venta, precio
    item.fecha_venta = datetime.datetime.now()
    db.commit()
    return RedirectResponse("/stock_view", status_code=303)

@app.get("/etiqueta_aparato/{item_id}", response_class=HTMLResponse)
def etiqueta_aparato(item_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    return templates.TemplateResponse(request=request, name="etiqueta_aparato.html", context={"item": item})

@app.get("/etiqueta_pieza/{item_id}", response_class=HTMLResponse)
def etiqueta_pieza(item_id: str, request: Request, db: Session = Depends(get_db)):
    pieza = db.query(Item).filter(Item.id == item_id).first()
    return templates.TemplateResponse(request=request, name="etiqueta_pieza.html", context={"pieza": pieza})

@app.post("/actualizar_diagnostico/{item_id}")
def actualizar_diagnostico(item_id: str, diagnostico: str = Form(...), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    db.add(HistorialDiagnostico(item_id=item_id, diagnostico=diagnostico))
    item.diagnostico_inicial = diagnostico
    db.commit()
    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.post("/eliminar_item/{item_id}")
def eliminar_item(item_id: str, password: str = Form(...), db: Session = Depends(get_db)):
    if password != "3539": return HTMLResponse("Contraseña incorrecta")
    db.query(Imagen).filter(Imagen.item_id == item_id).delete()
    db.query(Item).filter(Item.id == item_id).delete()
    db.commit()
    return RedirectResponse("/panel", status_code=303)

@app.get("/qr/{item_id}")
def generar_qr(item_id: str, request: Request):
    img = qrcode.make(f"{request.base_url}item/{item_id}")
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# --- AMAZON ---
@app.get("/importar_amazon", response_class=HTMLResponse)
def importar_amazon_form(request: Request):
    return templates.TemplateResponse(request=request, name="importar_amazon.html")

@app.post("/importar_amazon")
async def procesar_amazon(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
    sheet = wb.active
    mapa = {"lavadora secadora": 12, "lavasecadora": 12, "lavadora": 1, "secadora": 3, "frigorifico": 2, "vinoteca": 2, "lavavajillas": 4, "horno": 5, "arcon": 11}
    prefijos = {1:"LAV", 2:"FRI", 3:"SEC", 4:"LAVV", 5:"HOR", 11:"ARC", 12:"LSEC"}
    items = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row[2]: continue
        desc = str(row[2]).lower()
        fid = next((v for k,v in mapa.items() if k in desc), None)
        id_gen = f"{prefijos.get(fid, 'AMZ')}-{str(uuid.uuid4())[:4].upper()}"
        item = Item(id=id_gen, familia_id=fid, nombre_pieza=str(row[2])[:100], numero_serie=str(row[3]), estado_actual="PENDIENTE_CLASIFICAR", origen="AMAZON", camion=2)
        db.add(item)
        items.append(item)
        qr = qrcode.make(f"{request.base_url}item/{id_gen}")
        qr.save(f"app/static/{id_gen}.png")
    db.commit()
    return templates.TemplateResponse(request=request, name="etiquetas_lote.html", context={"items": items})

@app.get("/procesar_camion_2")
async def procesar_camion_2(request: Request, db: Session = Depends(get_db)):
    path = "Copia de ELECTRO ILLUECA 2.xlsx"
    if not os.path.exists(path): return HTMLResponse("Error: Excel no encontrado")
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet = wb.active
    mapa = {"lavadora secadora": 12, "lavasecadora": 12, "lavadora": 1, "frigorifico": 2, "arcon": 11}
    prefijos = {1:"LAV", 2:"FRI", 11:"ARC", 12:"LSEC"}
    items = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row[2]: continue
        desc = str(row[2]).lower()
        fid = next((v for k,v in mapa.items() if k in desc), None)
        id_gen = f"{prefijos.get(fid, 'AMZ')}-{str(uuid.uuid4())[:4].upper()}"
        item = Item(id=id_gen, familia_id=fid, nombre_pieza=str(row[2])[:100], numero_serie=str(row[3]), estado_actual="PENDIENTE_CLASIFICAR", origen="AMAZON", camion=2)
        db.add(item)
        items.append(item)
        qr = qrcode.make(f"{request.base_url}item/{id_gen}")
        qr.save(f"app/static/{id_gen}.png")
    db.commit()
    return templates.TemplateResponse(request=request, name="etiquetas_lote.html", context={"items": items})

# --- SEGURIDAD ---
USUARIO, PASSWORD = "admin", "1234"
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username == USUARIO and password == PASSWORD:
        res = RedirectResponse("/panel", status_code=303)
        res.set_cookie(key="auth", value="ok", httponly=True)
        return res
    return HTMLResponse("Login incorrecto")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if any(request.url.path.startswith(r) for r in ["/login", "/static", "/qr", "/etiqueta", "/print"]): return await call_next(request)
    if request.cookies.get("auth") != "ok": return RedirectResponse("/login")
    return await call_next(request)
