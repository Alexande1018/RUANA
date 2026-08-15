"""Tests: Stripe obligatorio — sin cobro manual tras acuerdo."""

import os
import tempfile
import unittest

from core.db_manager import DBManager
from core.services import pago_service
from core.settings import get_settings


class TestStripeObligatorio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        os.environ["RUANA_DB_PATH"] = self.tmp.name
        os.environ["RUANA_STRIPE_PAYMENTS_ENABLED"] = "1"
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_x"
        os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
        get_settings.cache_clear()
        self.db = DBManager(db_path=self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _crear_par(self):
        for i, (codigo, nombre) in enumerate((("91001", "Sol"), ("91002", "Pro"))):
            r = self.db.crear_aliado(
                codigo=codigo,
                nombre=nombre,
                marca="M",
                oficio="Fontanería",
                codigo_postal="28001",
                email=f"{codigo}@test.com",
                telefono=f"+3461000000{i}",
                estado="activo",
                score=50,
            )
            self.assertEqual(r["status"], "success", r.get("message"))
        r = self.db.crear_contacto_ruana("91001", "91002", servicio="Servicio", motivo_contacto="Test")
        self.assertEqual(r["status"], "success", r.get("message"))
        return r["id"]

    def _habilitar_stripe(self, codigo="91002"):
        conn = self.db._connect()
        conn.execute(
            "UPDATE aliados SET stripe_account_id=?, stripe_charges_enabled=1 WHERE codigo=?",
            ("acct_test_oblig", codigo),
        )
        conn.commit()
        conn.close()

    def _flujo_hasta_precio(self, cid):
        pasos = [
            ("91001", "proponer", "servicio", "Reparación"),
            ("91002", "aceptar", "servicio", ""),
            ("91001", "proponer", "fecha", "2026-08-20"),
            ("91002", "aceptar", "fecha", ""),
            ("91001", "proponer", "hora", "10:00"),
            ("91002", "aceptar", "hora", ""),
            ("91001", "proponer", "direccion", "Calle 1"),
            ("91002", "aceptar", "direccion", ""),
            ("91001", "proponer", "observaciones", "Ok"),
            ("91002", "aceptar", "observaciones", "Ok"),
            ("91002", "proponer", "precio", "100"),
        ]
        for codigo, accion, campo, valor in pasos:
            if accion == "aceptar":
                res = self.db.aceptar_negociacion(cid, codigo, campo, valor)
            else:
                res = self.db.proponer_negociacion(cid, codigo, campo, valor)
            self.assertEqual(res["status"], "success", res.get("message"))

    def test_bloquea_acuerdo_sin_stripe_profesional(self):
        cid = self._crear_par()
        self._flujo_hasta_precio(cid)
        res = self.db.aceptar_negociacion(cid, "91001", "precio")
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["message"], pago_service.MSG_PROFESIONAL_STRIPE_NO_LISTO)
        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertNotEqual(contacto["estado"], "pendiente_de_pago")

    def test_acuerdo_con_stripe_activa_pago(self):
        cid = self._crear_par()
        self._habilitar_stripe("91002")
        self._flujo_hasta_precio(cid)
        res = self.db.aceptar_negociacion(cid, "91001", "precio")
        self.assertEqual(res["status"], "success", res.get("message"))
        self.assertTrue(res.get("cierre_automatico"))
        self.assertEqual(res.get("modo_pago"), "stripe")
        contacto = self.db.obtener_contacto_por_id(cid)
        self.assertEqual(contacto["estado"], "pendiente_de_pago")
        self.assertEqual(contacto["modo_pago"], "stripe")
        self.assertEqual(contacto["estado_pago"], "esperando_cobro_cliente")

    def test_negociacion_expone_aviso_pago_no_disponible(self):
        cid = self._crear_par()
        neg = self.db.obtener_negociacion_contacto(cid, "91001")
        self.assertEqual(neg["status"], "success")
        self.assertFalse(neg.get("profesional_stripe_listo"))
        self.assertEqual(neg.get("aviso_pago_no_disponible"), pago_service.AVISO_PAGO_NO_DISPONIBLE)
        self.assertEqual(
            neg.get("mensaje_stripe_negociacion"),
            pago_service.MSG_CONTRATANTE_ESPERA_STRIPE_PROFESIONAL,
        )

    def test_negociacion_profesional_expone_onboarding_stripe(self):
        cid = self._crear_par()
        neg = self.db.obtener_negociacion_contacto(cid, "91002")
        self.assertEqual(neg["status"], "success")
        self.assertFalse(neg.get("profesional_stripe_listo"))
        self.assertTrue(neg.get("puede_iniciar_onboarding_stripe"))
        self.assertEqual(
            neg.get("mensaje_stripe_negociacion"),
            pago_service.MSG_PROFESIONAL_DEBE_CONECTAR_STRIPE,
        )


if __name__ == "__main__":
    unittest.main()
