"""
GuíaBot — API FastAPI
Endpoints para el dashboard web
"""

import os
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv
from bot.main import escanear_tarea

load_dotenv()

app = FastAPI(title="GuíaBot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_sb() -> Client:
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY"),
    )


# ── Health check ──────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "app": "GuíaBot CAC"}


# ── Cursos ────────────────────────────────────────────────
@app.get("/cursos/{docente_id}")
def listar_cursos(docente_id: str):
    sb = get_sb()
    result = sb.table("cursos").select("*").eq("docente_id", docente_id).eq("activo", True).execute()
    return result.data


# ── Tareas de un curso ────────────────────────────────────
@app.get("/tareas/{curso_id}")
def listar_tareas(curso_id: str):
    sb = get_sb()
    result = sb.table("tareas").select("*").eq("curso_id", curso_id).execute()
    return result.data


# ── Entregas de una tarea ─────────────────────────────────
@app.get("/entregas/{tarea_id}")
def listar_entregas(tarea_id: str):
    sb = get_sb()
    result = sb.table("entregas").select(
        "*, estudiantes(nombre_completo, email_gmail), reportes(*)"
    ).eq("tarea_id", tarea_id).execute()
    return result.data


# ── Reporte individual ────────────────────────────────────
@app.get("/reporte/{entrega_id}")
def obtener_reporte(entrega_id: str):
    sb = get_sb()
    result = sb.table("reportes").select("*").eq("entrega_id", entrega_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return result.data


# ── Resumen de tarea para el dashboard ───────────────────
@app.get("/resumen/{tarea_id}")
def resumen_tarea(tarea_id: str):
    sb = get_sb()

    entregas = sb.table("entregas").select(
        "estado, nombre_correcto, analisis_completado, reportes(ia_detectada, ia_probabilidad)"
    ).eq("tarea_id", tarea_id).execute().data

    total = len(entregas)
    entregados = sum(1 for e in entregas if e["estado"] in ("entregado", "entregado_tarde"))
    pendientes = sum(1 for e in entregas if e["estado"] == "pendiente")
    nombre_incorrecto = sum(1 for e in entregas if e["estado"] == "nombre_incorrecto")
    tarde = sum(1 for e in entregas if e["estado"] == "entregado_tarde")
    con_ia = sum(
        1 for e in entregas
        if e.get("reportes") and e["reportes"].get("ia_detectada")
    )

    return {
        "total_estudiantes": total,
        "entregados": entregados,
        "pendientes": pendientes,
        "entregado_tarde": tarde,
        "nombre_incorrecto": nombre_incorrecto,
        "posible_uso_ia": con_ia,
        "porcentaje_entrega": round(entregados / total * 100) if total else 0,
    }


# ── Trigger manual de escaneo ─────────────────────────────
@app.post("/escanear/{tarea_id}")
def trigger_escaneo(tarea_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(escanear_tarea, tarea_id)
    return {"mensaje": f"Escaneo iniciado para tarea {tarea_id}", "status": "procesando"}


# ── Notificaciones del docente ────────────────────────────
@app.get("/notificaciones/{usuario_id}")
def obtener_notificaciones(usuario_id: str):
    sb = get_sb()
    result = sb.table("notificaciones").select("*").eq(
        "usuario_id", usuario_id
    ).eq("leida", False).order("creado_en", desc=True).limit(20).execute()
    return result.data


@app.patch("/notificaciones/{notif_id}/leida")
def marcar_leida(notif_id: str):
    sb = get_sb()
    sb.table("notificaciones").update({"leida": True}).eq("id", notif_id).execute()
    return {"ok": True}
