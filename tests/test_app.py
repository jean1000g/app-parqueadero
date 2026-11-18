"""Pruebas automáticas por característica (R. 1 a R. 8)."""
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import create_app  # noqa: E402

MANANA = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
PASADO = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")


@pytest.fixture()
def cliente(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "prueba.db"), "TESTING": True})
    return app.test_client()


def registrar(cliente, correo="ana@uni.edu", documento="1001", vinculacion="estudiante"):
    return cliente.post("/registro", data={
        "nombre": "Ana Pérez", "documento": documento, "correo": correo, "tipo_vinculacion": vinculacion,
        "placa_vehiculo": "abc123", "contrasena": "secreto1"}, follow_redirects=True)


def entrar(cliente, correo="ana@uni.edu", clave="secreto1"):
    return cliente.post("/login", data={"correo": correo, "contrasena": clave}, follow_redirects=True)


def entrar_admin(cliente):
    return entrar(cliente, "admin@universidad.edu", "Admin123")


def reservar(cliente, id_espacio=1, fecha=MANANA, inicio="08:00", fin="10:00"):
    return cliente.post(f"/reservar/{id_espacio}", data={
        "fecha": fecha, "hora_inicio": inicio, "hora_fin": fin}, follow_redirects=True)


# ---- R. 1: registro y autenticación
def test_registro_exitoso(cliente):
    assert "Registro exitoso" in registrar(cliente).get_data(as_text=True)


def test_registro_duplicado(cliente):
    registrar(cliente)
    assert "Ya existe un usuario" in registrar(cliente).get_data(as_text=True)


def test_registro_correo_invalido(cliente):
    assert "formato válido" in registrar(cliente, correo="no-es-correo").get_data(as_text=True)


def test_login_correcto_e_incorrecto(cliente):
    registrar(cliente)
    assert "Inicio de sesión exitoso" in entrar(cliente).get_data(as_text=True)
    cliente.get("/logout")
    assert "incorrectos" in entrar(cliente, clave="mala").get_data(as_text=True)


def test_cerrar_sesion(cliente):
    registrar(cliente)
    entrar(cliente)
    assert "Sesión cerrada" in cliente.get("/logout", follow_redirects=True).get_data(as_text=True)


def test_restablecer_contrasena(cliente):
    registrar(cliente)
    cliente.post("/recuperar", data={"correo": "ana@uni.edu", "documento": "1001", "contrasena": "nueva123"})
    assert "Inicio de sesión exitoso" in entrar(cliente, clave="nueva123").get_data(as_text=True)


def test_usuario_no_entra_al_panel_admin(cliente):
    registrar(cliente)
    entrar(cliente)
    assert "Solo el administrador" in cliente.get("/admin", follow_redirects=True).get_data(as_text=True)


def test_ruta_protegida_sin_sesion(cliente):
    assert "Inicia sesión" in cliente.get("/disponibilidad", follow_redirects=True).get_data(as_text=True)


# ---- R. 2: usuarios
def test_usuario_modifica_su_perfil(cliente):
    registrar(cliente)
    entrar(cliente)
    respuesta = cliente.post("/perfil", data={
        "nombre": "Ana María", "documento": "1001", "correo": "ana@uni.edu", "tipo_vinculacion": "docente",
        "placa_vehiculo": "xyz789"}, follow_redirects=True)
    assert "Datos actualizados" in respuesta.get_data(as_text=True)
    assert "XYZ789" in cliente.get("/perfil").get_data(as_text=True)


def test_admin_modifica_y_elimina_usuarios(cliente):
    registrar(cliente)
    entrar_admin(cliente)
    assert "Ana" in cliente.get("/admin/usuarios").get_data(as_text=True)
    cambio = cliente.post("/admin/usuarios/2/editar", data={
        "nombre": "Ana Editada", "documento": "1001", "correo": "ana@uni.edu", "tipo_vinculacion": "docente",
        "placa_vehiculo": "ABC123", "rol": "usuario"}, follow_redirects=True)
    assert "Usuario actualizado" in cambio.get_data(as_text=True)
    assert "Usuario eliminado" in cliente.post("/admin/usuarios/2/eliminar", follow_redirects=True).get_data(as_text=True)


def test_no_elimina_usuario_con_reservas(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    cliente.get("/logout")
    entrar_admin(cliente)
    assert "tiene reservas" in cliente.post("/admin/usuarios/2/eliminar", follow_redirects=True).get_data(as_text=True)


# ---- R. 3: espacios
def test_admin_registra_espacio(cliente):
    entrar_admin(cliente)
    respuesta = cliente.post("/admin/espacios", data={"codigo": "d-01", "zona": "d", "tipo_vehiculo": "carro"})
    assert "D-01" in respuesta.get_data(as_text=True)


def test_espacio_duplicado(cliente):
    entrar_admin(cliente)
    cliente.post("/admin/espacios", data={"codigo": "Z-01", "zona": "Z", "tipo_vehiculo": "carro"})
    respuesta = cliente.post("/admin/espacios", data={"codigo": "Z-01", "zona": "Z", "tipo_vehiculo": "carro"})
    assert "Ya existe un espacio" in respuesta.get_data(as_text=True)


def test_admin_actualiza_estado_de_espacio(cliente):
    entrar_admin(cliente)
    respuesta = cliente.post("/admin/espacios/1/editar", data={
        "zona": "A", "tipo_vehiculo": "carro", "estado": "fuera_de_servicio"}, follow_redirects=True)
    assert "Espacio actualizado" in respuesta.get_data(as_text=True)


def test_no_elimina_espacio_con_reservas_activas(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    cliente.get("/logout")
    entrar_admin(cliente)
    assert "reservas activas" in cliente.post("/admin/espacios/1/eliminar", follow_redirects=True).get_data(as_text=True)


def test_elimina_espacio_sin_reservas(cliente):
    entrar_admin(cliente)
    assert "Espacio eliminado" in cliente.post("/admin/espacios/1/eliminar", follow_redirects=True).get_data(as_text=True)


# ---- R. 4: disponibilidad
def test_disponibilidad_con_filtros(cliente):
    registrar(cliente)
    entrar(cliente)
    pagina = cliente.get("/disponibilidad?zona=C&tipo_vehiculo=moto").get_data(as_text=True)
    assert "C-01" in pagina and "A-01" not in pagina


def test_informacion_muestra_tarifas_y_horario(cliente):
    registrar(cliente)
    entrar(cliente)
    pagina = cliente.get("/informacion").get_data(as_text=True)
    assert "06:00" in pagina and "COP" in pagina


# ---- R. 5 y R. 6: reservas y tarifas
def test_reserva_exitosa_calcula_valor(cliente):
    registrar(cliente)
    entrar(cliente)
    pagina = reservar(cliente, inicio="08:00", fin="10:00").get_data(as_text=True)
    assert "RES-" in pagina
    assert "$4.800 COP" in pagina  # carro estudiante: 2.400/h x 2 h


def test_valor_proporcional_a_los_minutos(cliente):
    registrar(cliente)
    entrar(cliente)
    assert "$1.200 COP" in reservar(cliente, inicio="08:00", fin="08:30").get_data(as_text=True)


def test_no_permite_reservas_cruzadas(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente, inicio="08:00", fin="10:00")
    assert "ya está reservado" in reservar(cliente, inicio="09:00", fin="11:00").get_data(as_text=True)


def test_horarios_consecutivos_no_se_cruzan(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente, inicio="08:00", fin="10:00")
    assert "RES-" in reservar(cliente, inicio="10:00", fin="11:00").get_data(as_text=True)


def test_rechaza_fecha_pasada(cliente):
    registrar(cliente)
    entrar(cliente)
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert "anterior a hoy" in reservar(cliente, fecha=ayer).get_data(as_text=True)


def test_rechaza_horas_invertidas_y_fuera_de_horario(cliente):
    registrar(cliente)
    entrar(cliente)
    assert "posterior" in reservar(cliente, inicio="10:00", fin="09:00").get_data(as_text=True)
    assert "atiende de" in reservar(cliente, inicio="05:00", fin="07:00").get_data(as_text=True)


def test_rechaza_espacio_fuera_de_servicio(cliente):
    entrar_admin(cliente)
    cliente.post("/admin/espacios/1/editar", data={"zona": "A", "tipo_vehiculo": "carro", "estado": "fuera_de_servicio"})
    cliente.get("/logout")
    registrar(cliente)
    entrar(cliente)
    assert "fuera de servicio" in reservar(cliente).get_data(as_text=True)


def test_cancelar_reserva(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    assert "cancelada correctamente" in cliente.post("/reservas/1/cancelar", follow_redirects=True).get_data(as_text=True)
    assert "RES-" in cliente.get("/mis-reservas").get_data(as_text=True)
    assert "ya está reservado" not in reservar(cliente).get_data(as_text=True)


def test_usuario_no_cancela_reserva_ajena(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    cliente.get("/logout")
    registrar(cliente, correo="otro@uni.edu", documento="2002")
    entrar(cliente, "otro@uni.edu")
    assert "No se encontró" in cliente.post("/reservas/1/cancelar", follow_redirects=True).get_data(as_text=True)


def test_admin_modifica_reserva(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    cliente.get("/logout")
    entrar_admin(cliente)
    respuesta = cliente.post("/admin/reservas/1/editar", data={
        "fecha": PASADO, "hora_inicio": "14:00", "hora_fin": "16:00"}, follow_redirects=True)
    assert "Reserva modificada" in respuesta.get_data(as_text=True)


def test_admin_registra_nueva_tarifa(cliente):
    entrar_admin(cliente)
    cliente.post("/admin/tarifas", data={"tipo_vehiculo": "carro", "tipo_vinculacion": "estudiante", "valor_hora": "5000"})
    pagina = cliente.get("/admin/tarifas").get_data(as_text=True)
    assert "$5.000 COP" in pagina and "$2.400 COP" not in pagina


def test_tarifa_invalida(cliente):
    entrar_admin(cliente)
    respuesta = cliente.post("/admin/tarifas", data={"tipo_vehiculo": "carro", "tipo_vinculacion": "docente", "valor_hora": "-5"})
    assert "valor por hora positivo" in respuesta.get_data(as_text=True)


# ---- R. 7: pagos
def test_pago_exitoso_y_comprobante(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    respuesta = cliente.post("/pagar/1", data={"tarjeta": "4111 1111 1111 1111"}, follow_redirects=True)
    assert "Pago exitoso" in respuesta.get_data(as_text=True)
    assert "COMP-" in cliente.get("/historial").get_data(as_text=True)


def test_pago_rechazado(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    respuesta = cliente.post("/pagar/1", data={"tarjeta": "4111111111110000"}, follow_redirects=True)
    assert "rechazado" in respuesta.get_data(as_text=True)


def test_no_se_paga_dos_veces(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    cliente.post("/pagar/1", data={"tarjeta": "4111111111111111"})
    assert "ya está pagada" in cliente.get("/pagar/1", follow_redirects=True).get_data(as_text=True)


def test_tarjeta_demasiado_corta(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    assert "al menos 12 dígitos" in cliente.post("/pagar/1", data={"tarjeta": "123"}).get_data(as_text=True)


def test_admin_consulta_pagos(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente)
    cliente.post("/pagar/1", data={"tarjeta": "4111111111111111"})
    cliente.get("/logout")
    entrar_admin(cliente)
    assert "Ana Pérez" in cliente.get("/admin/pagos").get_data(as_text=True)


# ---- R. 8: reportes
def test_reporte_con_datos(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente, inicio="08:00", fin="10:00")
    cliente.post("/pagar/1", data={"tarjeta": "4111111111111111"})
    cliente.get("/logout")
    entrar_admin(cliente)
    pagina = cliente.get(f"/admin/reportes?desde={MANANA}&hasta={MANANA}").get_data(as_text=True)
    assert "06:00-10:00" in pagina and "$4.800 COP" in pagina


def test_reporte_sin_datos(cliente):
    entrar_admin(cliente)
    assert "No hay datos" in cliente.get(f"/admin/reportes?desde={MANANA}&hasta={MANANA}").get_data(as_text=True)


def test_reporte_rango_invalido(cliente):
    entrar_admin(cliente)
    assert "no puede ser posterior" in cliente.get(f"/admin/reportes?desde={PASADO}&hasta={MANANA}").get_data(as_text=True)


# ---- Disponibilidad por fecha y hora, y reservas sin cruces entre usuarios
def test_espacio_reservado_se_muestra_no_disponible(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente, inicio="08:00", fin="11:00")
    pagina = cliente.get(f"/disponibilidad?fecha={MANANA}&desde=09:00&hasta=10:00").get_data(as_text=True)
    assert "espacio reservado" in pagina and "No disponible: reservado" in pagina
    assert "08:00 a 11:00" in pagina


def test_espacio_libre_fuera_del_horario_reservado(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente, inicio="08:00", fin="11:00")
    pagina = cliente.get(f"/disponibilidad?fecha={MANANA}&desde=11:00&hasta=12:00&zona=A").get_data(as_text=True)
    assert "espacio reservado" not in pagina


def test_consulta_con_horas_invalidas_usa_valores_por_defecto(cliente):
    registrar(cliente)
    entrar(cliente)
    pagina = cliente.get(f"/disponibilidad?fecha={MANANA}&desde=12:00&hasta=10:00").get_data(as_text=True)
    assert "hora final debe ser posterior" in pagina


def test_otro_usuario_no_puede_reservar_el_mismo_horario(cliente):
    registrar(cliente)
    entrar(cliente)
    reservar(cliente, inicio="08:00", fin="11:00")
    cliente.get("/logout")
    registrar(cliente, correo="otro@uni.edu", documento="2002")
    entrar(cliente, "otro@uni.edu")
    assert "ya está reservado" in reservar(cliente, inicio="08:00", fin="11:00").get_data(as_text=True)
    assert "ya está reservado" in reservar(cliente, inicio="09:00", fin="10:00").get_data(as_text=True)


def test_reservar_precarga_fecha_y_horas_de_la_consulta(cliente):
    registrar(cliente)
    entrar(cliente)
    pagina = cliente.get(f"/reservar/1?fecha={MANANA}&desde=09:00&hasta=10:00").get_data(as_text=True)
    assert 'value="09:00"' in pagina and 'value="10:00"' in pagina
