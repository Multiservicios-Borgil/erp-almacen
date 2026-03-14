from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi import Header
from .models import Evento, Venta
from .models import Base, Item, Familia, Imagen

from sqlalchemy.orm import Session, aliased
from sqlalchemy import func

import csv
import io
import datetime
import uuid
import qrcode
from fastapi.responses import StreamingResponse
import requests



from .database import SessionLocal, engine
from .models import Base, Item, Familia

SUPABASE_URL = "https://vmwetkguivvuiehchuax.supabase.co"
SUPABASE_KEY = "ocCo11SS61o1lYP1"


FAMILIAS_PREDEFINIDAS = [
    "Lavadora",
    "Frigorífico",
    "Secadora",
    "Lavavajillas",
    "Horno",
    "Microondas",
    "Aire acondicionado",
    "Termo eléctrico",
    "Placa vitrocerámica",
    "Campana extractora"
]
PIEZAS_POR_FAMILIA = {

    "Lavadora": [
        {"nombre": "Puerta", "medida": True},
        {"nombre": "Placa electronica", "medida": False},
        {"nombre": "Motor", "medida": False},
        {"nombre": "Frontal", "medida": False},
        {"nombre": "Cajetin", "medida": False},
        {"nombre": "Bomba desague", "medida": False}
    ],

    "Lavavajillas": [
        {"nombre": "Resistencia", "medida": False},
        {"nombre": "Bomba", "medida": False},
        {"nombre": "Resistencia-Bomba", "medida": False},
        {"nombre": "Cesta Superior", "medida": False},
        {"nombre": "Cesta Inferior", "medida": False},
        {"nombre": "Frontal", "medida": False},
        {"nombre": "Placa Frontal", "medida": False},
        {"nombre": "Placa Motor", "medida": False},
        {"nombre": "Tubo aquastop", "medida": False}
    ],

    "Frigorífico": [
        {"nombre": "Placa", "medida": False},
        {"nombre": "Placa-Motor", "medida": False},
        {"nombre": "Arrancador", "medida": False},
        {"nombre": "Bandeja", "medida": True},
        {"nombre": "Botellero", "medida": False},
        {"nombre": "Cajon lateral", "medida": False},
        {"nombre": "Cajon Congelador Superior", "medida": True},
        {"nombre": "Cajon Congelador Medio", "medida": True},
        {"nombre": "Cajon Congelador Inferior", "medida": True},
        {"nombre": "Cajon Izd frigo", "medida": True},
        {"nombre": "Cajon derecho frigo", "medida": True}
    ],

    "Vitroceramica": [
        {"nombre": "Resistencia", "medida": True},
        {"nombre": "Placa", "medida": False}
    ],

    "Placa de Induccion": [
        {"nombre": "Inductores", "medida": True},
        {"nombre": "Placa", "medida": False}
    ],

    "Horno": [
        {"nombre": "Resistencia Superior", "medida": False},
        {"nombre": "Resistencia Inferior", "medida": False},
        {"nombre": "Puerta", "medida": False},
        {"nombre": "Tirador", "medida": False},
        {"nombre": "Selector", "medida": False},
        {"nombre": "Placa", "medida": False}
    ]
}

def crear_familias_predeterminadas():
    db = SessionLocal()
    try:
        for nombre in FAMILIAS_PREDEFINIDAS:
            existe = db.query(Familia).filter(Familia.nombre == nombre).first()
            if not existe:
                db.add(Familia(nombre=nombre))
        db.commit()
    finally:
        db.close()


crear_familias_predeterminadas()

# ---------------- APP ----------------

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")

# ---------------- DB ----------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- ROLES ----------------

def verificar_roles_permitidos(*roles_permitidos):
    def wrapper(x_rol: str = Header()):
        if x_rol not in roles_permitidos:
            raise HTTPException(status_code=403, detail="Permiso denegado")
    return wrapper

# ---------------- ESTADOS ----------------

TRANSICIONES = {

    "PENDIENTE_DIAGNOSTICO": ["FUNCIONA", "ESTROPEADO"],

    "REGISTRADO": ["FUNCIONA", "ESTROPEADO"],

    "FUNCIONA": [
        "VENTA_SEGUNDA_MANO",
        "VENTA_REACONDICIONADO",
        "VENTA_NUEVO"
    ],

    "ESTROPEADO": [
        "REPARADO",
        "PARA_DESPIECE"
    ],

    "REPARADO": [
        "VENTA_SEGUNDA_MANO",
        "VENTA_REACONDICIONADO",
        "VENTA_NUEVO"
    ],

    "VENTA_SEGUNDA_MANO": ["VENDIDO"],
    "VENTA_REACONDICIONADO": ["VENDIDO"],
    "VENTA_NUEVO": ["VENDIDO"]
}

# ---------------- CREAR ITEM ----------------

class ItemCreate(BaseModel):
    familia_id: int
    sku_id: int
    numero_serie: str
    proveedor_id: int
    fecha_compra: str
    origen: str
    motivo_retirada: str | None = None
    diagnostico_inicial: str | None = None

@app.post("/crear_item")
def crear_item(
    data: ItemCreate,
    db: Session = Depends(get_db),
    permiso: str = Depends(verificar_roles_permitidos("OPERARIO", "ADMIN"))
):

    if data.origen == "RETIRADO_VIVIENDA" and not data.diagnostico_inicial:
        raise HTTPException(status_code=400, detail="Diagnóstico obligatorio")

    estado_inicial = "PENDIENTE_DIAGNOSTICO" if data.origen == "RETIRADO_VIVIENDA" else "REGISTRADO"

    nuevo_id = f"{datetime.datetime.now().year}-{str(uuid.uuid4())[:6]}"

    item = Item(
        id=nuevo_id,
        familia_id=data.familia_id,
        sku_id=data.sku_id,
        numero_serie=data.numero_serie,
        proveedor_id=data.proveedor_id,
        fecha_compra=datetime.datetime.strptime(data.fecha_compra, "%Y-%m-%d"),
        estado_actual=estado_inicial,
        origen=data.origen,
        motivo_retirada=data.motivo_retirada,
        diagnostico_inicial=data.diagnostico_inicial,
    )

    db.add(item)
    db.commit()

    return {"id": nuevo_id}

# ---------------- CAMBIAR ESTADO ----------------

class EstadoUpdate(BaseModel):
    item_id: str
    nuevo_estado: str

@app.post("/cambiar_estado")
def cambiar_estado(
    data: EstadoUpdate,
    db: Session = Depends(get_db),
    permiso: str = Depends(verificar_roles_permitidos("OPERARIO", "ADMIN"))
):

    item = db.query(Item).filter(Item.id == data.item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")

    if data.nuevo_estado not in TRANSICIONES.get(item.estado_actual, []):
        raise HTTPException(status_code=400, detail="Transición no permitida")

    estado_anterior = item.estado_actual
    item.estado_actual = data.nuevo_estado

    if data.nuevo_estado == "VENDIDO":
        item.en_stock = False

    evento = Evento(
        item_id=item.id,
        estado_anterior=estado_anterior,
        estado_nuevo=data.nuevo_estado,
        usuario="sistema"
    )

    db.add(evento)
    db.commit()

    return {"mensaje": "Estado actualizado"}

# ---------------- REGISTRAR VENTA ----------------

class RegistrarVenta(BaseModel):
    item_id: str
    tipo_venta_id: int
    cliente: str
    precio: float | None = None
    garantia_meses: int | None = None
    numero_factura: str | None = None

@app.post("/registrar_venta")
def registrar_venta(
    data: RegistrarVenta,
    db: Session = Depends(get_db),
    permiso: str = Depends(verificar_roles_permitidos("OPERARIO", "ADMIN"))
):

    item = db.query(Item).filter(Item.id == data.item_id).first()

    if not item or not item.en_stock:
        raise HTTPException(status_code=400, detail="Item no disponible")

    venta = Venta(
        item_id=data.item_id,
        tipo_venta_id=data.tipo_venta_id,
        cliente=data.cliente,
        precio=data.precio,
        garantia_meses=data.garantia_meses,
        numero_factura=data.numero_factura
    )

    item.en_stock = False
    item.estado_actual = "VENDIDO"

    db.add(venta)
    db.commit()

    return {"mensaje": "Venta registrada"}

# ---------------- STOCK ----------------

@app.get("/stock")
def ver_stock(
    db: Session = Depends(get_db),
    permiso: str = Depends(verificar_roles_permitidos("OPERARIO", "ADMIN"))
):
    items = db.query(Item).filter(Item.en_stock == True).all()
    return [{"id": i.id, "estado": i.estado_actual} for i in items]

# ---------------- ROOT ----------------

@app.get("/")
def root():
    return {"mensaje": "ERP Almacen funcionando correctamente"}
@app.get("/panel", response_class=HTMLResponse)
def panel(request: Request, db: Session = Depends(get_db)):
    familias = db.query(Familia).all()
    return templates.TemplateResponse(
        "panel.html",
        {"request": request, "familias": familias}
    )
@app.get("/nuevo", response_class=HTMLResponse)
def nuevo_form(request: Request, db: Session = Depends(get_db)):
    familias = db.query(Familia).all()
    return templates.TemplateResponse(
        "nuevo.html",
        {"request": request, "familias": familias}
    )
from fastapi import Form
from fastapi.responses import RedirectResponse


@app.get("/stock_view", response_class=HTMLResponse)
def stock_view(request: Request, db: Session = Depends(get_db)):
    items_db = db.query(Item).filter(Item.en_stock == True).all()

    items = []
    for i in items_db:
        items.append({
            "id": i.id,
            "estado": i.estado_actual,
            "serie": i.numero_serie,
            "origen": i.origen,
            "familia": i.familia.nombre if i.familia else "Sin familia"
        })

    return templates.TemplateResponse(
        "stock.html",
        {"request": request, "items": items}
    )
import qrcode
import os

@app.post("/crear_item_web")
def crear_item_web(
    request: Request,
    familia_id: int = Form(...),
    numero_serie: str = Form(...),
    marca: str = Form(None),
    modelo: str = Form(None),
    origen: str = Form(...),
    diagnostico_inicial: str = Form(None),
    db: Session = Depends(get_db)
):

    # primero crear ID
    prefijos = {
    1: "LAV",
    2: "FRI",
    3: "SEC",
    4: "LAVV",
    5: "HOR",
    6: "MIC",
    7: "AIRE",
    8: "TER",
    9: "VIT",
    10: "CAM"
}
    prefijo = prefijos.get(familia_id, "ART")

    nuevo_id = f"{prefijo}-{str(uuid.uuid4())[:4]}"

    # luego crear item
    item = Item(
        id=nuevo_id,
        familia_id=familia_id,
        numero_serie=numero_serie,
        marca=marca,
        modelo=modelo,
        estado_actual="REGISTRADO",
        origen=origen,
        diagnostico_inicial=diagnostico_inicial
    )

    db.add(item)
    db.commit()

    # generar QR
    url = f"{request.base_url}item/{nuevo_id}"

    qr = qrcode.make(url)
    qr.save(f"app/static/{nuevo_id}.png")

    return RedirectResponse(f"/item/{nuevo_id}", status_code=303)
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/item/{item_id}", response_class=HTMLResponse)
def ver_item(item_id: str, request: Request, db: Session = Depends(get_db)):

    item = db.query(Item).filter(Item.id == item_id).first()

    hijos = db.query(Item).filter(Item.parent_id == item_id).all()

    piezas_disponibles = []

    if item and item.familia:
        piezas_disponibles = PIEZAS_POR_FAMILIA.get(item.familia.nombre, [])

    return templates.TemplateResponse(
        "item.html",
        {
            "request": request,
            "item": item,
            "hijos": hijos,
            "piezas_disponibles": piezas_disponibles
        }
    )

@app.post("/cambiar_estado_web/{item_id}")
def cambiar_estado_web(
    item_id: str,
    nuevo_estado: str = Form(...),
    db: Session = Depends(get_db)
):
    item = db.query(Item).filter(Item.id == item_id).first()

    if not item:
        return HTMLResponse("<h2>Item no encontrado</h2>")

    item.estado_actual = nuevo_estado
    db.commit()

    return RedirectResponse(f"/item/{item_id}", status_code=303)
@app.get("/scan", response_class=HTMLResponse)
def scan_page(request: Request):
    return templates.TemplateResponse("scan.html", {"request": request})
@app.get("/vender/{item_id}", response_class=HTMLResponse)
def vender_form(item_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()

    if not item:
        return HTMLResponse("<h2>Item no encontrado</h2>")

    return templates.TemplateResponse(
        "vender.html",
        {"request": request, "item": item}
    )
@app.post("/vender/{item_id}")
def procesar_venta(
    item_id: str,
    numero_factura: str = Form(None),
    tipo_venta: str = Form(...),
    precio: float = Form(...),
    db: Session = Depends(get_db)
):
    item = db.query(Item).filter(Item.id == item_id).first()

    if not item:
        return HTMLResponse("<h2>Item no encontrado</h2>")

    item.estado_actual = "VENDIDO"
    item.en_stock = False
    item.numero_factura = numero_factura
    item.tipo_venta = tipo_venta
    item.precio_venta = precio
    item.fecha_venta = datetime.datetime.now()

    db.commit()

    return RedirectResponse("/stock_view", status_code=303)
@app.get("/crear_pieza/{item_id}", response_class=HTMLResponse)
def crear_pieza_form(item_id: str, request: Request):
    return templates.TemplateResponse(
        "crear_pieza.html",
        {"request": request, "parent_id": item_id}
    )

import qrcode
import os

@app.post("/crear_pieza/{item_id}")
def crear_pieza(
    item_id: str,
    nombre_pieza: str = Form(...),
    medidas: str = Form(None),
    db: Session = Depends(get_db)
):

    padre = db.query(Item).filter(Item.id == item_id).first()

    nuevo_id = f"PZ-{str(uuid.uuid4())[:6]}"

    pieza = Item(
        id=nuevo_id,
        nombre_pieza=nombre_pieza,
        medidas=medidas,
        familia_id=padre.familia_id,
        estado_actual="REGISTRADO",
        origen="DESPIECE",
        parent_id=item_id,
        en_stock=True
    )

    db.add(pieza)
    db.commit()
    url = f"{request.base_url}item/{nuevo_id}"
    qr = qrcode.make(url)
    qr.save(f"app/static/{nuevo_id}.png")
    url = f"https://erp-almacen.onrender.com/item/{nuevo_id}"

    os.makedirs("app/static", exist_ok=True)

    qr = qrcode.make(url)
    qr.save(f"app/static/{nuevo_id}.png")

    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.get("/backup_json")
def backup_json(db: Session = Depends(get_db)):

    items = db.query(Item).all()

    data = []

    for i in items:
        data.append({
            "id": i.id,
            "familia": i.familia.nombre if i.familia else None,
            "serie": i.numero_serie,
            "estado": i.estado_actual,
            "origen": i.origen,
            "precio_compra": i.precio_compra,
            "albaran": i.numero_albaran
        })

    return data
@app.get("/buscar", response_class=HTMLResponse)
def buscar(q: str, request: Request, db: Session = Depends(get_db)):

    item = db.query(Item).filter(
        (Item.id == q) |
        (Item.numero_serie == q)
    ).first()

    if item:
        return RedirectResponse(f"/item/{item.id}", status_code=303)

    return templates.TemplateResponse(
        "panel.html",
        {"request": request, "error": "Artículo no encontrado"}
    )
@app.get("/export_csv")
def export_csv(db: Session = Depends(get_db)):

    items = db.query(Item).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Tipo",
        "Familia",
        "Marca",
        "Modelo",
        "Numero serie",
        "Nombre pieza",
        "Medidas",
        "Estado",
        "Origen",
        "Precio compra",
        "Precio venta",
        "Numero albaran",
        "Diagnostico inicial",
        "Decision tecnica",
        "Aparato origen",
        "En stock",
        "Fecha creacion"
    ])

    for i in items:

        tipo = "PIEZA" if i.parent_id else "ELECTRODOMESTICO"

        writer.writerow([
            i.id,
            tipo,
            i.familia.nombre if i.familia else "",
            i.marca,
            i.modelo,
            i.numero_serie,
            i.nombre_pieza,
            i.medidas,
            i.estado_actual,
            i.origen,
            i.precio_compra,
            i.precio_venta,
            i.numero_albaran,
            i.diagnostico_inicial,
            i.decision_tecnica,
            i.parent_id,
            i.en_stock,
            i.fecha_creacion
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=almacen_completo.csv"
        }
    )

@app.get("/buscar_piezas", response_class=HTMLResponse)
def buscar_piezas(
    request: Request,
    familia: str = "",
    nombre_pieza: str = "",
    modelo: str = "",
    db: Session = Depends(get_db)
):

    query = db.query(Item).filter(Item.parent_id != None)

    if familia:
        query = query.join(Familia).filter(Familia.nombre == familia)

    if nombre_pieza:
        query = query.filter(Item.nombre_pieza == nombre_pieza)

    if modelo:
        query = query.filter(Item.modelo.ilike(f"%{modelo}%"))

    piezas = query.all()

    return templates.TemplateResponse(
        "buscar_piezas.html",
        {
            "request": request,
            "piezas": piezas
        }
    )

@app.get("/crear_pieza_directa/{item_id}/{nombre}")
def crear_pieza_directa(
    item_id: str,
    nombre: str,
    db: Session = Depends(get_db)
):

    padre = db.query(Item).filter(Item.id == item_id).first()
    if padre.decision_tecnica == "REPARAR":
        return HTMLResponse("<h2>Este aparato está marcado para reparación y no puede despiezarse</h2>")

    if not padre:
        return HTMLResponse("<h2>Item no encontrado</h2>")
    if padre.decision_tecnica == "REPARAR":
        return HTMLResponse("<h2>Este aparato está marcado para reparación y no puede despiezarse</h2>")

    # 🚫 evitar despiezar piezas
    if padre.parent_id is not None:
        return HTMLResponse("<h2>Una pieza no puede tener subpiezas</h2>")

    nuevo_id = f"PZ-{str(uuid.uuid4())[:6]}"

    pieza = Item(
        id=nuevo_id,
        nombre_pieza=nombre,
        familia_id=padre.familia_id,
        estado_actual="REGISTRADO",
        origen="DESPIECE",
        parent_id=item_id,
        en_stock=True
    )

    db.add(pieza)
    db.commit()

    return RedirectResponse(f"/item/{item_id}", status_code=303)
@app.get("/diagnostico/{item_id}", response_class=HTMLResponse)
def diagnostico_form(item_id: str, request: Request, db: Session = Depends(get_db)):

    item = db.query(Item).filter(Item.id == item_id).first()

    return templates.TemplateResponse(
        "diagnostico.html",
        {"request": request, "item": item}
    )
@app.post("/diagnostico/{item_id}")
def guardar_diagnostico(
    item_id: str,
    coste: float = Form(None),
    decision: str = Form(None),
    db: Session = Depends(get_db)
):

    item = db.query(Item).filter(Item.id == item_id).first()

    item.coste_reparacion_estimado = coste
    item.decision_tecnica = decision

    db.commit()

    return RedirectResponse(f"/item/{item_id}", status_code=303)

@app.get("/nueva_pieza", response_class=HTMLResponse)
def nueva_pieza_form(request: Request, db: Session = Depends(get_db)):

    familias = db.query(Familia).all()

    return templates.TemplateResponse(
        "nueva_pieza.html",
        {"request": request, "familias": familias}
    )
@app.post("/crear_pieza_directa")
def crear_pieza_directa(
    familia_id: int = Form(...),
    nombre_pieza: str = Form(...),
    medidas: str = Form(None),
    modelo: str = Form(None),
    db: Session = Depends(get_db)
):

    nuevo_id = f"PZ-{str(uuid.uuid4())[:6]}"

    pieza = Item(
        id=nuevo_id,
        nombre_pieza=nombre_pieza,
        medidas=medidas,
        modelo=modelo,
        familia_id=familia_id,
        estado_actual="REGISTRADO",
        origen="STOCK_ANTIGUO",
        en_stock=True
    )

    db.add(pieza)
    db.commit()

    return RedirectResponse(f"/item/{nuevo_id}", status_code=303)
@app.post("/precio/{item_id}")
def actualizar_precio(
    item_id: str,
    precio: float = Form(...),
    db: Session = Depends(get_db)
):

    item = db.query(Item).filter(Item.id == item_id).first()

    item.precio_venta = precio

    db.commit()

    return RedirectResponse(f"/item/{item_id}", status_code=303)
@app.get("/print_qr/{item_id}", response_class=HTMLResponse)
def print_qr(item_id: str, request: Request, db: Session = Depends(get_db)):

    item = db.query(Item).filter(Item.id == item_id).first()

    return templates.TemplateResponse(
        "print_qr.html",
        {"request": request, "item": item}
    )
@app.get("/print_pieza/{item_id}", response_class=HTMLResponse)
def print_pieza(item_id: str, request: Request, db: Session = Depends(get_db)):

    pieza = db.query(Item).filter(Item.id == item_id).first()

    return templates.TemplateResponse(
        "print_pieza.html",
        {"request": request, "pieza": pieza}
    )
import qrcode
import io
from fastapi.responses import StreamingResponse


@app.get("/qr/{item_id}")
def generar_qr(item_id: str, request: Request):

    url = str(request.base_url) + "item/" + item_id

    img = qrcode.make(url)

    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")

@app.get("/buscar_piezas_avanzado", response_class=HTMLResponse)
def buscar_piezas_avanzado(
    request: Request,
    familia_id: int = None,
    modelo: str = "",
    nombre_pieza: str = "",
    db: Session = Depends(get_db)
):

    query = db.query(Item).filter(Item.parent_id != None)

    if familia_id:
        query = query.filter(Item.familia_id == familia_id)

    if modelo:
        query = query.filter(Item.modelo.ilike(f"%{modelo}%"))

    if nombre_pieza:
        query = query.filter(Item.nombre_pieza.ilike(f"%{nombre_pieza}%"))

    piezas = query.all()

    familias = db.query(Familia).all()

    return templates.TemplateResponse(
        "buscar_piezas.html",
        {
            "request": request,
            "piezas": piezas,
            "familias": familias
        }
    )

@app.get("/buscar_aparatos", response_class=HTMLResponse)
def buscar_aparatos(
    request: Request,
    familia_id: int = None,
    estado: str = "",
    db: Session = Depends(get_db)
):

    query = db.query(Item).filter(Item.parent_id == None)

    if familia_id:
        query = query.filter(Item.familia_id == familia_id)

    if estado:
        query = query.filter(Item.estado_actual == estado)

    aparatos = query.all()

    familias = db.query(Familia).all()

    return templates.TemplateResponse(
        "buscar_aparatos.html",
        {
            "request": request,
            "aparatos": aparatos,
            "familias": familias
        }
    )

@app.get("/buscar_piezas", response_class=HTMLResponse)
def buscar_piezas(
    request: Request,
    marca: str = "",
    modelo: str = "",
    nombre_pieza: str = "",
    db: Session = Depends(get_db)
):

    query = db.query(Item).filter(Item.parent_id != None)

    if marca:
        query = query.filter(Item.marca.ilike(f"%{marca}%"))

    if modelo:
        query = query.filter(Item.modelo.ilike(f"%{modelo}%"))

    if nombre_pieza:
        query = query.filter(Item.nombre_pieza.ilike(f"%{nombre_pieza}%"))

    piezas = query.all()

    return templates.TemplateResponse(
        "buscar_piezas.html",
        {
            "request": request,
            "piezas": piezas
        }
    )

@app.get("/piezas_por_familia/{familia}")
def piezas_por_familia(familia: str):

    piezas = PIEZAS_POR_FAMILIA.get(familia, [])

    return [p["nombre"] for p in piezas]

@app.get("/etiqueta_pieza/{item_id}", response_class=HTMLResponse)
def etiqueta_pieza(item_id: str, request: Request, db: Session = Depends(get_db)):

    pieza = db.query(Item).filter(Item.id == item_id).first()

    return templates.TemplateResponse(
        "etiqueta_pieza.html",
        {
            "request": request,
            "pieza": pieza
        }
    )

@app.get("/etiqueta_aparato/{item_id}", response_class=HTMLResponse)
def etiqueta_aparato(item_id: str, request: Request, db: Session = Depends(get_db)):

    item = db.query(Item).filter(Item.id == item_id).first()

    return templates.TemplateResponse(
        "etiqueta_aparato.html",
        {
            "request": request,
            "item": item
        }
    )

@app.get("/etiqueta_pieza/{item_id}", response_class=HTMLResponse)
def etiqueta_pieza(item_id: str, request: Request, db: Session = Depends(get_db)):

    pieza = db.query(Item).filter(Item.id == item_id).first()

    return templates.TemplateResponse(
        "etiqueta_pieza.html",
        {
            "request": request,
            "pieza": pieza
        }
    )

from fastapi import UploadFile, File

import requests

@app.post("/subir_imagen/{item_id}")
async def subir_imagen(
    item_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    contenido = await file.read()

    filename = f"{item_id}.jpg"

    url = f"{SUPABASE_URL}/storage/v1/object/imagenes/{filename}"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": file.content_type
    }

    # IMPORTANTE: PUT
    response = requests.put(url, headers=headers, data=contenido)

    if response.status_code not in [200, 201]:
        return {"error": response.text}

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/imagenes/{filename}"

    imagen = Imagen(item_id=item_id, url=public_url)

    db.add(imagen)
    db.commit()

    return {"ok": True}

@app.get("/imagenes/{item_id}")
def ver_imagenes(item_id: str, db: Session = Depends(get_db)):

    fotos = db.query(Imagen).filter(Imagen.item_id == item_id).order_by(Imagen.orden).all()

    return fotos

@app.post("/borrar_imagen/{imagen_id}")
def borrar_imagen(imagen_id: int, db: Session = Depends(get_db)):

    imagen = db.query(Imagen).filter(Imagen.id == imagen_id).first()

    filename = imagen.url.split("/")[-1]

    supabase.storage.from_("imagenes").remove([filename])

    db.delete(imagen)
    db.commit()

    return {"ok": True}
