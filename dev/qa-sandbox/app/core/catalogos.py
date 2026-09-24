"""
catalogos.py — Listas fijas para selectboxes: geografía RD, catálogos de negocio y embudo comercial.
"""

PAISES = [
    "República Dominicana", "Estados Unidos", "España", "Puerto Rico",
    "Panamá", "Inglaterra", "Holanda", "Italia", "Francia", "Canadá",
    "Venezuela", "Colombia", "México", "Suiza", "Alemania",
    "Guatemala", "Chile", "Ecuador", "Perú",
    "Otro",
]

PROVINCIAS_RD = [
    "Distrito Nacional", "Azua", "Bahoruco", "Barahona", "Dajabón", "Duarte",
    "Elías Piña", "El Seibo", "Espaillat", "Hato Mayor", "Hermanas Mirabal",
    "Independencia", "La Altagracia", "La Romana", "La Vega",
    "María Trinidad Sánchez", "Monseñor Nouel", "Monte Cristi", "Monte Plata",
    "Pedernales", "Peravia", "Puerto Plata", "Samaná", "San Cristóbal",
    "San José de Ocoa", "San Juan", "San Pedro de Macorís", "Sánchez Ramírez",
    "Santiago", "Santiago Rodríguez", "Santo Domingo", "Valverde",
]

MUNICIPIOS_POR_PROVINCIA = {
    "Distrito Nacional": ["Santo Domingo de Guzmán"],
    "Santo Domingo": [
        "Santo Domingo Este", "Santo Domingo Oeste", "Santo Domingo Norte",
        "Boca Chica", "San Antonio de Guzmán", "Los Alcarrizos", "Pedro Brand", "Villa Altagracia",
    ],
    "Azua": ["Azua de Compostela", "Estebanía", "Guayabal", "Las Charcas", "Las Yayas de Viajama", "Padre Las Casas", "Peralta", "Pueblo Viejo", "Sabana Yegua", "Tábara Arriba"],
    "Bahoruco": ["Neiba", "Galván", "Los Ríos", "Tamayo", "Villa Jaragua"],
    "Barahona": ["Barahona", "Cabral", "Enriquillo", "Fundación", "Jaquimeyes", "La Ciénaga", "Las Salinas", "Paraíso", "Polo", "Vicente Noble"],
    "Dajabón": ["Dajabón", "El Pino", "Loma de Cabrera", "Partido", "Restauración"],
    "Duarte": ["San Francisco de Macorís", "Arenoso", "Castillo", "Eugenio María de Hostos", "Las Guáranas", "Pimentel", "Villa Riva"],
    "Elías Piña": ["Comendador", "Bánica", "El Llano", "Hondo Valle", "Juan Santiago", "Pedro Santana"],
    "El Seibo": ["El Seibo", "Miches"],
    "Espaillat": ["Moca", "Cayetano Germosén", "Gaspar Hernández", "Jamao al Norte"],
    "Hato Mayor": ["Hato Mayor", "El Valle", "Sabana de la Mar"],
    "Hermanas Mirabal": ["Salcedo", "Tenares", "Villa Tapia"],
    "Independencia": ["Jimaní", "Cristóbal", "Duvergé", "La Descubierta", "Mella", "Postrer Río"],
    "La Altagracia": ["Higüey", "San Rafael del Yuma"],
    "La Romana": ["La Romana", "Guaymate", "Villa Hermosa"],
    "La Vega": ["La Vega", "Constanza", "Jarabacoa", "Jima Abajo"],
    "María Trinidad Sánchez": ["Nagua", "Cabrera", "El Factor", "Río San Juan"],
    "Monseñor Nouel": ["Bonao", "Maimón", "Piedra Blanca"],
    "Monte Cristi": ["Monte Cristi", "Castañuelas", "Guayubín", "Las Matas de Santa Cruz", "Pepillo Salcedo", "Villa Vásquez"],
    "Monte Plata": ["Monte Plata", "Bayaguana", "Peralvillo", "Sabana Grande de Boyá", "Yamasá"],
    "Pedernales": ["Pedernales", "Oviedo"],
    "Peravia": ["Baní", "Nizao"],
    "Puerto Plata": ["Puerto Plata", "Altamira", "Guananico", "Imbert", "Los Hidalgos", "Luperón", "Sosúa", "Villa Isabela", "Villa Montellano"],
    "Samaná": ["Samaná", "Las Terrenas", "Sánchez"],
    "San Cristóbal": ["San Cristóbal", "Bajos de Haina", "Cambita Garabitos", "Los Cacaos", "Sabana Grande de Palenque", "San Gregorio de Nigua", "Yaguate"],
    "San José de Ocoa": ["San José de Ocoa", "Rancho Arriba", "Sabana Larga"],
    "San Juan": ["San Juan de la Maguana", "Bohechío", "El Cercado", "Juan de Herrera", "Las Matas de Farfán", "Vallejuelo"],
    "San Pedro de Macorís": ["San Pedro de Macorís", "Consuelo", "Guayacanes", "Quisqueya", "Ramón Santana", "San José de Los Llanos"],
    "Sánchez Ramírez": ["Cotuí", "Cevicos", "Fantino", "La Mata"],
    "Santiago": ["Santiago de los Caballeros", "Bisonó", "Jánico", "Licey al Medio", "Puñal", "Sabana Iglesia", "San José de las Matas", "Tamboril", "Villa González"],
    "Santiago Rodríguez": ["Sabaneta", "Monción", "Villa Los Almácigos"],
    "Valverde": ["Mao", "Esperanza", "Laguna Salada"],
}

TIPOS_INMUEBLE = [
    "Apartamento", "Casa", "Solar", "Villa", "Local Comercial", "Penthouse",
    "Edificio", "Hotel", "Nave Industrial", "Loft", "Townhouse",
    "Mixto", "Otro",
]

GENEROS = ["Masculino", "Femenino"]

ESTADOS_CIVILES = ["Soltero/a", "Casado/a", "Unión Libre", "Divorciado/a", "Viudo/a"]

VIAS_REFERIDAS = [
    "Publicidad", "Referencia", "Familiar", "Google", "Facebook",
    "Revista", "Volante", "Periódico", "Página Gratis", "Cliente Existente", "Otro",
]

NIVELES_ASESOR = ["Asesor Inmobiliario", "Asesor Junior", "Asesor Senior", "Asesor Senior con Equipo"]

INSTITUCIONES_BANCARIAS = [
    "Banreservas", "Scotia Bank", "Banco Popular",
    "Asociación Nacional de Ahorros y Préstamos",
    "Asociación Popular de Ahorros y Préstamos", "Otro",
]

CANALES_MARKETING = [
    "Instagram Ads", "Facebook Ads", "Google Ads", "Portal Inmobiliario",
    "Influencer / Referido Pagado", "Volantes / Impreso", "Radio/TV", "Otro",
]

ETAPAS_EMBUDO = ["Nuevo", "Contactado", "Calificado", "Negociación", "Cliente", "Perdido"]
MOTIVOS_COMPRA = ["Vivienda Principal", "Inversión", "Segunda Vivienda", "Vacacional", "Otro"]
METODOS_PAGO_PREFERIDO = ["Fondos Propios", "Financiamiento Bancario", "Mixto"]
TIEMPOS_MUDANZA = ["Inmediato (0-3 meses)", "3-6 meses", "6-12 meses", "+12 meses / Planos"]

AMENIDADES_DISPONIBLES = [
    "Piscina", "Gimnasio", "Seguridad 24h", "Ascensor", "Parqueo Techado",
    "Mascotas", "Área Social", "Balcón/Terraza", "Área Niños", "Cancha Deportiva",
    "Terraza Compartida", "Terraza Exclusiva", "Línea Blanca",
]

MONEDAS = ["RD$", "US$", "MX$", "COL$", "₡", "Q", "S/"]

OCUPACIONES = [
    "Asalariado Sector Privado", "Asalariado Sector Público",
    "Independiente/Profesional Liberal", "Empresario/Dueño de Negocio",
    "Remesas del Exterior", "Jubilado/Pensionado", "Otro",
]

RANGOS_INGRESO_MENSUAL = [
    "Menos de RD$50,000", "RD$50,000 - RD$100,000", "RD$100,000 - RD$200,000",
    "RD$200,000 - RD$400,000", "Más de RD$400,000", "Prefiere no decir",
]
