from app.database import SessionLocal
from app.models import Item, Imagen, HistorialDiagnostico
from datetime import datetime, date, timedelta

db = SessionLocal()
hoy = date.today()
manana = hoy + timedelta(days=1)

try:
    # 1. Borrar por fecha de creacion (Cualquier cosa de hoy)
    # 2. Borrar por origen AMAZON y camion 2 (por si acaso la fecha UTC varia)
    items_a_borrar = db.query(Item).filter(
        (Item.fecha_creacion >= hoy) | 
        ((Item.origen == "AMAZON") & (Item.camion == 2))
    ).all()
    
    num = len(items_a_borrar)
    print(f"Detectados {num} artículos para borrar...")
    
    for item in items_a_borrar:
        # Borrar registros asociados primero por las claves foraneas
        db.query(Imagen).filter(Imagen.item_id == item.id).delete()
        db.query(HistorialDiagnostico).filter(HistorialDiagnostico.item_id == item.id).delete()
        # Borrar el item
        db.delete(item)
    
    db.commit()
    print(f"ÉXITO: Se han borrado {num} artículos. La base de datos está limpia para el Camión 2.")
except Exception as e:
    db.rollback()
    print(f"Error durante la limpieza: {e}")
finally:
    db.close()
