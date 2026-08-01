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
        self.assertEqual(sol['accion'].get('servicio_precargado'), 'Reparación grifo')
        self.assertNotIn('servicio', sol['accion'].get('campos', []))
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
        self.assertTrue(ok.get('cierre_automatico'), ok)
        self.assertEqual(ok.get('estado_contacto') or ok.get('estado_cierre'), 'trabajo_cerrado')

        final = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertTrue(final.get('acuerdo_alcanzado') or final['negociacion'].get('completo'))
        self.assertEqual(final['estado_contacto'], 'trabajo_cerrado')
        self.assertEqual(final['accion']['tipo'], 'cerrado')

        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertIsNotNone(contacto)
        self.assertEqual(contacto['estado'], 'trabajo_cerrado')
        self.assertTrue(contacto.get('acuerdo_resumen_json'))
        self.assertEqual(float(contacto.get('importe_acordado') or 0), 150.0)

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
        last = None
        for codigo, accion, campo, valor in pasos:
            if accion == 'aceptar':
                last = self.db.aceptar_negociacion(cid, codigo, campo, valor)
            else:
                last = self.db.proponer_negociacion(cid, codigo, campo, valor)
            self.assertEqual(last['status'], 'success', last.get('message'))

        self.assertTrue(last.get('cierre_automatico'), last)
        self.assertEqual(last.get('estado_contacto') or last.get('estado_cierre'), 'trabajo_cerrado')

        final = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertTrue(final.get('acuerdo_alcanzado') or final['negociacion'].get('completo'))
        self.assertEqual(final['estado_contacto'], 'trabajo_cerrado')
        self.assertEqual(final['accion']['tipo'], 'cerrado')

        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertIsNotNone(contacto)
        self.assertEqual(contacto['estado'], 'trabajo_cerrado')
        self.assertTrue(contacto.get('acuerdo_resumen_json'))
        self.assertEqual(float(contacto.get('importe_acordado')), 150.0)
        self.assertEqual(float(contacto['importe_final']), 150.0)
        self.assertEqual(contacto.get('estado_pago'), 'pendiente_pago')
        self.assertGreater(float(contacto.get('apoyo_ruana') or 0), 0)

    def _flujo_hasta_acuerdo(self, precio='150'):
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
            ('90002', 'proponer', 'precio', precio),
            ('90001', 'aceptar', 'precio', ''),
        ]
        for codigo, accion, campo, valor in pasos:
            if accion == 'aceptar':
                r = self.db.aceptar_negociacion(cid, codigo, campo, valor)
            else:
                r = self.db.proponer_negociacion(cid, codigo, campo, valor)
            self.assertEqual(r['status'], 'success', r.get('message'))
        return cid

    def test_cierre_bilateral_registra_trabajo(self):
        """Al aceptar el precio ya queda trabajo_cerrado; el cierre bilateral solo acusa el resumen."""
        cid = self._flujo_hasta_acuerdo('150')
        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertEqual(contacto['estado'], 'trabajo_cerrado')
        self.assertEqual(float(contacto['importe_final']), 150.0)
        self.assertEqual(contacto.get('estado_pago'), 'pendiente_pago')
        self.assertGreater(float(contacto.get('apoyo_ruana') or 0), 0)

        r1 = self.db.cerrar_negociacion(cid, '90001')
        self.assertEqual(r1['status'], 'success', r1.get('message'))
        self.assertEqual(r1.get('estado_contacto'), 'trabajo_cerrado')
        self.assertTrue(r1.get('yo_confirme_cierre'))

        r2 = self.db.cerrar_negociacion(cid, '90002')
        self.assertEqual(r2['status'], 'success', r2.get('message'))
        self.assertEqual(r2.get('estado_contacto'), 'trabajo_cerrado')

        acuerdos_sol = self.db.listar_acuerdos_aliado('90001')
        acuerdos_pro = self.db.listar_acuerdos_aliado('90002')
        self.assertTrue(any(a['contacto_id'] == cid and a['rol'] == 'contrate' for a in acuerdos_sol))
        self.assertTrue(any(a['contacto_id'] == cid and a['rol'] == 'contratado' for a in acuerdos_pro))

    def test_confirmar_importe_usa_precio_acordado_no_cliente(self):
        # Crear acuerdo sin auto-cierre numérico no aplica; usamos precio y verificamos
        # que un segundo intento con otro importe no cambia el oficial ya cerrado.
        cid = self._flujo_hasta_acuerdo('200')
        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertEqual(contacto['estado'], 'trabajo_cerrado')
        self.assertEqual(float(contacto['importe_final']), 200.0)
        r = self.db.registrar_importe_contacto(
            cid, 'solicitante', 999.0, usuario='90001', usar_precio_acordado=False,
        )
        self.assertEqual(r['status'], 'error')
        self.assertEqual(r.get('estado'), 'trabajo_cerrado')
        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertEqual(float(contacto['importe_final']), 200.0)

    def test_confirmar_acordado_sin_reingreso(self):
        cid = self._flujo_hasta_acuerdo('175')
        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertEqual(contacto['estado'], 'trabajo_cerrado')
        self.assertEqual(float(contacto['importe_final']), 175.0)
        self.assertEqual(float(contacto.get('importe_acordado')), 175.0)

    def test_dismiss_resumen_oculta_flotante(self):
        cid = self._flujo_hasta_acuerdo('120')
        visibles = self.db.listar_resumenes_acuerdo_visibles('90001')
        self.assertTrue(any(v['contacto_id'] == cid for v in visibles))
        r = self.db.dismiss_resumen_acuerdo(cid, '90001')
        self.assertEqual(r['status'], 'success')
        visibles2 = self.db.listar_resumenes_acuerdo_visibles('90001')
        self.assertFalse(any(v['contacto_id'] == cid for v in visibles2))
        # La otra parte sigue viéndolo
        visibles_pro = self.db.listar_resumenes_acuerdo_visibles('90002')
        self.assertTrue(any(v['contacto_id'] == cid for v in visibles_pro))

    def test_acuerdo_precio_ilegible_no_cierra_automatico(self):
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
            ('90002', 'proponer', 'precio', 'a convenir'),
            ('90001', 'aceptar', 'precio', ''),
        ]
        last = None
        for codigo, accion, campo, valor in pasos:
            if accion == 'aceptar':
                last = self.db.aceptar_negociacion(cid, codigo, campo, valor)
            else:
                last = self.db.proponer_negociacion(cid, codigo, campo, valor)
            self.assertEqual(last['status'], 'success', last.get('message'))

        self.assertFalse(last.get('cierre_automatico'))
        self.assertEqual(last.get('estado_contacto'), 'acuerdo_alcanzado')

        final = self.db.obtener_negociacion_contacto(cid, '90001')
        self.assertEqual(final['estado_contacto'], 'acuerdo_alcanzado')
        self.assertEqual(final['accion']['tipo'], 'resumen')

        self.db.cerrar_negociacion(cid, '90001')
        r2 = self.db.cerrar_negociacion(cid, '90002')
        self.assertEqual(r2['status'], 'success', r2.get('message'))
        self.assertFalse(r2.get('cierre_automatico'))
        self.assertTrue(r2.get('cierre_aviso'))
        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertEqual(contacto['estado'], 'acuerdo_alcanzado')
        self.assertTrue(contacto.get('cierre_confirmado_solicitante_en'))
        self.assertTrue(contacto.get('cierre_confirmado_profesional_en'))

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
