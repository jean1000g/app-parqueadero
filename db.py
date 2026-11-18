"""Acceso a la base de datos SQLite del Sistema Inteligente de Gestión de Parqueaderos."""
import sqlite3
from datetime import datetime

from flask import current_app, g
from werkzeug.security import generate_password_hash

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    documento TEXT NOT NULL UNIQUE,
    correo TEXT NOT NULL UNIQUE,
    contrasena_hash TEXT NOT NULL,
    tipo_vinculacion TEXT NOT NULL,
    placa_vehiculo TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'usuario'
);
CREATE TABLE IF NOT EXISTS espacio (
    id_espacio INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    zona TEXT NOT NULL,
    tipo_vehiculo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'disponible'
);
CREATE TABLE IF NOT EXISTS tarifa (
    id_tarifa INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_vehiculo TEXT NOT NULL,
    tipo_vinculacion TEXT NOT NULL,
    valor_hora INTEGER NOT NULL,
    vigente INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS reserva (
    id_reserva INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL REFERENCES usuario(id_usuario),
    id_espacio INTEGER NOT NULL REFERENCES espacio(id_espacio),
    id_tarifa INTEGER NOT NULL REFERENCES tarifa(id_tarifa),
    fecha TEXT NOT NULL,
    hora_inicio TEXT NOT NULL,
    hora_fin TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activa',
    codigo_confirmacion TEXT NOT NULL,
    valor_total INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pago (
    id_pago INTEGER PRIMARY KEY AUTOINCREMENT,
    id_reserva INTEGER NOT NULL REFERENCES reserva(id_reserva),
    monto INTEGER NOT NULL,
    estado TEXT NOT NULL,
    fecha_pago TEXT NOT NULL,
    comprobante TEXT NOT NULL
);
"""

TIPOS_VEHICULO = ["carro", "moto"]
TIPOS_VINCULACION = ["estudiante", "docente", "trabajador", "visitante"]
VALORES_BASE = {"carro": 3000, "moto": 1500}
DESCUENTO = {"estudiante": 0.8, "docente": 0.9, "trabajador": 0.9, "visitante": 1.0}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    conexion = g.pop("db", None)
    if conexion is not None:
        conexion.close()


def init_db():
    """Crea las tablas y, si la base está vacía, carga los datos iniciales."""
    conexion = get_db()
    conexion.executescript(ESQUEMA)
    if conexion.execute("SELECT COUNT(*) FROM usuario").fetchone()[0] == 0:
        conexion.execute(
            "INSERT INTO usuario (nombre, documento, correo, contrasena_hash, tipo_vinculacion, placa_vehiculo, rol)"
            " VALUES (?, ?, ?, ?, ?, ?, 'administrador')",
            ("Administrador", "0000", "admin@universidad.edu", generate_password_hash("Admin123"),
             "trabajador", "ADM000"),
        )
        for zona, tipo, cantidad in (("A", "carro", 6), ("B", "carro", 6), ("C", "moto", 4)):
            for numero in range(1, cantidad + 1):
                conexion.execute(
                    "INSERT INTO espacio (codigo, zona, tipo_vehiculo) VALUES (?, ?, ?)",
                    (f"{zona}-{numero:02d}", zona, tipo),
                )
        for tipo in TIPOS_VEHICULO:
            for vinculacion in TIPOS_VINCULACION:
                valor = int(VALORES_BASE[tipo] * DESCUENTO[vinculacion])
                conexion.execute(
                    "INSERT INTO tarifa (tipo_vehiculo, tipo_vinculacion, valor_hora) VALUES (?, ?, ?)",
                    (tipo, vinculacion, valor),
                )
        conexion.commit()


def finalizar_reservas_vencidas():
    """R. 4-5: las reservas cuyo horario ya pasó se marcan como finalizadas."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    conexion = get_db()
    conexion.execute(
        "UPDATE reserva SET estado = 'finalizada'"
        " WHERE estado = 'activa' AND (fecha || ' ' || hora_fin) <= ?",
        (ahora,),
    )
    conexion.commit()
