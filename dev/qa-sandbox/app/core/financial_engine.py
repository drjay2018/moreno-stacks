"""
financial_engine.py — Motor financiero unificado para DLAB CRM.
Combina la precisión fiscal (Decimal) de dlab-app con los helpers de dlab-data.
"""

import logging
from typing import Any, Dict, List
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

logger = logging.getLogger(__name__)


class FinancialEngine:

    # --------------------------------------------------------------------------
    # 1. ESTRUCTURACIÓN DE LA VENTA
    # --------------------------------------------------------------------------
    @staticmethod
    def calcular_monto_diferido(monto_inicial: float, monto_separacion: float) -> float:
        """Monto a Diferir = monto_inicial - monto_separacion"""
        return max(0.0, round(float(monto_inicial or 0.0) - float(monto_separacion or 0.0), 2))

    @staticmethod
    def calcular_valor_cuota(monto_diferido: float, num_cuotas: int) -> float:
        """Valor de Cuota Mensual = Monto Diferido / num_cuotas"""
        if not num_cuotas or num_cuotas <= 0:
            return 0.0
        return round(float(monto_diferido or 0.0) / int(num_cuotas), 2)

    @staticmethod
    def calcular_monto_a_financiar(monto_total: float, monto_inicial: float) -> float:
        """Monto a Financiar = monto_total - monto_inicial"""
        return max(0.0, round(float(monto_total or 0.0) - float(monto_inicial or 0.0), 2))

    @staticmethod
    def estructurar_venta(monto_total: float, monto_separacion: float, monto_inicial: float, num_cuotas: int) -> dict:
        """Estructura completa de la transacción."""
        monto_diferido = FinancialEngine.calcular_monto_diferido(monto_inicial, monto_separacion)
        valor_cuota = FinancialEngine.calcular_valor_cuota(monto_diferido, num_cuotas)
        monto_financiar = FinancialEngine.calcular_monto_a_financiar(monto_total, monto_inicial)
        porcentaje_inicial = (monto_inicial / monto_total) * 100 if monto_total > 0 else 0

        return {
            "monto_total": round(float(monto_total), 2),
            "monto_separacion": round(float(monto_separacion), 2),
            "monto_inicial": round(float(monto_inicial), 2),
            "porcentaje_inicial": porcentaje_inicial,
            "num_cuotas": int(num_cuotas),
            "monto_diferido": monto_diferido,
            "valor_cuota_mensual": valor_cuota,
            "monto_a_financiar": monto_financiar,
            "monto_restante": monto_financiar,
            "monto_por_cuota": valor_cuota
        }

    # --------------------------------------------------------------------------
    # 2. CONTROL DE COBROS
    # --------------------------------------------------------------------------
    @staticmethod
    def calcular_total_pagado(pagos: List[Any]) -> float:
        """Total Pagado a la Fecha = SUM(Pago.monto)"""
        return round(sum(float(getattr(p, "monto", p.get("monto", 0.0) if isinstance(p, dict) else 0.0) or 0.0) for p in pagos), 2)

    @staticmethod
    def calcular_saldo_cuota(monto_total: float, total_pagado: float) -> float:
        """Saldo Pendiente = monto_total - total_pagado"""
        return max(0.0, round(float(monto_total or 0.0) - float(total_pagado or 0.0), 2))

    @staticmethod
    def calcular_dias_atraso(fecha_vencimiento, fecha_actual=None):
        """Días de Atraso (Aging) = max(0, Fecha Actual - fecha_vencimiento)"""
        if not fecha_vencimiento:
            return 0
        if not fecha_actual:
            fecha_actual = date.today()
        diff = (fecha_actual - fecha_vencimiento).days
        return max(0, diff)

    # --------------------------------------------------------------------------
    # 3. DISTRIBUCIÓN DE COMISIONES
    # --------------------------------------------------------------------------
    @staticmethod
    def calcular_bolsa_comision(monto_venta: Any, pct_comision: Any) -> Decimal:
        """Bolsa Total = monto_venta * (pct_comision / 100) — retorna Decimal."""
        mv = Decimal(str(monto_venta or 0))
        pct = Decimal(str(pct_comision or 0))
        return (mv * (pct / Decimal('100'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    def calcular_distribucion_inmobiliaria(
        bolsa_total: Any,
        vendedor_id: int,
        captador_id: int,
        origen_prospecto: str,
        es_exclusivo: bool,
        is_same_asesor: bool
    ) -> Dict[str, Any]:
        """Distribución de comisiones según reglas Inmobiliaria (matriz por niveles)."""
        bt = Decimal(str(bolsa_total or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        origen = str(origen_prospecto or '').strip().lower()

        p_a = Decimal('0.00')
        if vendedor_id == 1:
            p_a = Decimal('0.40')
        elif vendedor_id == 2:
            p_a = Decimal('0.50') if origen == 'propio' else Decimal('0.40')
        elif vendedor_id == 3:
            p_a = Decimal('0.60') if origen == 'propio' else Decimal('0.40')
        elif vendedor_id == 4:
            p_a = Decimal('0.60')
        elif vendedor_id == 5:
            p_a = Decimal('0.80')
        elif vendedor_id == 6:
            p_a = Decimal('0.20')

        p_n = Decimal('0.00')
        if not is_same_asesor and vendedor_id == 5:
            p_n = Decimal('0.00')
        else:
            cat_captador = vendedor_id if is_same_asesor else captador_id
            if cat_captador == 1:
                p_n = Decimal('0.10')
            elif cat_captador == 2:
                p_n = Decimal('0.15')
            elif cat_captador == 3:
                p_n = Decimal('0.20')

        if not is_same_asesor and (p_a + p_n) > Decimal('0.70'):
            exceso = (p_a + p_n) - Decimal('0.70')
            p_n -= exceso
            if p_n < Decimal('0.00'):
                p_a += p_n
                p_n = Decimal('0.00')

        p_proy = Decimal('0.05')
        p_admin = Decimal('1.00') - (p_a + p_n + p_proy)

        c_a = (bt * p_a).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        c_n = (bt * p_n).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        c_proy = (bt * p_proy).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        c_admin = bt - (c_a + c_n + c_proy)

        return {
            "bolsa_total": float(bt),
            "pct_a": float(p_a), "comision_a": float(c_a),
            "pct_n": float(p_n), "comision_n": float(c_n),
            "pct_ase1": 0.0, "comision_ase1": 0.0,
            "pct_ase2": 0.0, "comision_ase2": 0.0,
            "pct_proyecto": float(p_proy), "comision_proyecto": float(c_proy),
            "pct_admin": float(p_admin), "comision_admin": float(c_admin),
            "pct_extra": 0.0, "comision_extra": 0.0,
            "pct_pub_gfm": 0.0, "comision_pub_gfm": 0.0,
            "cuadre_perfecto": True
        }

    @staticmethod
    def distribuir_comision(
        bolsa_total: float,
        pct_vendedor: float = 50.0,
        pct_captador: float = 30.0,
        pct_empresa: float = 20.0
    ) -> Dict[str, Any]:
        """Distribución simple 3 vías con validación de cuadre 100%."""
        suma_pct = round(float(pct_vendedor) + float(pct_captador) + float(pct_empresa), 4)
        if abs(suma_pct - 100.0) > 0.0001:
            raise ValueError(f"Descuadre financiero: {suma_pct}% != 100.0%")

        comision_vendedor = round(bolsa_total * (pct_vendedor / 100.0), 2)
        comision_captador = round(bolsa_total * (pct_captador / 100.0), 2)
        comision_empresa = round(bolsa_total - comision_vendedor - comision_captador, 2)

        return {
            "bolsa_total": bolsa_total,
            "pct_vendedor": pct_vendedor, "comision_vendedor": comision_vendedor,
            "pct_captador": pct_captador, "comision_captador": comision_captador,
            "pct_empresa": pct_empresa, "comision_empresa": comision_empresa,
            "cuadre_perfecto": True
        }

    # --------------------------------------------------------------------------
    # 4. BALANCES
    # --------------------------------------------------------------------------
    @staticmethod
    def calcular_balance_asesor(comision_ganada: Any, comision_pagada: Any) -> Decimal:
        """Balance Pendiente = comision_ganada - comision_pagada."""
        cg = Decimal(str(comision_ganada or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        cp = Decimal(str(comision_pagada or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return max(Decimal('0.00'), cg - cp)

    # --------------------------------------------------------------------------
    # 5. RETENCIONES FISCALES (ISR / ITBIS)
    # --------------------------------------------------------------------------
    @staticmethod
    def calcular_retenciones_fiscales(
        comision_bruta_empresa: Any,
        comision_bruta_vendedor: Any,
        tipo_persona_vendedor: str,
        aplica_itbis_vendedor: bool
    ) -> Dict[str, Any]:
        """Calcula retenciones fiscales según legislación RD."""
        TASA_ITBIS = Decimal('0.18')
        ISR_FISICA = Decimal('0.15')
        ISR_JURIDICA = Decimal('0.00')
        RETENCION_ITBIS_FISICA = Decimal('1.00')
        RETENCION_ITBIS_JURIDICA = Decimal('0.30')

        cbe = Decimal(str(comision_bruta_empresa or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        cbv = Decimal(str(comision_bruta_vendedor or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        itbis_empresa = (cbe * TASA_ITBIS).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        tipo = str(tipo_persona_vendedor or '').strip().lower()
        is_fisica = 'fisica' in tipo or 'física' in tipo or not tipo

        pct_isr = ISR_FISICA if is_fisica else ISR_JURIDICA
        retencion_isr = (cbv * pct_isr).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        itbis_vendedor = Decimal('0.00')
        pct_itbis_retenido = Decimal('0.00')
        retencion_itbis = Decimal('0.00')

        if aplica_itbis_vendedor:
            itbis_vendedor = (cbv * TASA_ITBIS).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            pct_itbis_retenido = RETENCION_ITBIS_FISICA if is_fisica else RETENCION_ITBIS_JURIDICA
            retencion_itbis = (itbis_vendedor * pct_itbis_retenido).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        total_retenciones = retencion_isr + retencion_itbis
        neto_pagado_vendedor = cbv + itbis_vendedor - total_retenciones
        costo_total_vendedor = cbv + itbis_vendedor - retencion_itbis
        ganancia_empresa_sin_itbis = cbe - cbv
        margen_empresa_neto = ganancia_empresa_sin_itbis - total_retenciones

        return {
            "comision_empresa_sin_itbis": float(cbe),
            "itbis_comision_empresa": float(itbis_empresa),
            "comision_vendedor_bruta": float(cbv),
            "tipo_persona_vendedor": "Fisica" if is_fisica else "Juridica",
            "aplica_itbis_vendedor": bool(aplica_itbis_vendedor),
            "pct_isr": float(pct_isr),
            "retencion_isr": float(retencion_isr),
            "itbis_vendedor": float(itbis_vendedor),
            "pct_itbis_retenido": float(pct_itbis_retenido),
            "retencion_itbis": float(retencion_itbis),
            "total_retenciones": float(total_retenciones),
            "neto_pagado_vendedor": float(neto_pagado_vendedor),
            "costo_total_vendedor": float(costo_total_vendedor),
            "ganancia_empresa_sin_itbis": float(ganancia_empresa_sin_itbis),
            "margen_empresa_neto": float(margen_empresa_neto)
        }
