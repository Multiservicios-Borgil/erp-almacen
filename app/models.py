import datetime
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, Text, Date, DateTime
from sqlalchemy.orm import relationship
from .database import Base

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


class Familia(Base):
    __tablename__ = "familias"
    id = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True)


class Item(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True)
    parent_id = Column(String, ForeignKey("items.id"), nullable=True)
    familia_id = Column(Integer, ForeignKey("familias.id"))
    sku_id = Column(Integer, ForeignKey("productos.id"))
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"))
    
    marca = Column(String, nullable=True)
    modelo = Column(String, nullable=True)
    nombre_pieza = Column(String, nullable=True)
    medidas = Column(String, nullable=True)
    numero_serie = Column(String)
    numero_albaran = Column(String, nullable=True)
    
    precio_compra = Column(Float, nullable=True)
    precio_venta = Column(Float, nullable=True)
    
    estado_actual = Column(String, default="REGISTRADO")
    en_stock = Column(Boolean, default=True)
    camion = Column(Integer, default=1)
    
    origen = Column(String)
    diagnostico_inicial = Column(Text, nullable=True)
    diagnostico_tecnico = Column(Text, nullable=True)
    coste_reparacion_estimado = Column(Float, nullable=True)
    decision_tecnica = Column(String, nullable=True)
    
    fecha_compra = Column(Date, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.datetime.utcnow)
    fecha_venta = Column(DateTime, nullable=True)
    
    en_wallapop = Column(Boolean, default=False)
    numero_factura = Column(String, nullable=True)
    tipo_venta = Column(String, nullable=True)

    parent = relationship("Item", remote_side=[id], back_populates="hijos")
    hijos = relationship("Item", back_populates="parent", cascade="all, delete")
    familia = relationship("Familia")


class Imagen(Base):
    __tablename__ = "imagenes"
    id = Column(Integer, primary_key=True)
    item_id = Column(String, ForeignKey("items.id"))
    url = Column(String)
    orden = Column(Integer, default=0)


class HistorialDiagnostico(Base):
    __tablename__ = "historial_diagnostico"
    id = Column(Integer, primary_key=True)
    item_id = Column(String, ForeignKey("items.id"))
    fecha = Column(DateTime, default=datetime.datetime.utcnow)
    diagnostico = Column(Text)
