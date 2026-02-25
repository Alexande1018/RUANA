"""
Colector de métricas - RUANA
Recolecta métricas reales desde DBManager (contactos_ruana) para el motor de evaluación.
"""


class MetricsCollector:
    """Colector de métricas para RUANA (métricas reales desde BD)."""

    def __init__(self, logger=None, db=None):
        """
        Inicializa el colector.
        logger: Logger opcional.
        db: Instancia de DBManager. Si no se pasa, collect(db=...) debe recibirla.
        """
        self.logger = logger
        self.db = db
        self.metrics = {}

    def collect(self, data: dict = None, db=None) -> dict:
        """
        Recolecta métricas reales por aliado desde la BD.
        tasa_respuesta, tasa_confirmacion, meses_sin_trabajo por cada aliado activo.
        data: No usado (compatibilidad).
        db: DBManager. Si no se pasa, usa self.db.
        Returns:
            dict codigo_aliado -> {tasa_respuesta, tasa_confirmacion, meses_sin_trabajo}
        """
        database = db or self.db
        if not database:
            if self.logger:
                self.logger.warning(
                    "📊 MetricsCollector: sin DB, no se pueden recolectar métricas reales"
                )
            self.metrics = {}
            return self.metrics

        codigos = database.listar_codigos_aliados_activos()
        self.metrics = {}
        for codigo in codigos:
            self.metrics[codigo] = database.obtener_metricas_motor_por_aliado(codigo)

        if self.logger:
            self.logger.debug(
                "📊 Métricas recolectadas: %s aliado(s) desde BD", len(self.metrics)
            )
        return self.metrics

    def get_metrics(self) -> dict:
        """Devuelve las métricas recolectadas (o vacío si no se ha llamado a collect)."""
        return self.metrics if self.metrics else {}
