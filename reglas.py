"""Reglas de negocio: horarios, cruces de reservas, tarifas y disponibilidad."""
from datetime import date, datetime, timedelta

from db import get_db

HORA_APERTURA = "06:00"
HORA_CIERRE = "22:00"
HORAS_DIA = 16
ESTADOS_ESPACIO = ["disponible", "reservado", "ocupado", "fuera_de_servicio"]


def a_minutos(hora):
    horas, minutos = hora.split(":")
    return int(horas) * 60 + int(minutos)


def calcular_valor(valor_hora, hora_inicio, hora_fin):
    """R. 6-3: valor del servicio según la tarifa y el tiempo reservado."""
    minutos = a_minutos(hora_fin) - a_minutos(hora_inicio)
    return int(round(valor_hora * minutos / 60))


def validar_horario(fecha, hora_inicio, hora_fin):
    """Devuelve un mensaje de error o None si el horario es válido."""
    try:
        dia = datetime.strptime(fecha, "%Y-%m-%d").date()
        a_minutos(hora_inicio)
        a_minutos(hora_fin)
    except (ValueError, AttributeError):
        return "Debes indicar una fecha y unas horas válidas."
    if dia < date.today():
        return "La fecha de la reserva no puede ser anterior a hoy."
    if hora_inicio >= hora_fin:
        return "La hora de fin debe ser posterior a la hora de inicio."
    if hora_inicio < HORA_APERTURA or hora_fin > HORA_CIERRE:
        return f"El parqueadero atiende de {HORA_APERTURA} a {HORA_CIERRE}."
    if dia == date.today() and hora_inicio < datetime.now().strftime("%H:%M"):
        return "La hora de inicio ya pasó."
    return None


def validar_consulta(fecha, desde, hasta):
    """Devuelve True si la fecha o las horas de una consulta de disponibilidad no son válidas."""
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
        return a_minutos(desde) >= a_minutos(hasta)
    except (ValueError, AttributeError):
        return True


def hay_cruce(id_espacio, fecha, hora_inicio, hora_fin, excluir=None):
    """R. 5-6: verifica si el espacio ya está reservado en ese horario."""
    consulta = (
        "SELECT 1 FROM reserva WHERE id_espacio = ? AND fecha = ? AND estado = 'activa'"
        " AND hora_inicio < ? AND hora_fin > ?"
    )
    parametros = [id_espacio, fecha, hora_fin, hora_inicio]
    if excluir is not None:
        consulta += " AND id_reserva != ?"
        parametros.append(excluir)
    return get_db().execute(consulta, parametros).fetchone() is not None


def buscar_tarifa(tipo_vehiculo, tipo_vinculacion):
    return get_db().execute(
        "SELECT * FROM tarifa WHERE tipo_vehiculo = ? AND tipo_vinculacion = ? AND vigente = 1"
        " ORDER BY id_tarifa DESC LIMIT 1",
        (tipo_vehiculo, tipo_vinculacion),
    ).fetchone()


def ventana_por_defecto():
    """Fecha y horas de consulta cuando el usuario no las indica: desde ahora, una hora."""
    ahora = datetime.now()
    fin = min(ahora + timedelta(hours=1), ahora.replace(hour=23, minute=59))
    return ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M"), fin.strftime("%H:%M")


def listar_espacios(zona="", tipo_vehiculo="", estado="", fecha=None, desde=None, hasta=None):
    """R. 4-1, 4-2 y 4-4: espacios con su estado en la fecha y horas consultadas, filtrables."""
    fecha_ref, desde_ref, hasta_ref = ventana_por_defecto()
    fecha, desde, hasta = fecha or fecha_ref, desde or desde_ref, hasta or hasta_ref
    reservados = {
        fila["id_espacio"]: f"{fila['hora_inicio']} a {fila['hora_fin']}"
        for fila in get_db().execute(
            "SELECT id_espacio, hora_inicio, hora_fin FROM reserva WHERE estado = 'activa' AND fecha = ?"
            " AND hora_inicio < ? AND hora_fin > ? ORDER BY hora_inicio DESC",
            (fecha, hasta, desde),
        )
    }
    resultado = []
    for espacio in get_db().execute("SELECT * FROM espacio ORDER BY zona, codigo"):
        actual = espacio["estado"]
        if actual == "disponible" and espacio["id_espacio"] in reservados:
            actual = "reservado"
        if zona and espacio["zona"] != zona:
            continue
        if tipo_vehiculo and espacio["tipo_vehiculo"] != tipo_vehiculo:
            continue
        if estado and actual != estado:
            continue
        resultado.append({**dict(espacio), "estado_actual": actual,
                          "horario_reservado": reservados.get(espacio["id_espacio"], "")})
    return resultado


def tiene_reservas_activas(id_espacio):
    return get_db().execute(
        "SELECT 1 FROM reserva WHERE id_espacio = ? AND estado = 'activa'", (id_espacio,)
    ).fetchone() is not None


def pago_aprobado(id_reserva):
    return get_db().execute(
        "SELECT 1 FROM pago WHERE id_reserva = ? AND estado = 'pagado'", (id_reserva,)
    ).fetchone() is not None


def generar_reporte(desde, hasta):
    """R. 8: consolida reservas, espacios y pagos para los reportes."""
    conexion = get_db()
    dias = (datetime.strptime(hasta, "%Y-%m-%d") - datetime.strptime(desde, "%Y-%m-%d")).days + 1
    reservas = conexion.execute(
        "SELECT r.*, e.zona FROM reserva r JOIN espacio e ON e.id_espacio = r.id_espacio"
        " WHERE r.estado != 'cancelada' AND r.fecha BETWEEN ? AND ?",
        (desde, hasta),
    ).fetchall()
    if not reservas:
        return None
    zonas = {}
    for fila in conexion.execute("SELECT zona, COUNT(*) AS total FROM espacio GROUP BY zona"):
        zonas[fila["zona"]] = {"espacios": fila["total"], "horas": 0.0}
    franjas = {"06:00-10:00": 0, "10:00-14:00": 0, "14:00-18:00": 0, "18:00-22:00": 0}
    for reserva in reservas:
        duracion = (a_minutos(reserva["hora_fin"]) - a_minutos(reserva["hora_inicio"])) / 60
        zonas[reserva["zona"]]["horas"] += duracion
        inicio = a_minutos(reserva["hora_inicio"]) // 60
        clave = list(franjas)[min(max((inicio - 6) // 4, 0), 3)]
        franjas[clave] += 1
    ocupacion = {
        zona: round(100 * datos["horas"] / (datos["espacios"] * dias * HORAS_DIA), 1)
        for zona, datos in zonas.items()
    }
    ingresos = conexion.execute(
        "SELECT COALESCE(SUM(p.monto), 0) FROM pago p JOIN reserva r ON r.id_reserva = p.id_reserva"
        " WHERE p.estado = 'pagado' AND r.estado != 'cancelada' AND r.fecha BETWEEN ? AND ?",
        (desde, hasta),
    ).fetchone()[0]
    return {"total_reservas": len(reservas), "ocupacion": ocupacion, "franjas": franjas, "ingresos": ingresos}
