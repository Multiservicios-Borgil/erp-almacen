from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, DateTime, Date, Text
from sqlalchemy.orm import relationship, declarative_base
import datetime

Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    rol = Column(String, nullable=False)  # OPERARIO o ADMIN
    activo = Column(Boolean, default=True)

class Familia(Base):
    __tablename__ = "familias"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True, nullable=False)
    descripcion = Column(String)
    activa = Column(Boolean, default=True)

class Proveedor(Base):
    __tablename__ = "proveedores"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    telefono = Column(String)
    email = Column(String)
    activo = Column(Boolean, default=True)

class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True)
    sku_codigo = Column(String, unique=True, nullable=False)
    marca = Column(String)
    modelo = Column(String)
    activo = Column(Boolean, default=True)

class TipoVenta(Base):
    __tablename__ = "tipos_venta"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True)

class Item(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True)
    parent_id = Column(String, ForeignKey("items.id"), nullable=True)
    parent = relationship(
    "Item",
    remote_side=[id],
    backref="hijos"
)
    familia_id = Column(Integer, ForeignKey("familias.id"))
    sku_id = Column(Integer, ForeignKey("productos.id"))
    numero_serie = Column(String)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"))

    estado_actual = Column(String, default="REGISTRADO")
    en_stock = Column(Boolean, default=True)

    origen = Column(String)
    motivo_retirada = Column(Text)
    diagnostico_inicial = Column(Text)
    diagnostico_tecnico = Column(Text)

    fecha_compra = Column(Date)
    fecha_creacion = Column(DateTime, default=datetime.datetime.utcnow)

    familia = relationship("Familia")
    hijos = relationship("Item", remote_side=[id])
    from sqlalchemy import Float, DateTime
import datetime

precio_venta = Column(Float, nullable=True)
numero_factura = Column(String, nullable=True)
tipo_venta = Column(String, nullable=True)
fecha_venta = Column(DateTime, nullable=True)

class Evento(Base):
    __tablename__ = "eventos"

    id_evento = Column(Integer, primary_key=True)
    item_id = Column(String, ForeignKey("items.id"))
    estado_anterior = Column(String)
    estado_nuevo = Column(String)
    usuario = Column(String)
    fecha = Column(DateTime, default=datetime.datetime.utcnow)
    comentario = Column(Text)

class Venta(Base):
    __tablename__ = "ventas"

    id_venta = Column(Integer, primary_key=True)
    item_id = Column(String, ForeignKey("items.id"))
    tipo_venta_id = Column(Integer, ForeignKey("tipos_venta.id"))
    cliente = Column(String)
    precio = Column(String)
    garantia_meses = Column(Integer)
    numero_factura = Column(String, nullable=True)
    fecha = Column(DateTime, default=datetime.datetime.utcnow)

    tipo_venta = relationship("TipoVenta")
