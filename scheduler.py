"""
GuíaBot — Scheduler
Escaneo automático de Drive cada N minutos
"""

import os
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from supabase import create_client
from bot.main import escanear_tarea

load_dotenv()
log = logging.getLogger("guiabot.scheduler")


def escanear_todas_las_tareas():
    """Escanea todas las tareas activas que tienen carpeta Drive configurada."""
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

    tareas = sb.table("tareas").select(
        "id, titulo, cursos(activo)"
    ).not_.is_("drive_folder_id", "null").execute().data

    tareas_activas = [t for t in tareas if t.get("cursos", {}).get("activo")]
    log.info(f"Escaneando {len(tareas_activas)} tarea(s) activa(s)...")

    for tarea in tareas_activas:
        try:
            escanear_tarea(tarea["id"])
        except Exception as e:
            log.error(f"Error escaneando tarea {tarea['id']}: {e}")


if __name__ == "__main__":
    intervalo = int(os.getenv("BOT_SCAN_INTERVAL_MINUTES", "30"))
    scheduler = BlockingScheduler()
    scheduler.add_job(escanear_todas_las_tareas, "interval", minutes=intervalo)
    log.info(f"Scheduler iniciado. Intervalo: {intervalo} minutos.")
    scheduler.start()
