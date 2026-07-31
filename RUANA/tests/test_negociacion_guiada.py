"""Tests del flujo de negociación guiada RUANA."""
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

    def _crear_aliados_y_contacto(self, servicio='Reparación grifo'):
        for i, (codigo, nombre) in enumerate((('90001', 'Sol'), ('90002', 'Pro'))):
            r = self.db.crear_aliado(
                codigo=codigo, nombre=nombre, marca='M', oficio='Fontanería',
                codigo_postal='28001', email=f'{codigo}@test.com',
                telefono=f'+3460000000{i}', estado='activo', score=50,
            )
            self.assertEqual(r['status'], 'success', r.get('message'))
        r = self.db.crear_contacto_ruana(
            '90001', '90002', servicio=servicio, motivo_contacto='Presupuesto'
        )
        self.assertEqual(r['status'], 'success', r.get('message'))
        return r['id']

    def test_inicio_solicitante_debe_proponer_completo(self):
        cid = self._crear_aliados_y_contacto()
        sol = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertEqual(sol['status'], 'success')
        self.assertEqual(sol['accion']['tipo'], 'wizard_contratante')
        self.assertEqual(sol['accion'].get('valores_sugeridos', {}).get('servicio'), 'Reparación grifo')
        self.assertNotIn('precio', sol['accion'].get('campos', []))

        pro = self.db.obtener_negociacion_contacto(cid, '90002')
        self.assertEqual(pro['accion']['tipo'], 'esperar')
        self.assertIn('contratante', pro['accion']['mensaje'].lower())

    def test_propuesta_completa_profesional_confirma_punto_por_punto(self):
        cid = self._crear_aliados_y_contacto()
        valores = {
            'servicio': 'Reparación grifo',
            'fecha': '2026-08-15',
            'hora': '10:00',
            'direccion': 'Calle Mayor 1',
            'observaciones': 'Llevar herramientas',
        }
        r = self.db.proponer_propuesta_completa_negociacion(cid, '90001', valores)
        self.assertEqual(r['status'], 'success', r.get('message'))
        self.assertEqual(r['negociacion']['campos']['precio']['estado'], neg_mgr.ESTADO_PENDIENTE)

        sol = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertEqual(sol['accion']['tipo'], 'proponer')
        self.assertTrue(sol['accion'].get('modificar_propia'))

        pro = self.db.obtener_negociacion_contacto(cid, '90002')
        self.assertEqual(pro['accion']['tipo'], 'responder')
        self.assertEqual(pro['accion']['campo'], 'servicio')

        for campo in ('servicio', 'fecha', 'hora', 'direccion', 'observaciones'):
            ok = self.db.aceptar_negociacion(cid, '90002', campo)
            self.assertEqual(ok['status'], 'success', ok.get('message'))

        pro_precio = self.db.obtener_negociacion_contacto(cid, '90002')
        self.assertEqual(pro_precio['accion']['tipo'], 'proponer')
        self.assertEqual(pro_precio['accion']['campo'], 'precio')

        r_precio = self.db.proponer_negociacion(cid, '90002', 'precio', '150')
        self.assertEqual(r_precio['status'], 'success', r_precio.get('message'))

        sol_precio = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertEqual(sol_precio['accion']['tipo'], 'responder')
        self.assertEqual(sol_precio['accion']['campo'], 'precio')

        ok = self.db.aceptar_negociacion(cid, '90001', 'precio')
        self.assertEqual(ok['status'], 'success', ok.get('message'))

        final = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertTrue(final.get('acuerdo_alcanzado') or final['negociacion'].get('completo'))
        self.assertEqual(final['accion']['tipo'], 'resumen')

    def test_flujo_servicio_profesional_responde(self):
        cid = self._crear_aliados_y_contacto()
        r = self.db.proponer_negociacion(cid, '90001', 'servicio', 'Reparación grifo')
        self.assertEqual(r['status'], 'success')
        pro = self.db.obtener_negociacion_contacto(cid, '90002')
        self.assertEqual(pro['accion']['tipo'], 'responder')
        self.assertEqual(pro['accion']['campo'], 'servicio')

        ok = self.db.aceptar_negociacion(cid, '90002', 'servicio')
        self.assertEqual(ok['status'], 'success')
        sol = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertEqual(sol['accion']['tipo'], 'proponer')
        self.assertEqual(sol['accion']['campo'], 'fecha')

    def test_flujo_completo_acuerdo_alcanzado(self):
        cid = self._crear_aliados_y_contacto()
        pasos = [
            ('90001', 'proponer', 'servicio', 'Reparación grifo'),
            ('90002', 'aceptar', 'servicio', ''),
            ('90001', 'proponer', 'fecha', '2026-08-15'),
            ('90002', 'aceptar', 'fecha', ''),
            ('90001', 'proponer', 'hora', '10:00'),
            ('90002', 'aceptar', 'hora', ''),
            ('90001', 'proponer', 'direccion', 'Calle Mayor 1'),
            ('90002', 'aceptar', 'direccion', ''),
            ('90001', 'proponer', 'observaciones', 'Llevar herramientas'),
            ('90002', 'aceptar', 'observaciones', 'Acceso por portal B'),
            ('90002', 'proponer', 'precio', '150'),
            ('90001', 'aceptar', 'precio', ''),
        ]
        for codigo, accion, campo, valor in pasos:
            if accion == 'aceptar':
                r = self.db.aceptar_negociacion(cid, codigo, campo, valor)
            else:
                r = self.db.proponer_negociacion(cid, codigo, campo, valor)
            self.assertEqual(r['status'], 'success', r.get('message'))

        final = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertTrue(final.get('acuerdo_alcanzado') or final['negociacion'].get('completo'))
        self.assertEqual(final['accion']['tipo'], 'resumen')

    def test_normalizar_estado_sin_bloqueo_paso_confirmado(self):
        estado = neg_mgr.estado_inicial()
        estado['campos']['servicio'] = {
            'valor': 'X', 'estado': neg_mgr.ESTADO_CONFIRMADO,
            'propuesto_por': 'solicitante', 'confirmado_en': '2026-01-01',
        }
        estado['paso_actual'] = 'servicio'  # desincronizado a propósito
        norm = neg_mgr.normalizar_estado(estado)
        self.assertEqual(norm['paso_actual'], 'fecha')
        acc = neg_mgr.accion_disponible(norm, 'solicitante', 'iniciado')
        self.assertEqual(acc['tipo'], 'proponer')
        self.assertEqual(acc['campo'], 'fecha')

    def test_contraoferta_solo_campo_en_disputa(self):
        cid = self._crear_aliados_y_contacto()
        self.db.proponer_negociacion(cid, '90001', 'servicio', 'Grifo')
        self.db.aceptar_negociacion(cid, '90002', 'servicio')
        self.db.proponer_negociacion(cid, '90001', 'fecha', '2026-08-01')
        r = self.db.contraoferta_negociacion(cid, '90002', 'fecha', '2026-08-05')
        self.assertEqual(r['status'], 'success')
        self.assertEqual(r['negociacion']['campos']['fecha']['valor'], '2026-08-05')
        self.assertEqual(r['negociacion']['campos']['fecha']['propuesto_por'], 'profesional')

        sol = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertEqual(sol['accion']['tipo'], 'responder')
        self.assertEqual(sol['accion']['campo'], 'fecha')
        self.assertTrue(sol.get('negociacion_meta', {}).get('requiere_mi_respuesta'))

    def test_contraoferta_propuesta_completa_desbloquea_contratante(self):
        cid = self._crear_aliados_y_contacto()
        valores = {
            'servicio': 'Baño de perro',
            'fecha': '2026-09-01',
            'hora': '11:00',
            'direccion': 'Calle Test 1',
            'observaciones': 'Perro mediano',
        }
        self.db.proponer_propuesta_completa_negociacion(cid, '90001', valores)
        r = self.db.contraoferta_negociacion(cid, '90002', 'servicio', 'Baño premium perro')
        self.assertEqual(r['status'], 'success', r.get('message'))

        sol = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertEqual(sol['accion']['tipo'], 'responder')
        self.assertEqual(sol['accion']['campo'], 'servicio')
        self.assertIn('profesional', sol['accion']['mensaje'].lower())

        ok = self.db.aceptar_negociacion(cid, '90001', 'servicio')
        self.assertEqual(ok['status'], 'success', ok.get('message'))

    def test_contraoferta_fuera_de_paso_actual_falla(self):
        cid = self._crear_aliados_y_contacto()
        valores = {
            'servicio': 'Servicio A',
            'fecha': '2026-09-01',
            'hora': '10:00',
            'direccion': 'Dir 1',
            'observaciones': 'Obs',
        }
        self.db.proponer_propuesta_completa_negociacion(cid, '90001', valores)
        r = self.db.contraoferta_negociacion(cid, '90002', 'fecha', '2026-09-05')
        self.assertEqual(r['status'], 'error')
        self.assertIn('paso actual', (r.get('message') or '').lower())

    def test_meta_negociacion_requiere_respuesta(self):
        cid = self._crear_aliados_y_contacto()
        self.db.proponer_negociacion(cid, '90001', 'servicio', 'Grifo')
        self.db.contraoferta_negociacion(cid, '90002', 'servicio', 'Grifo premium')
        sol = self.db.obtener_negociacion_contacto(cid, '90001')
        meta = sol.get('negociacion_meta') or {}
        self.assertTrue(meta.get('requiere_mi_respuesta'))
        self.assertEqual(meta.get('paso'), 'servicio')

    def test_cerrar_negociacion_ambas_partes(self):
        cid = self._crear_aliados_y_contacto()
        r = self.db.cerrar_negociacion(cid, '90001')
        self.assertEqual(r['status'], 'success')
        self.assertEqual(r['estado'], 'cerrado_no_concretado')
        neg = self.db.obtener_negociacion_contacto(cid, '90002')
        self.assertEqual(neg['accion']['tipo'], 'cerrado')
        r2 = self.db.cerrar_negociacion(cid, '90002')
        self.assertEqual(r2['status'], 'error')

    def test_resumen_sincronizado_con_estado(self):
        cid = self._crear_aliados_y_contacto()
        self.db.proponer_negociacion(cid, '90001', 'servicio', 'Grifo')
        neg = self.db.obtener_negociacion_contacto(cid, '90001')
        resumen = {i['campo']: i for i in neg['resumen']}
        self.assertEqual(resumen['servicio']['estado'], neg_mgr.ESTADO_EN_NEGOCIACION)
        self.assertEqual(resumen['servicio']['valor'], 'Grifo')
        self.assertEqual(resumen['fecha']['estado'], neg_mgr.ESTADO_PENDIENTE)

    def test_catalogo_servicios_configurados(self):
        self.db.crear_aliado(
            codigo='90002', nombre='Pro', marca='M', oficio='Fontanería',
            codigo_postal='28001', email='90002@test.com',
            telefono='+34600000002', estado='activo', score=50,
        )
        r = self.db.guardar_catalogo_servicio_aliado('90002', 1, 'Grifo', '80 EUR')
        self.assertEqual(r['status'], 'success')
        items = self.db.listar_catalogo_servicios_configurados('90002')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['descripcion'], 'Grifo')

    def test_cerrar_negociacion_excluye_contacto_abierto(self):
        cid = self._crear_aliados_y_contacto()
        self.db.cerrar_negociacion(cid, '90001')
        abiertos_sol = self.db.obtener_contactos_abiertos_por_codigo('90001')
        abiertos_pro = self.db.obtener_contactos_abiertos_por_codigo('90002')
        ids_sol = [c['id'] for c in abiertos_sol]
        ids_pro = [c['id'] for c in abiertos_pro]
        self.assertNotIn(cid, ids_sol)
        self.assertNotIn(cid, ids_pro)

    def test_no_concretado_excluye_contacto_abierto(self):
        cid = self._crear_aliados_y_contacto()
        r = self.db.marcar_cerrado_no_concretado(cid, actor_codigo='90002')
        self.assertEqual(r['status'], 'success')
        abiertos = self.db.obtener_contactos_abiertos_por_codigo('90001')
        self.assertTrue(all(c['id'] != cid for c in abiertos))

    def test_modificar_propia_propuesta_servicio(self):
        cid = self._crear_aliados_y_contacto()
        self.db.proponer_negociacion(cid, '90001', 'servicio', 'Grifo')
        r = self.db.proponer_negociacion(cid, '90001', 'servicio', 'Grifo y tubería')
        self.assertEqual(r['status'], 'success')
        self.assertEqual(r['negociacion']['campos']['servicio']['valor'], 'Grifo y tubería')
        pro = self.db.obtener_negociacion_contacto(cid, '90002')
        self.assertEqual(pro['accion']['tipo'], 'responder')


if __name__ == '__main__':
    unittest.main()
