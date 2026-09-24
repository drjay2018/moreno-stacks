import datetime
from sqlalchemy import text
from app.extensions import db

class LeadsEngine:
    @staticmethod
    def evaluar_y_recategorizar_asesores():
        """
        Evalúa trimestralmente (ventana móvil de los últimos 12 meses) las separaciones 
        para actualizar la categoría del asesor (A, B, o C) y su asignación base de leads.
        """
        hoy = datetime.date.today()
        # Restar 1 año usando timedelta simplificado
        try:
            hace_12_meses = hoy.replace(year=hoy.year - 1)
        except ValueError:
            # Para el 29 de febrero
            hace_12_meses = hoy.replace(year=hoy.year - 1, day=28)
        
        # 1. Obtener a todos los asesores (entidades)
        asesores = db.session.execute(
            text("SELECT id, nivel FROM entidades WHERE activo = 1")
        ).mappings().all()

        resultados = []

        for asesor in asesores:
            asesor_id = asesor["id"]
            nivel_actual = asesor["nivel"]

            # Contar las separaciones (transacciones creadas) en los últimos 12 meses
            separaciones_count = db.session.execute(
                text("""
                    SELECT COUNT(id) FROM transacciones 
                    WHERE (entidad_id = :aid OR captador_id = :aid)
                    AND estado != 'cancelado'
                    AND fecha_evento >= :hace_12_meses
                """),
                {"aid": asesor_id, "hace_12_meses": hace_12_meses}
            ).scalar() or 0

            # Lógica de Categorización (Ventana Móvil)
            nueva_categoria = "Asesor - Categoría C"
            leads_base = 10
            
            if separaciones_count >= 15:
                nueva_categoria = "Asesor - Categoría A"
                leads_base = 50
            elif separaciones_count >= 5:
                nueva_categoria = "Asesor - Categoría B"
                leads_base = 25
                
            # Actualizar el nivel del asesor si cambió
            # Tambien se podria guardar la asignación base de leads en atributos_extra, 
            # pero por ahora actualizamos el nivel.
            if nueva_categoria != nivel_actual:
                db.session.execute(
                    text("""
                        UPDATE entidades 
                        SET nivel = :nueva_categoria 
                        WHERE id = :aid
                    """),
                    {"nueva_categoria": nueva_categoria, "aid": asesor_id}
                )
                
            resultados.append({
                "asesor_id": asesor_id,
                "separaciones_12m": separaciones_count,
                "categoria_asignada": nueva_categoria,
                "leads_mensuales_asignados": leads_base
            })

        db.session.commit()
        return resultados
