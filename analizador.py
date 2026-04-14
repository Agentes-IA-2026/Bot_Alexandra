"""
GuíaBot — Motor de análisis con Claude
Evalúa rúbrica CAC, detecta uso de IA y verifica estructura del ensayo
"""

import os
import json
import anthropic

MODELO = "claude-sonnet-4-20250514"

PROMPT_SISTEMA = """Eres GuíaBot, un asistente académico especializado en evaluar ensayos argumentativos 
de estudiantes de colegio según la Rúbrica CAC (Cluster / Núcleo Común). 

Tu función es producir reportes objetivos, detallados y útiles para el docente.
Siempre respondes en español colombiano formal.
Nunca inventas información que no esté en el texto del estudiante.
Cuando detectas uso de IA, eres específico sobre las señales encontradas, no haces acusaciones vagas."""

PROMPT_ANALISIS = """Analiza el siguiente ensayo de un estudiante de grado {grado} y produce un reporte completo.

═══════════════════════════════════════════
TEXTO DEL ENSAYO
═══════════════════════════════════════════
{texto_ensayo}

═══════════════════════════════════════════
DATOS DEL ESTUDIANTE
═══════════════════════════════════════════
- Grado: {grado}°
- Tipo de texto esperado según escala CAC: {tipo_texto}
- Rango de palabras esperado: {palabras_min}–{palabras_max}
- Rango de párrafos esperado: {parrafos_min}–{parrafos_max}
- Palabras contadas: {conteo_palabras}
- Párrafos contados: {conteo_parrafos}

═══════════════════════════════════════════
RÚBRICA CAC — 6 CRITERIOS
═══════════════════════════════════════════
Evalúa cada criterio en: bajo / basico / alto / superior

1. PLANTEAMIENTO DE LA TESIS
   - bajo: La tesis es vaga o no expresa postura clara.
   - basico: La tesis es identificable pero general.
   - alto: La tesis es clara y discutible.
   - superior: La tesis formula un problema complejo e integra conceptos teóricos.

2. ARGUMENTACIÓN CONCEPTUAL
   - bajo: Argumentos superficiales o descriptivos.
   - basico: Argumentos con evidencia limitada.
   - alto: Argumentos claros sustentados en evidencia.
   - superior: Argumentación sólida que articula teorías, conceptos y evidencias.

3. CONTRAARGUMENTACIÓN
   - bajo: No reconoce posturas contrarias.
   - basico: Menciona objeciones de forma superficial.
   - alto: Expone contraargumentos relevantes.
   - superior: Analiza críticamente objeciones complejas y defiende la tesis.

4. USO DE FUENTES Y PROBIDAD ACADÉMICA
   - bajo: Uso mínimo de fuentes o sin citación.
   - basico: Uso limitado de fuentes con errores.
   - alto: Uso correcto de fuentes académicas.
   - superior: Análisis crítico de fuentes primarias y secundarias.

5. COHERENCIA Y ESTRUCTURA
   - bajo: Texto sin organización lógica.
   - basico: Estructura básica con transiciones débiles.
   - alto: Coherencia entre introducción, desarrollo y conclusión.
   - superior: Arquitectura argumentativa rigurosa con precisión gramatical y conectores lógicos.

6. PENSAMIENTO CRÍTICO Y SÍNTESIS
   - bajo: Predomina la descripción.
   - basico: Análisis limitado.
   - alto: Relaciona conceptos y evidencia.
   - superior: Evalúa teorías y propone interpretación original.

═══════════════════════════════════════════
ESTRUCTURA MÍNIMA REQUERIDA (verificar presencia)
═══════════════════════════════════════════
- Portada en formato APA (nombre, institución, fecha, título)
- Epígrafe en la introducción (máxima conceptual o fragmento)
- Cita textual corta en la introducción
- Cita textual larga en el desarrollo
- Contraargumentos en el desarrollo
- Conclusión que retoma la tesis
- Referencias bibliográficas en normas APA

═══════════════════════════════════════════
DETECCIÓN DE USO DE IA
═══════════════════════════════════════════
Analiza el texto buscando estas señales de escritura generada por IA:
- Vocabulario excesivamente uniforme y sofisticado para el grado
- Ausencia total de errores ortográficos o gramaticales propios de la edad
- Estructura demasiado perfecta y mecánica
- Frases genéricas y formulaicas sin voz personal
- Transiciones artificialmente fluidas
- Ausencia de experiencias, ejemplos personales o referencias locales
- Uso excesivo de conectores formales (sin embargo, no obstante, en conclusión)
- Párrafos perfectamente simétricos en longitud
- Ausencia de imprecisiones o dudas propias del aprendizaje

═══════════════════════════════════════════
INSTRUCCIONES DE RESPUESTA
═══════════════════════════════════════════
Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:

{{
  "ia_detectada": true/false,
  "ia_probabilidad": 0-100,
  "ia_senales": ["señal 1 encontrada", "señal 2 encontrada"],
  "criterios": {{
    "planteamiento_tesis": "bajo|basico|alto|superior",
    "argumentacion_conceptual": "bajo|basico|alto|superior",
    "contraargumentacion": "bajo|basico|alto|superior",
    "uso_fuentes": "bajo|basico|alto|superior",
    "coherencia_estructura": "bajo|basico|alto|superior",
    "pensamiento_critico": "bajo|basico|alto|superior"
  }},
  "justificacion_criterios": {{
    "planteamiento_tesis": "explicación específica con cita del texto",
    "argumentacion_conceptual": "explicación específica con cita del texto",
    "contraargumentacion": "explicación específica con cita del texto",
    "uso_fuentes": "explicación específica con cita del texto",
    "coherencia_estructura": "explicación específica con cita del texto",
    "pensamiento_critico": "explicación específica con cita del texto"
  }},
  "estructura": {{
    "tiene_portada_apa": true/false,
    "tiene_epigrafe": true/false,
    "tiene_cita_corta": true/false,
    "tiene_cita_larga": true/false,
    "tiene_contraargumentos": true/false,
    "tiene_conclusion": true/false,
    "tiene_referencias_apa": true/false
  }},
  "cumple_escala_cac": true/false,
  "resumen_docente": "Párrafo narrativo de 3-5 oraciones para el docente resumiendo los hallazgos más importantes",
  "recomendaciones": "2-3 recomendaciones concretas para que el estudiante mejore su trabajo"
}}"""


ESCALA_CAC = {
    "6":  {"tipo": "Descripción científica / observación", "palabras_min": 80,  "palabras_max": 150,  "parrafos_min": 1, "parrafos_max": 2},
    "7":  {"tipo": "Explicación de fenómeno",              "palabras_min": 150, "palabras_max": 250,  "parrafos_min": 2, "parrafos_max": 3},
    "8":  {"tipo": "Análisis simple de datos",             "palabras_min": 250, "palabras_max": 350,  "parrafos_min": 3, "parrafos_max": 4},
    "9":  {"tipo": "Argumentación básica",                 "palabras_min": 350, "palabras_max": 500,  "parrafos_min": 4, "parrafos_max": 5},
    "10": {"tipo": "Desarrollo teórico inicial",           "palabras_min": 500, "palabras_max": 700,  "parrafos_min": 5, "parrafos_max": 7},
    "11": {"tipo": "Escritura académica investigativa",    "palabras_min": 800, "palabras_max": 1200, "parrafos_min": 8, "parrafos_max": 12},
}


def analizar_ensayo(
    texto_ensayo: str,
    grado: str,
    conteo_palabras: int,
    conteo_parrafos: int,
) -> dict:
    """
    Envía el ensayo a Claude y retorna el análisis completo.
    """
    escala = ESCALA_CAC.get(str(grado), ESCALA_CAC["10"])

    prompt = PROMPT_ANALISIS.format(
        grado=grado,
        texto_ensayo=texto_ensayo[:8000],  # límite seguro de tokens
        tipo_texto=escala["tipo"],
        palabras_min=escala["palabras_min"],
        palabras_max=escala["palabras_max"],
        parrafos_min=escala["parrafos_min"],
        parrafos_max=escala["parrafos_max"],
        conteo_palabras=conteo_palabras,
        conteo_parrafos=conteo_parrafos,
    )

    cliente = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=2000,
        system=PROMPT_SISTEMA,
        messages=[{"role": "user", "content": prompt}],
    )

    texto_respuesta = respuesta.content[0].text.strip()

    # Limpiar posibles backticks de markdown
    if texto_respuesta.startswith("```"):
        texto_respuesta = texto_respuesta.split("```")[1]
        if texto_respuesta.startswith("json"):
            texto_respuesta = texto_respuesta[4:]

    resultado = json.loads(texto_respuesta)
    resultado["tokens_usados"] = respuesta.usage.input_tokens + respuesta.usage.output_tokens
    resultado["modelo_usado"] = MODELO

    return resultado
