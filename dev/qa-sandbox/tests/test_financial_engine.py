"""
test_financial_engine.py — Tests for the unified FinancialEngine.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.financial_engine import FinancialEngine


class TestEstructurarVenta:
    """Tests for estructurar_venta."""

    def test_basic(self):
        r = FinancialEngine.estructurar_venta(2000000, 100000, 400000, 10)
        assert r['monto_diferido'] == 300000.0
        assert r['valor_cuota_mensual'] == 30000.0
        assert r['monto_a_financiar'] == 1600000.0
        assert r['num_cuotas'] == 10

    def test_sin_separacion(self):
        r = FinancialEngine.estructurar_venta(1000000, 0, 200000, 5)
        assert r['monto_diferido'] == 200000.0
        assert r['valor_cuota_mensual'] == 40000.0
        assert r['monto_a_financiar'] == 800000.0

    def test_cero_cuotas(self):
        r = FinancialEngine.estructurar_venta(1000000, 100000, 300000, 0)
        assert r['num_cuotas'] == 0
        assert r['valor_cuota_mensual'] == 0.0

    def test_separacion_igual_diferido(self):
        r = FinancialEngine.estructurar_venta(1000000, 500000, 500000, 5)
        assert r['monto_diferido'] == 0.0
        assert r['monto_a_financiar'] == 500000.0

    def test_monto_total_consistency(self):
        r = FinancialEngine.estructurar_venta(3000000, 200000, 800000, 20)
        # monto_separacion + monto_diferido + monto_a_financiar == monto_total
        total = r['monto_separacion'] + r['monto_diferido'] + r['monto_a_financiar']
        assert total == 3000000.0


class TestBolsaComision:
    """Tests for calcular_bolsa_comision."""

    def test_basic(self):
        assert float(FinancialEngine.calcular_bolsa_comision(2000000, 5)) == 100000.0

    def test_zero_pct(self):
        assert float(FinancialEngine.calcular_bolsa_comision(2000000, 0)) == 0.0

    def test_high_pct(self):
        assert float(FinancialEngine.calcular_bolsa_comision(1000000, 15)) == 150000.0


class TestDistribucionInmobiliaria:
    """Tests for calcular_distribucion_inmobiliaria."""

    def test_distribucion_normal(self):
        d = FinancialEngine.calcular_distribucion_inmobiliaria(100000, 1, 1, 'propio', True, True)
        total = d['comision_a'] + d['comision_n'] + d['comision_proyecto'] + d['comision_admin']
        assert abs(total - 100000.0) < 0.01

    def test_distribucion_all_pct(self):
        d = FinancialEngine.calcular_distribucion_inmobiliaria(100000, 1, 1, 'propio', True, True)
        assert d['pct_a'] + d['pct_n'] + d['pct_proyecto'] + d['pct_admin'] == 1.0

    def test_distribucion_zero_comision(self):
        d = FinancialEngine.calcular_distribucion_inmobiliaria(0, 1, 1, 'propio', True, True)
        assert d['comision_a'] == 0.0


class TestRetencionesFiscales:
    """Tests for calcular_retenciones_fiscales."""

    def test_persona_fisica_con_itbis(self):
        r = FinancialEngine.calcular_retenciones_fiscales(50000, 30000, 'Fisica', True)
        assert r['total_retenciones'] > 0
        assert r['retencion_isr'] > 0

    def test_persona_fisica_sin_itbis(self):
        r = FinancialEngine.calcular_retenciones_fiscales(50000, 30000, 'Fisica', False)
        assert r['total_retenciones'] >= 0

    def test_persona_juridica(self):
        r = FinancialEngine.calcular_retenciones_fiscales(100000, 50000, 'Juridica', True)
        assert r['total_retenciones'] > 0


class TestDistribuirComision:
    """Tests for distribuir_comision (simple)."""

    def test_basic_split(self):
        d = FinancialEngine.distribuir_comision(100000, 50, 30, 20)
        assert d['comision_vendedor'] == 50000.0
        assert d['comision_captador'] == 30000.0
        assert d['comision_empresa'] == 20000.0

    def test_total_equals_input(self):
        d = FinancialEngine.distribuir_comision(75000, 40, 40, 20)
        total = d['comision_vendedor'] + d['comision_captador'] + d['comision_empresa']
        assert abs(total - 75000.0) < 0.01


class TestHelpers:
    """Tests for helper methods."""

    def test_calcular_monto_diferido(self):
        assert FinancialEngine.calcular_monto_diferido(400000, 100000) == 300000.0

    def test_calcular_valor_cuota(self):
        assert FinancialEngine.calcular_valor_cuota(300000, 10) == 30000.0

    def test_calcular_saldo_cuota(self):
        assert FinancialEngine.calcular_saldo_cuota(100000, 40000) == 60000.0

    def test_calcular_total_pagado(self):
        pagos = [{'monto': 1000}, {'monto': 2000}, {'monto': 500}]
        assert FinancialEngine.calcular_total_pagado(pagos) == 3500.0

    def test_calcular_total_pagado_vacio(self):
        assert FinancialEngine.calcular_total_pagado([]) == 0.0

    def test_calcular_balance_asesor(self):
        assert float(FinancialEngine.calcular_balance_asesor(50000, 20000)) == 30000.0

    def test_calcular_balance_asesor_cero(self):
        assert float(FinancialEngine.calcular_balance_asesor(10000, 10000)) == 0.0
