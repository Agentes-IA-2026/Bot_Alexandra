"""
GuíaBot — Orquestador principal
Escanea carpetas de Drive, procesa entregas y guarda resultados en Supabase
"""

import os
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client

from bot.drive.cliente import (
    listar_archivos_carpeta,
    descargar_docx,
    obtener_propietario,
    verificar_nombre_archivo,
)
from bot.drive.extractor import extraer_texto_docx, verificar_escala_cac
from bot.analyzer.analizador import analizar_ensayo

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("guiabot")


def get_supabase() -> Client:
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY"),  # Service key para el bot
    )


def escanear_tarea(tarea_id: str):
    """
    Escanea la carpeta Drive de una tarea específica y procesa las entregas nuevas.
    """
    sb = get_supabase()

    # 1. Cargar datos de la tarea y el curso
    tarea = sb.table("tareas").select(
        "*, cursos(grado, grupo, materia, docente_id)"
    ).eq("id", tarea_id).single().execute().data

    if not tarea or not tarea.get("drive_folder_id"):
        log.error(f"Tarea {tarea_id} no encontrada o sin carpeta Drive configurada.")
        return

    grado = tarea["cursos"]["grado"]
    folder_id = tarea["drive_folder_id"]

    log.info(f"Escaneando tarea: {tarea['titulo']} | Grado {grado} | Carpeta: {folder_id}")

    # 2. Listar archivos en la carpeta Drive
    archivos = listar_archivos_carpeta(folder_id)
    log.info(f"  → {len(archivos)} archivo(s) encontrado(s) en Drive")

    # Filtrar solo .docx y Google Docs (ensayos)
    ensayos = [
        f for f in archivos
        if f["name"].lower().endswith(".docx")
        or f.get("mimeType") == "application/vnd.google-apps.document"
    ]

    for archivo in ensayos:
        procesar_archivo(sb, archivo, tarea, grado)

    # 3. Log del escaneo
    sb.table("bot_logs").insert({
        "tipo": "scan_drive",
        "curso_id": tarea["cursos"].get("id") if isinstance(tarea.get("cursos"), dict) else None,
        "detalle": {
            "tarea_id": tarea_id,
            "archivos_total": len(archivos),
            "ensayos_procesados": len(ensayos),
        },
    }).execute()


def procesar_archivo(sb: Client, archivo: dict, tarea: dict, grado: str):
    """
    Procesa un archivo individual: verifica nombre, extrae texto y analiza con Claude.
    """
    file_id = archivo["id"]
    file_name = archivo["name"]
    propietario_email = obtener_propietario(archivo)

    log.info(f"  Procesando: {file_name} ({propietario_email})")

    # 1. Buscar o crear la entrega en Supabase
    entrega_existente = sb.table("entregas").select("id, analisis_completado").eq(
        "drive_file_id", file_id
    ).execute().data

    if entrega_existente and entrega_existente[0].get("analisis_completado"):
        log.info(f"    → Ya analizado, omitiendo.")
        return

    # 2. Buscar estudiante por email
    estudiante = sb.table("estudiantes").select("id, nombre_completo").eq(
        "email_gmail", propietario_email
    ).eq("curso_id", tarea.get("curso_id")).execute().data

    estudiante_id = estudiante[0]["id"] if estudiante else None

    # 3. Verificar nombre del archivo
    verificacion_nombre = verificar_nombre_archivo(file_name)

    # 4. Determinar estado
    fecha_entrega = tarea.get("fecha_entrega")
    fecha_subida = archivo.get("modifiedTime")
    estado = "entregado"
    if not verificacion_nombre["cumple"]:
        estado = "nombre_incorrecto"
    elif fecha_entrega and fecha_subida:
        fecha_subida_dt = datetime.fromisoformat(fecha_subida.replace("Z", "+00:00"))
        fecha_limite_dt = datetime.fromisoformat(f"{fecha_entrega}T23:59:59+00:00")
        if fecha_subida_dt > fecha_limite_dt:
            estado = "entregado_tarde"

    # 5. Guardar o actualizar entrega
    datos_entrega = {
        "tarea_id": tarea["id"],
        "estudiante_id": estudiante_id,
        "drive_file_id": file_id,
        "drive_file_name": file_name,
        "drive_owner_email": propietario_email,
        "drive_url": archivo.get("webViewLink"),
        "fecha_subida": fecha_subida,
        "estado": estado,
        "nombre_correcto": verificacion_nombre["cumple"],
        "analisis_completado": False,
    }

    if entrega_existente:
        entrega_id = entrega_existente[0]["id"]
        sb.table("entregas").update(datos_entrega).eq("id", entrega_id).execute()
    else:
        result = sb.table("entregas").insert(datos_entrega).execute()
        entrega_id = result.data[0]["id"]

    # 6. Si el nombre es incorrecto, no analizar el contenido
    if not verificacion_nombre["cumple"]:
        log.warning(f"    ⚠ Nombre incorrecto: {verificacion_nombre['razon']}")
        _notificar_docente(sb, tarea, file_name, propietario_email, "nombre_incorrecto")
        return

    # 7. Descargar y extraer texto
    try:
        contenido = descargar_docx(file_id)
        extraccion = extraer_texto_docx(contenido)
    except Exception as e:
        log.error(f"    ✗ Error descargando/extrayendo: {e}")
        sb.table("bot_logs").insert({
            "tipo": "error",
            "detalle": {"entrega_id": entrega_id, "archivo": file_name},
            "error": str(e),
        }).execute()
        return

    # 8. Verificar escala CAC
    escala = verificar_escala_cac(grado, extraccion["conteo_palabras"], extraccion["conteo_parrafos"])

    # 9. Analizar con Claude
    try:
        log.info(f"    → Analizando con Claude ({extraccion['conteo_palabras']} palabras)...")
        analisis = analizar_ensayo(
            texto_ensayo=extraccion["texto_completo"],
            grado=grado,
            conteo_palabras=extraccion["conteo_palabras"],
            conteo_parrafos=extraccion["conteo_parrafos"],
        )
    except Exception as e:
        log.error(f"    ✗ Error en análisis Claude: {e}")
        sb.table("bot_logs").insert({
            "tipo": "error",
            "detalle": {"entrega_id": entrega_id, "paso": "claude_analisis"},
            "error": str(e),
        }).execute()
        return

    # 10. Guardar reporte
    criterios = analisis.get("criterios", {})
    estructura = analisis.get("estructura", {})

    sb.table("reportes").upsert({
        "entrega_id": entrega_id,
        "ia_detectada": analisis.get("ia_detectada"),
        "ia_probabilidad": analisis.get("ia_probabilidad"),
        "ia_senales": analisis.get("ia_senales", []),
        "criterio_tesis": criterios.get("planteamiento_tesis"),
        "criterio_argumentacion": criterios.get("argumentacion_conceptual"),
        "criterio_contraargumentacion": criterios.get("contraargumentacion"),
        "criterio_fuentes": criterios.get("uso_fuentes"),
        "criterio_coherencia": criterios.get("coherencia_estructura"),
        "criterio_pensamiento": criterios.get("pensamiento_critico"),
        "tiene_portada_apa": estructura.get("tiene_portada_apa"),
        "tiene_epigrafe": estructura.get("tiene_epigrafe"),
        "tiene_cita_corta": estructura.get("tiene_cita_corta"),
        "tiene_cita_larga": estructura.get("tiene_cita_larga"),
        "tiene_contraargumentos": estructura.get("tiene_contraargumentos"),
        "tiene_conclusion": estructura.get("tiene_conclusion"),
        "tiene_referencias_apa": estructura.get("tiene_referencias_apa"),
        "conteo_palabras": extraccion["conteo_palabras"],
        "conteo_parrafos": extraccion["conteo_parrafos"],
        "cumple_escala_cac": analisis.get("cumple_escala_cac"),
        "escala_esperada_min": escala.get("escala_esperada_min"),  # lo que devuelve verificar_escala_cac no tiene esta clave, se puede mejorar
        "resumen_docente": analisis.get("resumen_docente"),
        "justificacion_criterios": analisis.get("justificacion_criterios"),
        "recomendaciones": analisis.get("recomendaciones"),
        "modelo_ia_usado": analisis.get("modelo_usado"),
        "tokens_usados": analisis.get("tokens_usados"),
    }).execute()

    # 11. Marcar entrega como completada
    sb.table("entregas").update({
        "analisis_completado": True,
        "procesado_en": datetime.now(timezone.utc).isoformat(),
    }).eq("id", entrega_id).execute()

    log.info(f"    ✓ Análisis completo. IA: {analisis.get('ia_probabilidad')}% | Criterios guardados.")

    # 12. Notificar al docente
    _notificar_docente(sb, tarea, file_name, propietario_email, "analisis_listo",
                       ia_detectada=analisis.get("ia_detectada"))


def _notificar_docente(sb: Client, tarea: dict, archivo: str, email_estudiante: str,
                        tipo: str, ia_detectada: bool = False):
    """Crea una notificación para el docente."""
    docente_id = tarea["cursos"].get("docente_id") if isinstance(tarea.get("cursos"), dict) else None
    if not docente_id:
        return

    mensajes = {
        "analisis_listo": f"✅ Análisis completado: '{archivo}' ({email_estudiante})" +
                          (" — ⚠️ Posible uso de IA detectado." if ia_detectada else ""),
        "nombre_incorrecto": f"⚠️ Nombre de archivo incorrecto: '{archivo}' subido por {email_estudiante}",
    }

    sb.table("notificaciones").insert({
        "usuario_id": docente_id,
        "tipo": tipo,
        "mensaje": mensajes.get(tipo, f"Evento: {tipo} — {archivo}"),
    }).execute()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        escanear_tarea(sys.argv[1])
    else:
        print("Uso: python -m bot.main [tarea_id]")
