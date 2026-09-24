CREATE TABLE entidades (
	id INTEGER NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	nombre VARCHAR(80) NOT NULL, 
	apellido VARCHAR(80) NOT NULL, 
	cedula VARCHAR(20) NOT NULL, 
	telefono VARCHAR(20), 
	email VARCHAR(120), 
	posicion VARCHAR(80) NOT NULL, 
	posicion_id INTEGER, 
	nivel_certificacion_id INTEGER, 
	especialidad_zona_id INTEGER, 
	nivel VARCHAR(60), 
	fecha_nacimiento DATE, 
	fecha_ingreso DATE NOT NULL, 
	supervisor_id INTEGER, 
	meta_mensual_ventas NUMERIC(14, 2), 
	activo BOOLEAN NOT NULL, 
	atributos_extra JSON NOT NULL, genero VARCHAR(20), direccion VARCHAR(255), tipo VARCHAR(20) DEFAULT 'Interno', posee_vehiculo BOOLEAN DEFAULT 0, tipo_vehiculo VARCHAR(50), vehiculo_datos VARCHAR(150), fecha_vencimiento_aei DATE, empresa TEXT DEFAULT 'INDEPENDIENTE', tipo_persona VARCHAR(20) DEFAULT 'Física', aplica_itbis BOOLEAN DEFAULT 1, 
	PRIMARY KEY (id), 
	UNIQUE (codigo), 
	UNIQUE (cedula), 
	FOREIGN KEY(supervisor_id) REFERENCES entidades (id)
);

CREATE TABLE contrapartes (
	id INTEGER NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	rnc VARCHAR(20), 
	telefono VARCHAR(20), 
	contacto VARCHAR(100), 
	activo BOOLEAN NOT NULL, 
	atributos_extra JSON NOT NULL, direccion VARCHAR(255), provincia VARCHAR(100), sector VARCHAR(100), municipio VARCHAR(100), 
	PRIMARY KEY (id), 
	UNIQUE (nombre), 
	UNIQUE (rnc)
);

CREATE TABLE gastos (
	id INTEGER NOT NULL, 
	concepto VARCHAR(150) NOT NULL, 
	proveedor VARCHAR(100) NOT NULL, 
	monto NUMERIC(14, 2) NOT NULL, 
	fecha DATE NOT NULL, 
	estado VARCHAR(9) NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE incidentes (
	id INTEGER NOT NULL, 
	tipo VARCHAR(80) NOT NULL, 
	descripcion TEXT NOT NULL, 
	fecha_reporte DATE NOT NULL, 
	severidad VARCHAR(7) NOT NULL, 
	fecha_cierre DATE, nivel INTEGER DEFAULT 1, area_responsable VARCHAR(100), enlace_f05 VARCHAR(255), fecha_resolucion DATE, comentario_resolucion TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE kpi_config (
	id INTEGER NOT NULL, 
	kpi_id VARCHAR(50) NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	categoria VARCHAR(50) NOT NULL, 
	unidad VARCHAR(20) NOT NULL, 
	meta NUMERIC(12, 2) NOT NULL, 
	umbral_amarillo NUMERIC(12, 2) NOT NULL, 
	umbral_rojo NUMERIC(12, 2) NOT NULL, 
	mayor_es_mejor BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (kpi_id)
);

CREATE TABLE usuarios (
	id INTEGER NOT NULL, 
	username VARCHAR(50) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	rol VARCHAR(30) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	intentos_fallidos INTEGER NOT NULL DEFAULT 0, 
	bloqueado_hasta DATETIME, entidad_id INTEGER REFERENCES entidades(id), 
	debo_cambiar_password INTEGER DEFAULT 0, acepto_politicas INTEGER DEFAULT 0, 
	PRIMARY KEY (id), 
	UNIQUE (username)
);

CREATE TABLE proyectos (
	id INTEGER NOT NULL, 
	nombre VARCHAR(100) NOT NULL, 
	contraparte_id INTEGER NOT NULL, 
	compania_ejecutora VARCHAR(100), 
	etapa VARCHAR(50), 
	etapa_desarrollo_id INTEGER, 
	tipo_inmueble VARCHAR(40), 
	provincia VARCHAR(60), 
	municipio VARCHAR(80), 
	sector VARCHAR(100), 
	direccion VARCHAR(200), 
	amenidades JSON NOT NULL, 
	score_amenidades INTEGER, 
	fecha_entrega_estimada DATE, 
	unidades_totales INTEGER, 
	precio_min NUMERIC(14, 2), 
	precio_max NUMERIC(14, 2), 
	activo BOOLEAN NOT NULL, encargado_id INTEGER, financiamiento BOOLEAN DEFAULT 0, institucion_bancaria VARCHAR(100), fecha_captacion DATE, captador_id INTEGER, correos_ventas VARCHAR(255), forma_registro VARCHAR(100), 
	atributos_extra JSON DEFAULT '{}', descripcion TEXT, es_exclusivo BOOLEAN DEFAULT 1, 
	PRIMARY KEY (id), 
	UNIQUE (nombre), 
	FOREIGN KEY(contraparte_id) REFERENCES contrapartes (id)
);

CREATE TABLE auditoria (
	id INTEGER NOT NULL, 
	usuario_id INTEGER, 
	username_snapshot VARCHAR(50) NOT NULL, 
	accion VARCHAR(50) NOT NULL, 
	modulo VARCHAR(50) NOT NULL, 
	detalle VARCHAR(300), 
	fecha DATETIME NOT NULL, 
	ip_address VARCHAR(45), user_agent VARCHAR(255), request_path VARCHAR(500), hash_firma VARCHAR(64), 
	PRIMARY KEY (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);

CREATE TABLE campanas (
	id INTEGER NOT NULL, 
	nombre VARCHAR(150) NOT NULL, 
	canal VARCHAR(60) NOT NULL, 
	proyecto_id INTEGER, 
	fecha_inicio DATE NOT NULL, 
	fecha_fin DATE, 
	monto_invertido NUMERIC(12, 2) NOT NULL, 
	activo BOOLEAN NOT NULL, impresiones INTEGER DEFAULT 0, clics INTEGER DEFAULT 0, leads_generados INTEGER DEFAULT 0, alcance INTEGER DEFAULT 0, 
	PRIMARY KEY (id), 
	FOREIGN KEY(proyecto_id) REFERENCES proyectos (id)
);

CREATE TABLE compromisos (
	id INTEGER NOT NULL, 
	contraparte_id INTEGER NOT NULL, 
	proyecto_id INTEGER, 
	categoria VARCHAR(80), 
	fecha_inicio DATE NOT NULL, 
	fecha_vencimiento DATE NOT NULL, 
	valor_pactado_pct NUMERIC(5, 2) NOT NULL, 
	atributos_extra JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(contraparte_id) REFERENCES contrapartes (id), 
	FOREIGN KEY(proyecto_id) REFERENCES proyectos (id)
);

CREATE TABLE lead_preferencias (
	id INTEGER NOT NULL, 
	cliente_id INTEGER NOT NULL, 
	motivo_compra VARCHAR(50), 
	presupuesto_min NUMERIC(14, 2), 
	presupuesto_max NUMERIC(14, 2), 
	moneda_presupuesto VARCHAR(5) NOT NULL, 
	metodo_pago_preferido VARCHAR(40), 
	tamano_familia INTEGER, 
	habitaciones_min INTEGER, 
	zonas_interes JSON NOT NULL, 
	tiempo_mudanza VARCHAR(40), 
	amenidades_must_have JSON NOT NULL, 
	ocupacion VARCHAR(60), 
	rango_ingreso_mensual VARCHAR(40), 
	fecha_actualizacion DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (cliente_id), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id)
);

CREATE TABLE transacciones (
	id INTEGER NOT NULL, 
	codigo VARCHAR(50) NOT NULL, 
	proyecto_id INTEGER NOT NULL, 
	entidad_id INTEGER NOT NULL, 
	cliente_id INTEGER, 
	edificio VARCHAR(60), 
	piso VARCHAR(20), 
	unidad VARCHAR(30), 
	calle VARCHAR(120), 
	tipo_inmueble VARCHAR(40), 
	financiamiento BOOLEAN NOT NULL, 
	financiamiento_bancario INTEGER, 
	banco_financiador_id INTEGER, 
	institucion_bancaria VARCHAR(80), 
	kyc_completo BOOLEAN NOT NULL, 
	canal VARCHAR(7) NOT NULL, 
	tipo_canal_externo VARCHAR(14), 
	origen_prospecto VARCHAR(7), 
	categoria_asesor_congelada VARCHAR(60), 
	monto NUMERIC(14, 2) NOT NULL, 
	monto_separacion NUMERIC(14, 2) NOT NULL, 
	monto_inicial NUMERIC(14, 2) NOT NULL, 
	num_cuotas INTEGER NOT NULL, 
	pct_comision NUMERIC(5, 2) NOT NULL, 
	pct_retencion_empresa NUMERIC(5, 2), 
	fecha_evento DATE NOT NULL, 
	fecha_hito_intermedio DATE, 
	fecha_hito_final DATE, 
	dias_ciclo_cierre INTEGER, 
	sla_dias_meta INTEGER NOT NULL, 
	estado VARCHAR(10) NOT NULL, 
	motivo_perdida VARCHAR(60), 
	motivo_perdida_id INTEGER, 
	estado_plan_pagos VARCHAR(10) NOT NULL, 
	atributos_extra JSON NOT NULL, nivel_id INTEGER, captador_id INTEGER, gastos_pub_id INTEGER, pct_a REAL DEFAULT 0.0, pct_n REAL DEFAULT 0.0, pct_ase1 REAL DEFAULT 0.0, pct_ase2 REAL DEFAULT 0.0, pct_proyecto REAL DEFAULT 0.0, pct_admin REAL DEFAULT 0.0, pct_extra REAL DEFAULT 0.0, pct_pub_gfm REAL DEFAULT 0.0, comision_empresa_sin_itbis NUMERIC(14, 2) DEFAULT 0.0, itbis_comision_empresa NUMERIC(14, 2) DEFAULT 0.0, comision_vendedor_bruta NUMERIC(14, 2) DEFAULT 0.0, tipo_persona_vendedor VARCHAR(20), aplica_itbis_vendedor BOOLEAN, pct_isr NUMERIC(5, 2) DEFAULT 0.0, retencion_isr NUMERIC(14, 2) DEFAULT 0.0, itbis_vendedor NUMERIC(14, 2) DEFAULT 0.0, pct_itbis_retenido NUMERIC(5, 2) DEFAULT 0.0, retencion_itbis NUMERIC(14, 2) DEFAULT 0.0, total_retenciones NUMERIC(14, 2) DEFAULT 0.0, neto_pagado_vendedor NUMERIC(14, 2) DEFAULT 0.0, costo_total_vendedor NUMERIC(14, 2) DEFAULT 0.0, ganancia_empresa_sin_itbis NUMERIC(14, 2) DEFAULT 0.0, margen_empresa_neto NUMERIC(14, 2) DEFAULT 0.0, promocion VARCHAR(100), adicionales TEXT, moneda VARCHAR(5) DEFAULT 'USD', tiempo_entrega DATE, plan_pago_tipo VARCHAR(30), descuento_pct NUMERIC(5, 2) DEFAULT 0, comision_gerencia_total NUMERIC(14, 2) DEFAULT 0, comision_gerencia_pagada NUMERIC(14, 2) DEFAULT 0, comision_gerencia_saldo NUMERIC(14, 2) DEFAULT 0, gastos_legales NUMERIC(14, 2) DEFAULT 0, saldo_pendiente_comision NUMERIC(14, 2) DEFAULT 0, saldo_pagado_comision NUMERIC(14, 2) DEFAULT 0, dropbox_plan_pago TEXT, dropbox_reserva TEXT, dropbox_kyc TEXT, dropbox_contrato TEXT, dropbox_pago_inicial TEXT, nombre_propiedad VARCHAR(120), numero_inmueble VARCHAR(30), fecha_cierre DATE, comprobante_fiscal VARCHAR(14), ingreso_verificado BOOLEAN DEFAULT 0, 
	PRIMARY KEY (id), 
	UNIQUE (codigo), 
	FOREIGN KEY(proyecto_id) REFERENCES proyectos (id), 
	FOREIGN KEY(entidad_id) REFERENCES entidades (id), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id)
);

CREATE TABLE cobros (
	id INTEGER NOT NULL, 
	transaccion_id INTEGER NOT NULL, 
	tipo VARCHAR(10) NOT NULL, 
	numero_cuota INTEGER, 
	tramo_comision INTEGER, 
	concepto VARCHAR(120) NOT NULL, 
	origen VARCHAR(80), 
	monto_total NUMERIC(14, 2) NOT NULL, 
	fecha_generado DATE NOT NULL, 
	fecha_vencimiento DATE, 
	dias_mora_calculados INTEGER, 
	estado_aging_id INTEGER, 
	metodo_pago_ultimo_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(transaccion_id) REFERENCES transacciones (id)
);

CREATE TABLE pagos (
	id INTEGER NOT NULL, 
	cobro_id INTEGER NOT NULL, 
	monto NUMERIC(14, 2) NOT NULL, 
	fecha_pago DATE NOT NULL, 
	metodo VARCHAR(50), 
	referencia VARCHAR(150), 
	registrado_en DATETIME NOT NULL, enlace_dropbox TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cobro_id) REFERENCES cobros (id)
);

CREATE TABLE google_oauth_tokens (
	id INTEGER NOT NULL, 
	email VARCHAR(120), 
	access_token TEXT, 
	refresh_token TEXT, 
	token_uri VARCHAR(255), 
	client_id VARCHAR(255), 
	client_secret VARCHAR(255), 
	scopes TEXT, 
	expires_at DATETIME, 
	conectado BOOLEAN NOT NULL, 
	fecha_conexion DATETIME, 
	PRIMARY KEY (id)
);

CREATE TABLE configuracion_sistema (
	id INTEGER NOT NULL, 
	frecuencia_postventa VARCHAR(9) NOT NULL, 
	antelacion_postventa_dias INTEGER NOT NULL, 
	dias_contacto_lead INTEGER NOT NULL, 
	antelacion_cobro_dias INTEGER NOT NULL, 
	calendar_id VARCHAR(255) NOT NULL, 
	timezone VARCHAR(80) NOT NULL, 
	fecha_actualizacion DATETIME NOT NULL, google_client_id TEXT, google_client_secret TEXT, google_redirect_uri TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE cat_niveles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        );


CREATE TABLE cat_captadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        );

CREATE TABLE cat_gastos_pub (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        );

CREATE TABLE config_matriz_comisiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nivel_id INTEGER,
            captador_id INTEGER,
            gastos_pub_id INTEGER,
            pct_a REAL DEFAULT 0.0,
            pct_n REAL DEFAULT 0.0,
            pct_ase1 REAL DEFAULT 0.0,
            pct_ase2 REAL DEFAULT 0.0,
            pct_proyecto REAL DEFAULT 0.0,
            pct_admin REAL DEFAULT 0.0,
            pct_extra REAL DEFAULT 0.0,
            pct_pub_gfm REAL DEFAULT 0.0,
            FOREIGN KEY(nivel_id) REFERENCES cat_niveles(id),
            FOREIGN KEY(captador_id) REFERENCES cat_captadores(id),
            FOREIGN KEY(gastos_pub_id) REFERENCES cat_gastos_pub(id),
            UNIQUE(nivel_id, captador_id, gastos_pub_id)
        );

CREATE TABLE app_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT UNIQUE NOT NULL,
    valor TEXT
);

CREATE TABLE "clientes" (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	nombre VARCHAR(80) NOT NULL, 
	apellido VARCHAR(80) NOT NULL, 
	genero VARCHAR(20), 
	genero_id INTEGER, 
	fecha_nacimiento DATE, 
	nacionalidad VARCHAR(60), 
	estado_civil VARCHAR(30), 
	estado_civil_id INTEGER, 
	ocupacion_sector_id INTEGER, 
	rango_ingreso_mensual_usd INTEGER, 
	pais VARCHAR(60), 
	provincia VARCHAR(60), 
	municipio VARCHAR(80), 
	direccion VARCHAR(200), 
	motivo_compra_id INTEGER, 
	presupuesto_max_usd INTEGER, 
	metodo_pago_pref_id INTEGER, 
	habitaciones_min INTEGER, 
	canal_captacion_id INTEGER, 
	via_referida VARCHAR(80), 
	campana_id INTEGER, 
	referido_por_cliente_id INTEGER, 
	vendedor_captador_id INTEGER, 
	fecha_captacion DATE, 
	etapa_embudo VARCHAR(11) NOT NULL, 
	activo BOOLEAN NOT NULL DEFAULT 1, proyecto_interes_id INTEGER REFERENCES proyectos(id), cedula VARCHAR(20), telefono VARCHAR(20), telefono_residencial VARCHAR(20), email VARCHAR(120), presupuesto_rango VARCHAR(60), sector VARCHAR(80), institucion_bancaria VARCHAR(80),
	FOREIGN KEY(campana_id) REFERENCES campanas (id), 
	FOREIGN KEY(referido_por_cliente_id) REFERENCES clientes (id), 
	FOREIGN KEY(vendedor_captador_id) REFERENCES entidades (id)
);

CREATE TABLE compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concepto VARCHAR(255) NOT NULL,
    monto_total NUMERIC(14,2) NOT NULL,
    fecha_solicitud DATE NOT NULL,
    aprobado_ceo BOOLEAN DEFAULT 0,
    fecha_aprobacion DATE,
    sla_dias_aprobacion INTEGER,
    enlace_dropbox VARCHAR(255) NOT NULL,
    numero_registro_erp VARCHAR(50),
    f03_completado BOOLEAN DEFAULT 0,
    estado VARCHAR(20) DEFAULT 'pendiente'
, proveedor_id INTEGER REFERENCES proveedores(id));

CREATE TABLE compras_pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id INTEGER NOT NULL,
    monto_pagado NUMERIC(14,2) NOT NULL,
    fecha_pago DATE NOT NULL DEFAULT CURRENT_DATE,
    referencia VARCHAR(150),
    FOREIGN KEY(compra_id) REFERENCES compras(id)
);

CREATE TABLE comisiones_pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entidad_id INTEGER NOT NULL,
    transaccion_id INTEGER NOT NULL,
    monto NUMERIC(14,2) NOT NULL,
    fecha_generacion DATE NOT NULL,
    fecha_maxima_pago DATE NOT NULL,
    fecha_aprobacion_ceo DATE,
    fecha_pago DATE,
    estado VARCHAR(20) DEFAULT 'pendiente',
    hito INTEGER DEFAULT 1,
    FOREIGN KEY(entidad_id) REFERENCES entidades(id),
    FOREIGN KEY(transaccion_id) REFERENCES transacciones(id)
);

CREATE TABLE proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        razon_social VARCHAR(255) NOT NULL,
        ruc VARCHAR(50),
        email VARCHAR(100),
        telefono VARCHAR(50),
        direccion TEXT,
        estado VARCHAR(20) DEFAULT 'activo',
        fecha_registro DATE DEFAULT CURRENT_DATE
    , descripcion TEXT);

CREATE TABLE compras_facturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        compra_id INTEGER NOT NULL REFERENCES compras(id),
        proveedor_id INTEGER NOT NULL REFERENCES proveedores(id),
        numero_factura VARCHAR(100),
        monto_factura NUMERIC(14,2),
        ruta_archivo_pdf VARCHAR(255) NOT NULL,
        fecha_subida DATETIME DEFAULT CURRENT_TIMESTAMP
    );