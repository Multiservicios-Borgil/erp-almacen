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

PIEZAS_POR_FAMILIA = {
    "Lavadora": [
        {"nombre": "Puerta", "medida": True},
        {"nombre": "Tapa superior", "medida": True},
        {"nombre": "Electroválvula", "medida": False},
        {"nombre": "Presostato", "medida": False},
        {"nombre": "Cajón detergente", "medida": False},
        {"nombre": "Placa electrónica", "medida": False},
        {"nombre": "Botonera", "medida": False},
        {"nombre": "Bomba desagüe", "medida": False},
        {"nombre": "Resistencia", "medida": False},
        {"nombre": "Motor", "medida": False},
        {"nombre": "Blocapuertas", "medida": False},
        {"nombre": "Goma escotilla", "medida": False}
    ],
    "Frigorífico": [
        {"nombre": "Placa electronica", "medida": False}, {"nombre": "Compresor", "medida": False},
        {"nombre": "Bandeja", "medida": True}, {"nombre": "Estante cristal", "medida": True},
        {"nombre": "Cajon verdura", "medida": True}, {"nombre": "Maneta puerta", "medida": False},
        {"nombre": "Termostato", "medida": False}, {"nombre": "Ventilador", "medida": False},
        {"nombre": "Sonda temperatura", "medida": False}, {"nombre": "Balcon estante", "medida": True}
    ],
    "Secadora": [
        {"nombre": "Placa electronica", "medida": False}, {"nombre": "Motor", "medida": False},
        {"nombre": "Resistencia", "medida": False}, {"nombre": "Correa", "medida": False}
    ],
    "Lavavajillas": [
        {"nombre": "Cesta superior", "medida": True},
        {"nombre": "Cesta inferior", "medida": True},
        {"nombre": "Blocapuertas", "medida": False},
        {"nombre": "Botonera", "medida": False},
        {"nombre": "Placa electrónica", "medida": False},
        {"nombre": "Bomba desagüe", "medida": False},
        {"nombre": "Motor", "medida": False},
        {"nombre": "Resistencia", "medida": False},
        {"nombre": "Jabonera", "medida": False},
        {"nombre": "Tapa superior", "medida": True},
        {"nombre": "Aquastop", "medida": False},
        {"nombre": "Bomba lavado", "medida": False}
    ],
    "Horno": [
        {"nombre": "Resistencia superior", "medida": False},
        {"nombre": "Resistencia inferior", "medida": False},
        {"nombre": "Ventilador superior", "medida": False},
        {"nombre": "Ventilador inferior", "medida": False},
        {"nombre": "Puerta", "medida": True},
        {"nombre": "Manillera", "medida": False},
        {"nombre": "Selector", "medida": False},
        {"nombre": "Selector temperatura", "medida": False},
        {"nombre": "Placa", "medida": False},
        {"nombre": "Placa termostato", "medida": False},
        {"nombre": "Termostato", "medida": False}
    ],
    "Arcón frigorífico": [
        {"nombre": "Motor-Compresor", "medida": False}, {"nombre": "Termostato", "medida": False},
        {"nombre": "Tapa", "medida": True}
    ],
    "Lavadora-Secadora": [
        {"nombre": "Puerta", "medida": True}, {"nombre": "Placa electronica", "medida": False},
        {"nombre": "Motor", "medida": False}
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

@app.get("/piezas_por_familia/{nombre_familia}")
def get_piezas_por_familia(nombre_familia: str):
    piezas = PIEZAS_POR_FAMILIA.get(nombre_familia, [])
    return [p["nombre"] for p in piezas]

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

@app.post("/crear_item_web")
async def crear_item_web(request: Request, familia_id: int = Form(...), marca: str = Form(...), modelo: str = Form(...), numero_serie: str = Form(None), estado: str = Form(...), db: Session = Depends(get_db)):
    prefijos = {1:"LAV", 2:"FRI", 3:"SEC", 4:"LAVV", 11:"ARC", 12:"LSEC"}
    id_gen = f"{prefijos.get(familia_id, 'ITEM')}-{str(uuid.uuid4())[:4].upper()}"
    item = Item(id=id_gen, familia_id=familia_id, marca=marca, modelo=modelo, numero_serie=numero_serie, estado_actual=estado, en_stock=True)
    db.add(item)
    db.commit()
    return RedirectResponse(f"/item/{id_gen}", status_code=303)

@app.get("/nueva_pieza", response_class=HTMLResponse)
def nueva_pieza_form(request: Request, db: Session = Depends(get_db)):
    familias = db.query(Familia).all()
    aparatos = db.query(Item).filter(Item.parent_id == None).all()
    return templates.TemplateResponse(request=request, name="nueva_pieza.html", context={"request": request, "familias": familias, "aparatos": aparatos})

@app.post("/crear_pieza_directa")
def crear_pieza_directa(request: Request, familia: str = Form(...), nombre_pieza: str = Form(...), medidas: str = Form(None), modelo: str = Form(None), marca: str = Form(...), db: Session = Depends(get_db)):
    familia_obj = db.query(Familia).filter(Familia.nombre == familia).first()
    if not familia_obj: return HTMLResponse("<h2>Familia no encontrada</h2>")
    nuevo_id = f"PZ-{str(uuid.uuid4())[:6].upper()}"
    pieza = Item(id=nuevo_id, nombre_pieza=nombre_pieza, medidas=medidas, modelo=modelo, marca=marca, familia_id=familia_obj.id, estado_actual="REGISTRADO", origen="STOCK_ANTIGUO", en_stock=True)
    db.add(pieza)
    db.commit()
    return RedirectResponse(f"/item/{nuevo_id}", status_code=303)

@app.get("/crear_pieza/{item_id}", response_class=HTMLResponse)
def crear_pieza_form(item_id: str, request: Request):
    return templates.TemplateResponse(request=request, name="crear_pieza.html", context={"request": request, "parent_id": item_id})

@app.post("/crear_pieza/{item_id}")
def crear_pieza(request: Request, item_id: str, nombre_pieza: str = Form(...), medidas: str = Form(None), db: Session = Depends(get_db)):
    padre = db.query(Item).filter(Item.id == item_id).first()
    if not padre: return HTMLResponse("<h2>Item no encontrado</h2>")
    nuevo_id = f"PZ-{str(uuid.uuid4())[:6].upper()}"
    pieza = Item(id=nuevo_id, nombre_pieza=nombre_pieza, medidas=medidas, familia_id=padre.familia_id, estado_actual="REGISTRADO", origen="DESPIECE", parent_id=item_id, en_stock=True)
    db.add(pieza)
    db.commit()
    qr = qrcode.make(f"{request.base_url}item/{nuevo_id}")
    os.makedirs("app/static", exist_ok=True)
    qr.save(f"app/static/{nuevo_id}.png")
    return RedirectResponse(f"/item/{nuevo_id}", status_code=303)

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
        db.add(Imagen(item_id=item_id, url=f"{SUPABASE_URL}/storage/v1/object/public/imagenes/{filename}", orden=fotos_existentes+1))
        db.commit()
        fotos_existentes += 1
    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.post("/actualizar_diagnostico/{item_id}")
def actualizar_diagnostico(item_id: str, diagnostico: str = Form(...), db: Session = Depends(get_db)):
    db.add(HistorialDiagnostico(item_id=item_id, diagnostico=diagnostico))
    db.query(Item).filter(Item.id == item_id).update({"diagnostico_inicial": diagnostico})
    db.commit()
    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.get("/buscar_aparatos", response_class=HTMLResponse)
def buscar_aparatos(request: Request, q: str = "", familia_id: int = None, estado: str = "", en_wallapop: str = "", db: Session = Depends(get_db)):
    query = db.query(Item).filter(Item.parent_id == None, Item.en_stock == True)
    if q: query = query.filter(or_(Item.id.ilike(f"%{q}%"), Item.marca.ilike(f"%{q}%"), Item.modelo.ilike(f"%{q}%")))
    if familia_id: query = query.filter(Item.familia_id == familia_id)
    if estado: query = query.filter(Item.estado_actual == estado)
    if en_wallapop == "si": query = query.filter(Item.en_wallapop == True)
    if en_wallapop == "no": query = query.filter(Item.en_wallapop == False)
    aparatos = query.all()
    familias = db.query(Familia).all()
    return templates.TemplateResponse(request=request, name="buscar_aparatos.html", context={"request": request, "aparatos": aparatos, "familias": familias})

@app.get("/buscar_piezas", response_class=HTMLResponse)
def buscar_piezas(request: Request, q: str = "", familia: str = "", marca: str = "", modelo: str = "", nombre_pieza: str = "", en_wallapop: str = "", db: Session = Depends(get_db)):
    query = db.query(Item).filter(Item.nombre_pieza != None, Item.en_stock == True)
    
    if q: query = query.filter(or_(Item.id.ilike(f"%{q}%"), Item.marca.ilike(f"%{q}%"), Item.modelo.ilike(f"%{q}%"), Item.nombre_pieza.ilike(f"%{q}%")))
    
    if familia:
        f_obj = db.query(Familia).filter(Familia.nombre == familia).first()
        if f_obj: query = query.filter(Item.familia_id == f_obj.id)
        
    if marca: query = query.filter(Item.marca.ilike(f"%{marca}%"))
    if modelo: query = query.filter(Item.modelo.ilike(f"%{modelo}%"))
    if nombre_pieza: query = query.filter(Item.nombre_pieza.ilike(f"%{nombre_pieza}%"))
    if en_wallapop == "si": query = query.filter(Item.en_wallapop == True)
    if en_wallapop == "no": query = query.filter(Item.en_wallapop == False)
    
    piezas = query.all()
    return templates.TemplateResponse(request=request, name="buscar_piezas.html", context={"request": request, "piezas": piezas})

@app.get("/buscar_vendidos", response_class=HTMLResponse)
def buscar_vendidos(request: Request, q: str = "", db: Session = Depends(get_db)):
    query = db.query(Item).filter(Item.en_stock == False)
    if q: query = query.filter(or_(Item.id.ilike(f"%{q}%"), Item.marca.ilike(f"%{q}%"), Item.modelo.ilike(f"%{q}%"), Item.nombre_pieza.ilike(f"%{q}%"), Item.numero_serie.ilike(f"%{q}%")))
    items = query.all()
    return templates.TemplateResponse(request=request, name="buscar_vendidos.html", context={"request": request, "items": items})

@app.post("/revertir_venta/{item_id}")
def revertir_venta(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: return HTMLResponse("<h2>Item no encontrado</h2>")
    item.en_stock = True
    item.estado_actual = "REGISTRADO" # O el estado que desees al volver
    item.fecha_venta = None
    item.precio_venta = None
    item.tipo_venta = None
    item.numero_factura = None
    db.commit()
    return RedirectResponse(f"/item/{item_id}", status_code=303)

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

@app.post("/importar_amazon")
async def procesar_amazon(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
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

@app.get("/procesar_camion_2")
async def procesar_camion_2(request: Request, db: Session = Depends(get_db)):
    # 1. Comprobar si ya existen items del camion 2 en la base de datos
    existentes = db.query(Item).filter(Item.camion == 2).all()
    if existentes:
        # Si ya existen, devolvemos las etiquetas de los que ya tenemos
        return templates.TemplateResponse(request=request, name="etiquetas_lote.html", context={"request": request, "items": existentes})

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
    db.commit()
    return templates.TemplateResponse(request=request, name="etiquetas_lote.html", context={"request": request, "items": items})

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == "1234":
        res = RedirectResponse("/panel", status_code=303)
        res.set_cookie(key="auth", value="ok", max_age=2592000, httponly=True)
        return res
    return HTMLResponse("Login incorrecto")

@app.post("/toggle_wallapop/{item_id}")
def toggle_wallapop(item_id: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: return HTMLResponse("<h2>Item no encontrado</h2>")
    item.en_wallapop = not item.en_wallapop
    db.commit()
    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.post("/cambiar_estado_web/{item_id}")
def cambiar_estado_web(item_id: str, nuevo_estado: str = Form(...), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: return HTMLResponse("<h2>Item no encontrado</h2>")
    item.estado_actual = nuevo_estado
    db.commit()
    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.get("/vender/{item_id}", response_class=HTMLResponse)
def vender_form(item_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: return HTMLResponse("<h2>Item no encontrado</h2>")
    return templates.TemplateResponse(request=request, name="vender.html", context={"request": request, "item": item})

@app.post("/vender/{item_id}")
def procesar_venta(item_id: str, numero_factura: str = Form(None), tipo_venta: str = Form(...), precio: float = Form(...), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item: return HTMLResponse("<h2>Item no encontrado</h2>")
    item.estado_actual = "VENDIDO"
    item.en_stock = False
    item.numero_factura = numero_factura
    item.tipo_venta = tipo_venta
    item.precio_venta = precio
    item.fecha_venta = datetime.datetime.now()
    db.commit()
    return RedirectResponse("/stock_view", status_code=303)

@app.post("/precio/{item_id}")
def actualizar_precio(item_id: str, precio: float = Form(...), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if item:
        item.precio_venta = precio
        db.commit()
    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.post("/eliminar_item/{item_id}")
def eliminar_item(item_id: str, password: str = Form(...), db: Session = Depends(get_db)):
    PASSWORD_ADMIN = "3539"
    if password != PASSWORD_ADMIN:
        return HTMLResponse("<h2>ContraseÃ±a incorrecta</h2>")
    item = db.query(Item).filter(Item.id == item_id).first()
    if item:
        db.query(Imagen).filter(Imagen.item_id == item_id).delete()
        db.delete(item)
        db.commit()
    return RedirectResponse("/panel", status_code=303)


# --- COMPATIBILIDAD ---
MARCAS_CONOCIDAS = ["Bosch", "Siemens", "Balay", "Neff", "Constructa", "Fagor", "Edesa", "Aspes",
    "LG", "Samsung", "Whirlpool", "Beko", "Indesit", "Ariston", "Candy", "Hoover", "Zanussi",
    "Electrolux", "AEG", "Miele", "Teka", "Corbero", "Otsein", "Haier", "Hisense",
    "Brandt", "Pitsos", "Blaupunkt", "Gaggenau", "Thermador", "Junkers", "Lynx",
    "Cata", "Nodor", "Smeg", "Liebherr", "Gorenje", "ATAG", "Kenmore"]

TIPOS_ELECTRO = {
    "lavadora": ["Lavadora"], "washing": ["Lavadora"],
    "lavavajillas": ["Lavavajillas"], "dishwasher": ["Lavavajillas"],
    "secadora": ["Secadora"], "dryer": ["Secadora"],
    "frigorifico": ["Frigorífico"], "fridge": ["Frigorífico"], "refrigerador": ["Frigorífico"],
    "horno": ["Horno"], "oven": ["Horno"],
    "microondas": ["Microondas"],
    "campana": ["Campana extractora"],
    "vitroceramica": ["Vitroceramica", "Placa de Induccion"],
    "induccion": ["Placa de Induccion"],
}

TIPOS_PIEZA = {
    "bomba desague": "Bomba desagüe", "bomba de drenaje": "Bomba desagüe", "drain pump": "Bomba desagüe",
    "bomba desag": "Bomba desagüe",
    "resistencia": "Resistencia", "heating element": "Resistencia",
    "motor": "Motor",
    "placa electronica": "Placa electrónica", "placa electr": "Placa electrónica", "pcb": "Placa electrónica",
    "modulo electronico": "Placa electrónica", "control board": "Placa electrónica",
    "blocapuertas": "Blocapuertas", "door lock": "Blocapuertas", "cierre puerta": "Blocapuertas",
    "electrovalvula": "Electroválvula", "electrov": "Electroválvula", "inlet valve": "Electroválvula",
    "presostato": "Presostato", "pressure switch": "Presostato",
    "puerta": "Puerta", "door": "Puerta",
    "goma escotilla": "Goma escotilla", "junta puerta": "Goma escotilla", "door seal": "Goma escotilla",
    "junta": "Goma escotilla",
    "bomba lavado": "Bomba lavado", "wash pump": "Bomba lavado", "bomba de lavado": "Bomba lavado",
    "cesta superior": "Cesta superior", "cesto superior": "Cesta superior", "upper basket": "Cesta superior",
    "cesta inferior": "Cesta inferior", "cesto inferior": "Cesta inferior", "lower basket": "Cesta inferior",
    "termostato": "Termostato", "thermostat": "Termostato",
    "ventilador": "Ventilador", "fan": "Ventilador",
    "compresor": "Compresor", "compressor": "Compresor",
    "cajon detergente": "Cajón detergente", "detergent drawer": "Cajón detergente",
    "bandeja": "Bandeja", "tray": "Bandeja",
    "estante": "Estante cristal", "shelf": "Estante cristal",
    "botonera": "Botonera", "button panel": "Botonera",
    "jabonera": "Jabonera", "soap dispenser": "Jabonera",
    "aquastop": "Aquastop",
    "correa": "Correa", "belt": "Correa",
    "maneta": "Maneta puerta", "handle": "Maneta puerta",
    "sonda": "Sonda temperatura", "sensor": "Sonda temperatura",
    "tapa superior": "Tapa superior", "top cover": "Tapa superior",
    "selector": "Selector",
    "manillera": "Manillera",
}

def buscar_compatibilidad_web(codigo):
    """Busca un código de pieza en la web usando Serper.dev (Google Search API)."""
    import os, json as json_mod
    api_key = os.getenv("SERPER_API_KEY", "")
    if not api_key:
        return None, "No se ha configurado la API key de Serper. Regístrate gratis en serper.dev y añade SERPER_API_KEY al archivo .env"
    
    try:
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        payload = json_mod.dumps({
            "q": f'"{codigo}" recambio electrodoméstico compatible',
            "gl": "es",
            "hl": "es",
            "num": 8
        })
        r = requests.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=15)
        
        if r.status_code == 401:
            return None, "API key de Serper inválida. Verifica tu SERPER_API_KEY en .env"
        if r.status_code == 429:
            return None, "Se ha superado el límite de búsquedas. Inténtalo más tarde."
        if r.status_code != 200:
            return None, f"Error en la búsqueda web (código {r.status_code})"
        
        data = r.json()
        results = data.get("organic", [])
        
        if not results:
            return None, f"No se encontraron resultados para el código '{codigo}'"
        
        # Extraer info de los snippets
        info = {"codigo_original": codigo, "tipo_pieza": None, "tipo_electrodomestico": None, "marcas": set()}
        web_results = []
        
        all_text = ""
        for result in results:
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            url = result.get("link", "")
            all_text += f" {title} {snippet} "
            web_results.append({"title": title, "snippet": snippet, "url": url})
        
        all_text_lower = all_text.lower()
        
        # Detectar tipo de pieza
        for keyword, pieza_name in TIPOS_PIEZA.items():
            if keyword in all_text_lower:
                info["tipo_pieza"] = pieza_name
                break
        
        # Detectar tipo de electrodoméstico
        for keyword, electro_names in TIPOS_ELECTRO.items():
            if keyword in all_text_lower:
                info["tipo_electrodomestico"] = electro_names[0]
                break
        
        # Detectar marcas
        for marca in MARCAS_CONOCIDAS:
            if marca.lower() in all_text_lower:
                info["marcas"].add(marca)
        
        info["marcas"] = sorted(list(info["marcas"]))
        
        return {"info": info, "web_results": web_results}, None
        
    except requests.exceptions.Timeout:
        return None, "La búsqueda web tardó demasiado. Inténtalo de nuevo."
    except Exception as e:
        return None, f"Error inesperado: {str(e)}"


def buscar_piezas_compatibles(db, info_pieza):
    """Busca en el inventario piezas que puedan ser compatibles."""
    query = db.query(Item).filter(Item.nombre_pieza != None, Item.en_stock == True)
    
    conditions = []
    
    # Filtrar por tipo de pieza si lo conocemos
    if info_pieza.get("tipo_pieza"):
        conditions.append(Item.nombre_pieza.ilike(f"%{info_pieza['tipo_pieza']}%"))
    
    # Filtrar por tipo de electrodoméstico
    if info_pieza.get("tipo_electrodomestico"):
        familia = db.query(Familia).filter(Familia.nombre.ilike(f"%{info_pieza['tipo_electrodomestico']}%")).first()
        if familia:
            query = query.filter(Item.familia_id == familia.id)
    
    # Si tenemos tipo de pieza, filtrar por ella
    if conditions:
        query = query.filter(or_(*conditions))
    
    # Si tenemos marcas compatibles, priorizar pero no excluir
    piezas = query.all()
    
    # Ordenar: primero las que coinciden en marca
    marcas_lower = [m.lower() for m in info_pieza.get("marcas", [])]
    def sort_key(p):
        marca_match = 0
        if p.marca and p.marca.lower() in marcas_lower:
            marca_match = 1
        return -marca_match
    
    piezas.sort(key=sort_key)
    return piezas


@app.get("/compatibilidad", response_class=HTMLResponse)
def compatibilidad_form(request: Request):
    return templates.TemplateResponse(request=request, name="compatibilidad.html", context={"request": request})

@app.get("/buscar_compatibilidad", response_class=HTMLResponse)
def buscar_compatibilidad(request: Request, codigo: str = "", db: Session = Depends(get_db)):
    if not codigo.strip():
        return templates.TemplateResponse(request=request, name="compatibilidad.html", 
            context={"request": request, "error": "Introduce un código de pieza"})
    
    codigo = codigo.strip()
    resultado, error = buscar_compatibilidad_web(codigo)
    
    if error:
        return templates.TemplateResponse(request=request, name="compatibilidad.html",
            context={"request": request, "codigo": codigo, "error": error})
    
    info_pieza = resultado["info"]
    web_results = resultado["web_results"]
    piezas_stock = buscar_piezas_compatibles(db, info_pieza)
    
    return templates.TemplateResponse(request=request, name="compatibilidad.html",
        context={
            "request": request,
            "codigo": codigo,
            "info_pieza": info_pieza,
            "resultados_web": web_results,
            "piezas_stock": piezas_stock
        })


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if any(request.url.path.startswith(r) for r in ["/login", "/static", "/qr", "/imagenes", "/etiqueta"]): return await call_next(request)
    if request.cookies.get("auth") != "ok": return RedirectResponse("/login")
    return await call_next(request)
