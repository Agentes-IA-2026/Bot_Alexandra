-- ============================================================
-- GuíaBot CAC — Schema Supabase
-- ============================================================

-- ── 1. INSTITUCIONES ──────────────────────────────────────
CREATE TABLE instituciones (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre        TEXT NOT NULL,
  ciudad        TEXT,
  tipo          TEXT CHECK (tipo IN ('publico', 'privado')) DEFAULT 'privado',
  creado_en     TIMESTAMPTZ DEFAULT NOW()
);

-- ── 2. USUARIOS (docentes / coordinadores) ────────────────
CREATE TABLE usuarios (
  id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  institucion_id  UUID REFERENCES instituciones(id),
  nombre          TEXT NOT NULL,
  email           TEXT NOT NULL UNIQUE,
  rol             TEXT CHECK (rol IN ('docente', 'coordinador', 'admin')) DEFAULT 'docente',
  creado_en       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 3. CURSOS ─────────────────────────────────────────────
CREATE TABLE cursos (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  institucion_id  UUID REFERENCES instituciones(id),
  docente_id      UUID REFERENCES usuarios(id),
  nombre          TEXT NOT NULL,        -- ej: "10A Lenguaje y Comunicación"
  grado           TEXT NOT NULL,        -- ej: "10"
  grupo           TEXT NOT NULL,        -- ej: "A"
  materia         TEXT NOT NULL,        -- ej: "Lenguaje & Comunicación"
  anio            INT  DEFAULT EXTRACT(YEAR FROM NOW()),
  drive_folder_id TEXT,                 -- ID de la carpeta en Google Drive
  drive_folder_url TEXT,                -- URL completa de la carpeta
  activo          BOOLEAN DEFAULT TRUE,
  creado_en       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 4. ESTUDIANTES ────────────────────────────────────────
CREATE TABLE estudiantes (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  curso_id        UUID REFERENCES cursos(id),
  nombre_completo TEXT NOT NULL,
  email_gmail     TEXT NOT NULL,        -- correo con el que sube a Drive
  grado           TEXT NOT NULL,        -- para aplicar escala CAC correcta
  creado_en       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(curso_id, email_gmail)
);

-- ── 5. TAREAS ─────────────────────────────────────────────
CREATE TABLE tareas (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  curso_id            UUID REFERENCES cursos(id),
  titulo              TEXT NOT NULL,    -- ej: "Ensayo EL LENGUAJE COMO..."
  tipo                TEXT CHECK (tipo IN ('ensayo', 'investigacion', 'trabajo_escrito', 'otro')) DEFAULT 'ensayo',
  nombre_archivo_patron TEXT NOT NULL,  -- ej: "Ensayo [TÍTULO].docx"
  descripcion_patron  TEXT,             -- instrucción para el estudiante
  fecha_entrega       DATE,
  drive_folder_id     TEXT,             -- subcarpeta específica de esta tarea
  rubrica_id          UUID,             -- referencia a la rúbrica aplicada
  creado_en           TIMESTAMPTZ DEFAULT NOW()
);

-- ── 6. RÚBRICAS ───────────────────────────────────────────
CREATE TABLE rubricas (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  institucion_id  UUID REFERENCES instituciones(id),
  nombre          TEXT NOT NULL,        -- ej: "Rúbrica CAC Ensayo 2026"
  criterios       JSONB NOT NULL,       -- los 6 criterios con niveles
  escala_cac      JSONB NOT NULL,       -- tabla progresiva por grado
  creado_en       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 7. ENTREGAS ───────────────────────────────────────────
CREATE TABLE entregas (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tarea_id            UUID REFERENCES tareas(id),
  estudiante_id       UUID REFERENCES estudiantes(id),
  -- Datos del archivo en Drive
  drive_file_id       TEXT,             -- ID del archivo en Drive
  drive_file_name     TEXT,             -- nombre real del archivo subido
  drive_owner_email   TEXT,             -- correo del propietario en Drive
  drive_url           TEXT,
  fecha_subida        TIMESTAMPTZ,
  -- Estado de la entrega
  estado              TEXT CHECK (estado IN (
                        'pendiente',
                        'entregado',
                        'entregado_tarde',
                        'nombre_incorrecto'
                      )) DEFAULT 'pendiente',
  nombre_correcto     BOOLEAN,          -- cumple la convención de nombre
  -- Análisis de IA
  analisis_completado BOOLEAN DEFAULT FALSE,
  procesado_en        TIMESTAMPTZ,
  creado_en           TIMESTAMPTZ DEFAULT NOW()
);

-- ── 8. REPORTES DE ANÁLISIS ───────────────────────────────
CREATE TABLE reportes (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entrega_id          UUID REFERENCES entregas(id) UNIQUE,
  -- Detección de IA
  ia_detectada        BOOLEAN,
  ia_probabilidad     INT CHECK (ia_probabilidad BETWEEN 0 AND 100),
  ia_senales          JSONB,            -- señales específicas encontradas
  -- Evaluación rúbrica CAC
  criterio_tesis              TEXT CHECK (criterio_tesis IN ('bajo','basico','alto','superior')),
  criterio_argumentacion      TEXT CHECK (criterio_argumentacion IN ('bajo','basico','alto','superior')),
  criterio_contraargumentacion TEXT CHECK (criterio_contraargumentacion IN ('bajo','basico','alto','superior')),
  criterio_fuentes            TEXT CHECK (criterio_fuentes IN ('bajo','basico','alto','superior')),
  criterio_coherencia         TEXT CHECK (criterio_coherencia IN ('bajo','basico','alto','superior')),
  criterio_pensamiento        TEXT CHECK (criterio_pensamiento IN ('bajo','basico','alto','superior')),
  -- Verificación estructural
  tiene_portada_apa           BOOLEAN,
  tiene_epigrafe              BOOLEAN,
  tiene_cita_corta            BOOLEAN,
  tiene_cita_larga            BOOLEAN,
  tiene_contraargumentos      BOOLEAN,
  tiene_conclusion            BOOLEAN,
  tiene_referencias_apa       BOOLEAN,
  -- Escala CAC
  conteo_palabras             INT,
  conteo_parrafos             INT,
  cumple_escala_cac           BOOLEAN,
  escala_esperada_min         INT,
  escala_esperada_max         INT,
  -- Reporte narrativo
  resumen_docente             TEXT,     -- reporte completo para el docente
  justificacion_criterios     JSONB,    -- justificación por cada criterio
  recomendaciones             TEXT,     -- sugerencias de mejora
  -- Metadata
  modelo_ia_usado             TEXT DEFAULT 'claude-sonnet-4-20250514',
  tokens_usados               INT,
  generado_en                 TIMESTAMPTZ DEFAULT NOW()
);

-- ── 9. NOTIFICACIONES ─────────────────────────────────────
CREATE TABLE notificaciones (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id      UUID REFERENCES usuarios(id),
  tipo            TEXT,                 -- 'nueva_entrega', 'analisis_listo', 'ia_detectada'
  mensaje         TEXT,
  leida           BOOLEAN DEFAULT FALSE,
  referencia_id   UUID,                 -- ID de entrega o reporte relacionado
  creado_en       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 10. LOGS DEL BOT ──────────────────────────────────────
CREATE TABLE bot_logs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo        TEXT,                     -- 'scan_drive', 'analisis', 'error'
  curso_id    UUID REFERENCES cursos(id),
  detalle     JSONB,
  error       TEXT,
  creado_en   TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ÍNDICES
-- ============================================================
CREATE INDEX idx_entregas_tarea     ON entregas(tarea_id);
CREATE INDEX idx_entregas_estado    ON entregas(estado);
CREATE INDEX idx_reportes_entrega   ON reportes(entrega_id);
CREATE INDEX idx_estudiantes_curso  ON estudiantes(curso_id);
CREATE INDEX idx_tareas_curso       ON tareas(curso_id);
CREATE INDEX idx_notif_usuario      ON notificaciones(usuario_id, leida);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE instituciones  ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios       ENABLE ROW LEVEL SECURITY;
ALTER TABLE cursos         ENABLE ROW LEVEL SECURITY;
ALTER TABLE estudiantes    ENABLE ROW LEVEL SECURITY;
ALTER TABLE tareas         ENABLE ROW LEVEL SECURITY;
ALTER TABLE entregas       ENABLE ROW LEVEL SECURITY;
ALTER TABLE reportes       ENABLE ROW LEVEL SECURITY;
ALTER TABLE notificaciones ENABLE ROW LEVEL SECURITY;

-- Docente solo ve sus propios cursos
CREATE POLICY "docente_sus_cursos" ON cursos
  FOR ALL USING (docente_id = auth.uid());

-- Docente ve estudiantes de sus cursos
CREATE POLICY "docente_sus_estudiantes" ON estudiantes
  FOR ALL USING (
    curso_id IN (SELECT id FROM cursos WHERE docente_id = auth.uid())
  );

-- Docente ve entregas de sus tareas
CREATE POLICY "docente_sus_entregas" ON entregas
  FOR ALL USING (
    tarea_id IN (
      SELECT t.id FROM tareas t
      JOIN cursos c ON t.curso_id = c.id
      WHERE c.docente_id = auth.uid()
    )
  );

-- Docente ve reportes de sus entregas
CREATE POLICY "docente_sus_reportes" ON reportes
  FOR ALL USING (
    entrega_id IN (
      SELECT e.id FROM entregas e
      JOIN tareas t ON e.tarea_id = t.id
      JOIN cursos c ON t.curso_id = c.id
      WHERE c.docente_id = auth.uid()
    )
  );

-- Notificaciones propias
CREATE POLICY "usuario_sus_notificaciones" ON notificaciones
  FOR ALL USING (usuario_id = auth.uid());

-- ============================================================
-- DATOS INICIALES — Rúbrica CAC
-- ============================================================
INSERT INTO rubricas (nombre, criterios, escala_cac) VALUES (
  'Rúbrica CAC Ensayo Argumentativo 2026',
  '{
    "planteamiento_tesis": {
      "bajo":     "La tesis es vaga o no expresa postura clara.",
      "basico":   "La tesis es identificable pero general.",
      "alto":     "La tesis es clara y discutible.",
      "superior": "La tesis formula un problema complejo e integra conceptos teóricos."
    },
    "argumentacion_conceptual": {
      "bajo":     "Argumentos superficiales o descriptivos.",
      "basico":   "Argumentos con evidencia limitada.",
      "alto":     "Argumentos claros sustentados en evidencia.",
      "superior": "Argumentación sólida que articula teorías, conceptos y evidencias."
    },
    "contraargumentacion": {
      "bajo":     "No reconoce posturas contrarias.",
      "basico":   "Menciona objeciones de forma superficial.",
      "alto":     "Expone contraargumentos relevantes.",
      "superior": "Analiza críticamente objeciones complejas y defiende la tesis."
    },
    "uso_fuentes": {
      "bajo":     "Uso mínimo de fuentes o sin citación.",
      "basico":   "Uso limitado de fuentes con errores.",
      "alto":     "Uso correcto de fuentes académicas.",
      "superior": "Análisis crítico de fuentes primarias y secundarias."
    },
    "coherencia_estructura": {
      "bajo":     "Texto sin organización lógica.",
      "basico":   "Estructura básica con transiciones débiles.",
      "alto":     "Coherencia entre introducción, desarrollo y conclusión.",
      "superior": "Arquitectura argumentativa rigurosa con precisión gramatical y conectores lógicos."
    },
    "pensamiento_critico": {
      "bajo":     "Predomina la descripción.",
      "basico":   "Análisis limitado.",
      "alto":     "Relaciona conceptos y evidencia.",
      "superior": "Evalúa teorías y propone interpretación original."
    }
  }',
  '{
    "6":  {"tipo": "Descripción científica / observación", "parrafos_min": 1, "parrafos_max": 2, "palabras_min": 80,  "palabras_max": 150},
    "7":  {"tipo": "Explicación de fenómeno",              "parrafos_min": 2, "parrafos_max": 3, "palabras_min": 150, "palabras_max": 250},
    "8":  {"tipo": "Análisis simple de datos",             "parrafos_min": 3, "parrafos_max": 4, "palabras_min": 250, "palabras_max": 350},
    "9":  {"tipo": "Argumentación básica",                 "parrafos_min": 4, "parrafos_max": 5, "palabras_min": 350, "palabras_max": 500},
    "10": {"tipo": "Desarrollo teórico inicial",           "parrafos_min": 5, "parrafos_max": 7, "palabras_min": 500, "palabras_max": 700},
    "11": {"tipo": "Escritura académica investigativa",    "parrafos_min": 8, "parrafos_max": 12,"palabras_min": 800, "palabras_max": 1200}
  }'
);
