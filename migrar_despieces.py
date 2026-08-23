import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from app.models import Base, Item, Familia

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, connect_args={"sslmode": "require"})
Session = sessionmaker(bind=engine)
session = Session()

try:
    lavadora = session.query(Familia).filter(Familia.nombre == "Lavadora").first()
    lavavajillas = session.query(Familia).filter(Familia.nombre == "Lavavajillas").first()
    
    if not lavadora or not lavavajillas:
        print("Error: No se encontró la familia Lavadora o Lavavajillas.")
        exit(1)
        
    print(f"Lavadora ID: {lavadora.id}, Lavavajillas ID: {lavavajillas.id}")
    
    lavadora_rename = {
        "Placa electronica": "Placa electrónica",
        "Bomba desague": "Bomba desagüe",
        "Cajon detergente": "Cajón detergente",
        "Electrovalvula": "Electroválvula"
    }
    
    lavavajillas_rename = {
        "Placa electronica": "Placa electrónica",
        "Bomba desague": "Bomba desagüe",
        "Cesto superior": "Cesta superior",
        "Cesta Superior": "Cesta superior",
        "Cesto inferior": "Cesta inferior",
        "Cesta Inferior": "Cesta inferior",
        "Tubo aquastop": "Aquastop"
    }
    
    updated_count = 0
    for old_name, new_name in lavadora_rename.items():
        items = session.query(Item).filter(
            Item.familia_id == lavadora.id,
            Item.nombre_pieza == old_name
        ).all()
        if items:
            print(f"Renombrando {len(items)} piezas de Lavadora: '{old_name}' -> '{new_name}'")
            for item in items:
                item.nombre_pieza = new_name
                updated_count += 1
                
    for old_name, new_name in lavavajillas_rename.items():
        items = session.query(Item).filter(
            Item.familia_id == lavavajillas.id,
            Item.nombre_pieza == old_name
        ).all()
        if items:
            print(f"Renombrando {len(items)} piezas de Lavavajillas: '{old_name}' -> '{new_name}'")
            for item in items:
                item.nombre_pieza = new_name
                updated_count += 1
                
    session.commit()
    print(f"Migración completada con éxito. Registros actualizados: {updated_count}")
except Exception as e:
    session.rollback()
    print(f"Error durante la migración: {e}")
finally:
    session.close()
