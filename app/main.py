from fastapi import FastAPI, Request, Depends, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import uuid, qrcode, os, openpyxl, io, datetime
from .database import SessionLocal, engine
from .models import Base, Item, Familia, Imagen, HistorialDiagnostico

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- RUTAS PRINCIPALES ---
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
    return templates.TemplateResponse(request=request, name="nueva_pieza.html", context={"familias": familias})

@app.get("/item/{item_id}", response_class=HTMLResponse)
def ver_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: return HTMLResponse("Item no encontrado")
    return templates.TemplateResponse(request=request, name="item.html", context={"item": item})

# --- AMAZON Y CAMIÓN 2 ---
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
        os.makedirs("app/static", exist_ok=True)
        qr.save(f"app/static/{id_gen}.png")
    db.commit()
    return templates.TemplateResponse(request=request, name="etiquetas_lote.html", context={"items": items})

@app.get("/procesar_camion_2")
async def procesar_camion_2(request: Request, db: Session = Depends(get_db)):
    path = "Copia de ELECTRO ILLUECA 2.xlsx"
    if not os.path.exists(path): return HTMLResponse("Error: Excel no encontrado")
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet = wb.active
    mapa = {"lavadora secadora": 12, "lavadora": 1, "frigorifico": 2, "arcon": 11}
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
    if any(request.url.path.startswith(r) for r in ["/login", "/static", "/qr"]): return await call_next(request)
    if request.cookies.get("auth") != "ok": return RedirectResponse("/login")
    return await call_next(request)
