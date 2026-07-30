"""Tests del flujo de negociación guiada RUANA."""
import json
import os
import tempfile
import unittest

from core.db_manager import DBManager
from core import negociacion_manager as neg_mgr


class TestNegociacionGuiada(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        os.environ['RUANA_DB_PATH'] = self.tmp.name
        self.db = DBManager(db_path=self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _crear_aliados_y_contacto(self):
        for i, (codigo, nombre) in enumerate((('90001', 'Sol'), ('90002', 'Pro'))):
            r = self.db.crear_aliado(
                codigo=codigo, nombre=nombre, marca='M', oficio='Fontanería',
                codigo_postal='28001', email=f'{codigo}@test.com',
                telefono=f'+3460000000{i}', estado='activo', score=50,
            )
            self.assertEqual(r['status'], 'success', r.get('message'))
        r = self.db.crear_contacto_ruana(
            '90001', '90002', servicio='Reparación grifo', motivo_contacto='Presupuesto'
        )
        self.assertEqual(r['status'], 'success', r.get('message'))
        return r['id']

    def test_inicio_negociacion_servicio_pendiente_aceptacion(self):
        cid = self._crear_aliados_y_contacto()
        ev = self.db.listar_eventos_negociacion(cid)
        self.assertGreaterEqual(len(ev), 2)
        neg = self.db.obtener_negociacion_contacto(cid, '90002')
        self.assertEqual(neg['status'], 'success')
        self.assertEqual(neg['accion']['tipo'], 'responder')
        self.assertEqual(neg['accion']['campo'], 'servicio')

        ok = self.db.aceptar_negociacion(cid, '90002', 'servicio')
        self.assertEqual(ok['status'], 'success')
        self.assertEqual(ok['negociacion']['campos']['servicio']['estado'], neg_mgr.ESTADO_CONFIRMADO)
        self.assertEqual(ok['accion']['tipo'], 'esperar')
        sol = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertEqual(sol['accion']['tipo'], 'proponer')
        self.assertEqual(sol['accion']['campo'], 'fecha')

    def test_flujo_completo_acuerdo_alcanzado(self):
        cid = self._crear_aliados_y_contacto()
        pasos = [
            ('90002', 'aceptar', 'servicio', ''),
            ('90001', 'proponer', 'fecha', '2026-08-15'),
            ('90002', 'aceptar', 'fecha', ''),
            ('90001', 'proponer', 'hora', '10:00'),
            ('90002', 'aceptar', 'hora', ''),
            ('90001', 'proponer', 'direccion', 'Calle Mayor 1'),
            ('90002', 'aceptar', 'direccion', ''),
            ('90001', 'proponer', 'precio', '150'),
            ('90002', 'aceptar', 'precio', ''),
            ('90001', 'proponer', 'observaciones', 'Llevar herramientas'),
            ('90002', 'aceptar', 'observaciones', 'Acceso por portal B'),
        ]
        for codigo, accion, campo, valor in pasos:
            if accion == 'aceptar':
                r = self.db.aceptar_negociacion(cid, codigo, campo, valor)
            else:
                r = self.db.proponer_negociacion(cid, codigo, campo, valor)
            self.assertEqual(r['status'], 'success', r.get('message'))

        final = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertTrue(final.get('acuerdo_alcanzado') or final['negociacion'].get('completo'))

    def test_contraoferta_solo_campo_en_disputa(self):
        cid = self._crear_aliados_y_contacto()
        self.db.aceptar_negociacion(cid, '90002', 'servicio')
        self.db.proponer_negociacion(cid, '90001', 'fecha', '2026-08-01')
        r = self.db.contraoferta_negociacion(cid, '90002', 'fecha', '2026-08-05')
        self.assertEqual(r['status'], 'success')
        self.assertEqual(r['negociacion']['campos']['fecha']['valor'], '2026-08-05')
        self.assertEqual(r['negociacion']['campos']['fecha']['propuesto_por'], 'profesional')


if __name__ == '__main__':
    unittest.main()
