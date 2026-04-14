"""
GuíaBot — Módulo Google Drive
Lectura de carpetas y descarga de archivos .docx
"""

import io
import os
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_drive_service():
    """Crea y retorna el cliente autenticado de Google Drive."""
    creds = service_account.Credentials.from_service_account_file(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "config/service_account.json"),
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds)


def listar_archivos_carpeta(folder_id: str) -> list[dict]:
    """
    Lista todos los archivos dentro de una carpeta de Drive.
    Retorna lista de dicts con: id, name, mimeType, owners, modifiedTime, webViewLink
    """
    service = get_drive_service()
    resultados = []
    page_token = None

    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, owners, lastModifyingUser, modifiedTime, webViewLink, size)",
            pageToken=page_token,
            pageSize=100,
        ).execute()

        resultados.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return resultados


def descargar_docx(file_id: str) -> Optional[bytes]:
    """
    Descarga un archivo .docx de Drive y retorna sus bytes.
    Si es Google Doc, lo exporta como .docx.
    """
    service = get_drive_service()

    # Verificar tipo de archivo
    file_meta = service.files().get(fileId=file_id, fields="mimeType, name").execute()
    mime = file_meta.get("mimeType", "")

    buffer = io.BytesIO()

    if mime == "application/vnd.google-apps.document":
        # Es un Google Doc — exportar como docx
        request = service.files().export_media(
            fileId=file_id,
            mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    else:
        # Es un .docx subido directamente
        request = service.files().get_media(fileId=file_id)

    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    return buffer.getvalue()


def obtener_propietario(file_info: dict) -> str:
    """
    Extrae el email del propietario/último modificador del archivo.
    """
    # Intentar lastModifyingUser primero
    modifier = file_info.get("lastModifyingUser", {})
    if modifier.get("emailAddress"):
        return modifier["emailAddress"]

    # Fallback a owners
    owners = file_info.get("owners", [])
    if owners:
        return owners[0].get("emailAddress", "desconocido")

    return "desconocido"


def verificar_nombre_archivo(nombre: str) -> dict:
    """
    Verifica si el nombre del archivo cumple la convención CAC:
    Patrón esperado: 'Ensayo [TÍTULO EN MAYÚSCULAS].docx'

    Retorna dict con: cumple (bool), razon (str)
    """
    nombre = nombre.strip()

    # Debe ser .docx
    if not nombre.lower().endswith(".docx"):
        return {
            "cumple": False,
            "razon": f"El archivo debe ser .docx, se recibió: '{nombre.split('.')[-1] if '.' in nombre else 'sin extensión'}'",
        }

    # Debe empezar con "Ensayo"
    nombre_sin_ext = nombre[:-5]  # quitar .docx
    if not nombre_sin_ext.startswith("Ensayo"):
        return {
            "cumple": False,
            "razon": f"El nombre debe comenzar con 'Ensayo', se recibió: '{nombre_sin_ext[:20]}...'",
        }

    # Debe tener contenido después de "Ensayo "
    titulo = nombre_sin_ext[6:].strip()  # quitar "Ensayo"
    if len(titulo) < 3:
        return {
            "cumple": False,
            "razon": "Falta el título del ensayo después de la palabra 'Ensayo'.",
        }

    return {
        "cumple": True,
        "razon": f"Nombre correcto. Título detectado: '{titulo}'",
    }
