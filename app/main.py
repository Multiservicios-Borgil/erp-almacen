from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi import Form
from fastapi.responses import RedirectResponse

templates = Jinja2Templates(directory="app/templates")
from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import datetime, uuid

from .database import SessionLocal, engine
from .models import Base, Item, Familia

Base.metadata.create_all(bind=engine)
from .models import Familia

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

app = FastAPI()

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
    "FUNCIONA": ["PREPARADO_VENTA"],
    "ESTROPEADO": ["REPARADO", "PARA_DESPIECE"],
    "REPARADO": ["PREPARADO_VENTA"],
    "PREPARADO_VENTA": ["VENDIDO"],
    "PARA_DESPIECE": ["DESPIEZADO"],
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

@app.post("/crear_item_web")
def crear_item_web(
    familia_id: int = Form(...),
    numero_serie: str = Form(...),
    origen: str = Form(...),
    db: Session = Depends(get_db)
):

    nuevo_id = f"{datetime.datetime.now().year}-{str(uuid.uuid4())[:6]}"

    item = Item(
        id=nuevo_id,
        familia_id=familia_id,
        numero_serie=numero_serie,
        estado_actual="REGISTRADO",
        origen=origen
    )

    db.add(item)
    db.commit()

    return RedirectResponse("/panel", status_code=303)
@app.get("/stock_view", response_class=HTMLResponse)
def stock_view(request: Request, db: Session = Depends(get_db)):
    items = db.query(Item).filter(Item.en_stock == True).all()
    return templates.TemplateResponse(
        "stock.html",
        {"request": request, "items": items}
    )
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
    familia_id: int = Form(...),
    numero_serie: str = Form(...),
    origen: str = Form(...),
    db: Session = Depends(get_db)
):

    nuevo_id = f"{datetime.datetime.now().year}-{str(uuid.uuid4())[:6]}"

    item = Item(
        id=nuevo_id,
        familia_id=familia_id,
        numero_serie=numero_serie,
        estado_actual="REGISTRADO",
        origen=origen
    )

    db.add(item)
    db.commit()

    # Crear QR
    url = f"https://tuservicio.onrender.com/item/{nuevo_id}"

    os.makedirs("app/static", exist_ok=True)

    qr = qrcode.make(url)
    qr.save(f"app/static/{nuevo_id}.png")

    return RedirectResponse(f"/item/{nuevo_id}", status_code=303)
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/item/{item_id}", response_class=HTMLResponse)
def ver_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    i = db.query(Item).filter(Item.id == item_id).first()

    if not i:
        hijos = db.query(Item).filter(Item.parent_id == item_id).all()
        return templates.TemplateResponse(
    "item.html",
    {
        "request": request,
        "item": item,
        "hijos": hijos
    }
)

    item = {
        "id": i.id,
        "estado": i.estado_actual,
        "serie": i.numero_serie,
        "origen": i.origen,
        "familia": i.familia.nombre if i.familia else "Sin familia"
    }

    return templates.TemplateResponse(
        "item.html",
        {"request": request, "item": item}
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
@app.post("/crear_pieza/{item_id}")
def crear_pieza(
    item_id: str,
    nombre: str = Form(...),
    db: Session = Depends(get_db)
):

    padre = db.query(Item).filter(Item.id == item_id).first()

    nuevo_id = f"PZ-{str(uuid.uuid4())[:6]}"

    pieza = Item(
        id=nuevo_id,
        numero_serie=None,
        familia_id=padre.familia_id,
        estado_actual="REGISTRADO",
        origen="DESPIECE",
        parent_id=item_id,
        en_stock=True
    )

    db.add(pieza)
    db.commit()

    return RedirectResponse(f"/item/{item_id}", status_code=303)
@app.get("/crear_pieza/{item_id}", response_class=HTMLResponse)
def crear_pieza_form(item_id: str, request: Request):
    return templates.TemplateResponse(
        "crear_pieza.html",
        {"request": request, "parent_id": item_id}
    )
@app.post("/crear_pieza/{item_id}")
def crear_pieza(
    item_id: str,
    nombre: str = Form(...),
    db: Session = Depends(get_db)
):

    nuevo_id = f"PZ-{str(uuid.uuid4())[:6]}"

    pieza = Item(
        id=nuevo_id,
        estado_actual="REGISTRADO",
        origen="DESPIECE",
        parent_id=item_id,
        en_stock=True
    )

    db.add(pieza)
    db.commit()

    return RedirectResponse(f"/item/{item_id}", status_code=303)
git commit -m "sistema basico de despiece"
@app.get("/crear_pieza/{item_id}", response_class=HTMLResponse)
def crear_pieza_form(item_id: str, request: Request):
    return templates.TemplateResponse(
        "crear_pieza.html",
        {"request": request, "parent_id": item_id}
    )
