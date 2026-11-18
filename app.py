"""Sistema Inteligente de Gestión de Parqueaderos - aplicación web (Flask + SQLite)."""
import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db
import reglas
from db import TIPOS_VEHICULO, TIPOS_VINCULACION, get_db

PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_app(config=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "clave-academica-cambiar")
    app.config["DATABASE"] = os.environ.get("DATABASE", os.path.join(app.root_path, "parqueadero.db"))
    if config:
        app.config.update(config)
    app.teardown_appcontext(db.close_db)
    with app.app_context():
        db.init_db()

    @app.context_processor
    def datos_globales():
        return {"usuario_actual": g.get("usuario"), "TIPOS_VEHICULO": TIPOS_VEHICULO,
                "TIPOS_VINCULACION": TIPOS_VINCULACION, "ESTADOS_ESPACIO": reglas.ESTADOS_ESPACIO,
                "pago_aprobado": reglas.pago_aprobado,
                "formato_cop": lambda valor: f"${valor:,.0f}".replace(",", ".") + " COP"}

    @app.before_request
    def cargar_usuario():
        g.usuario = None
        if session.get("id_usuario"):
            g.usuario = get_db().execute(
                "SELECT * FROM usuario WHERE id_usuario = ?", (session["id_usuario"],)).fetchone()
            if g.usuario is None:
                session.clear()
        db.finalizar_reservas_vencidas()

    def login_requerido(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if g.usuario is None:
                flash("Inicia sesión para continuar.", "error")
                return redirect(url_for("login"))
            return vista(*args, **kwargs)
        return envoltura

    def admin_requerido(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if g.usuario is None:
                return redirect(url_for("login"))
            if g.usuario["rol"] != "administrador":
                flash("Solo el administrador puede entrar a esa sección.", "error")
                return redirect(url_for("panel"))
            return vista(*args, **kwargs)
        return envoltura

    # ------------------------------------------------------------------ R. 1
    @app.route("/")
    def inicio():
        return redirect(url_for("panel" if g.usuario else "login"))

    def validar_datos_usuario(form, requiere_clave):
        errores = []
        if not all(form.get(c, "").strip() for c in ("nombre", "documento", "correo", "placa_vehiculo")):
            errores.append("Todos los campos son obligatorios.")
        if not PATRON_CORREO.match(form.get("correo", "").strip()):
            errores.append("El correo no tiene un formato válido.")
        if form.get("tipo_vinculacion") not in TIPOS_VINCULACION:
            errores.append("Selecciona un tipo de vinculación válido.")
        if requiere_clave and len(form.get("contrasena", "")) < 6:
            errores.append("La contraseña debe tener al menos 6 caracteres.")
        return errores

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if request.method == "POST":
            errores = validar_datos_usuario(request.form, True)
            if not errores:
                try:
                    get_db().execute(
                        "INSERT INTO usuario (nombre, documento, correo, contrasena_hash, tipo_vinculacion,"
                        " placa_vehiculo, rol) VALUES (?, ?, ?, ?, ?, ?, 'usuario')",
                        (request.form["nombre"].strip(), request.form["documento"].strip(),
                         request.form["correo"].strip().lower(), generate_password_hash(request.form["contrasena"]),
                         request.form["tipo_vinculacion"], request.form["placa_vehiculo"].strip().upper()))
                    get_db().commit()
                    flash("Registro exitoso. Ya puedes iniciar sesión.", "success")
                    return redirect(url_for("login"))
                except sqlite3.IntegrityError:
                    errores.append("Ya existe un usuario con ese documento o correo.")
            for error in errores:
                flash(error, "error")
        return render_template("registro.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            usuario = get_db().execute(
                "SELECT * FROM usuario WHERE correo = ?", (request.form.get("correo", "").strip().lower(),)).fetchone()
            if usuario and check_password_hash(usuario["contrasena_hash"], request.form.get("contrasena", "")):
                session.clear()
                session["id_usuario"] = usuario["id_usuario"]
                flash("Inicio de sesión exitoso.", "success")
                return redirect(url_for("panel"))
            flash("Correo o contraseña incorrectos.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Sesión cerrada.", "success")
        return redirect(url_for("login"))

    @app.route("/recuperar", methods=["GET", "POST"])
    def recuperar():
        if request.method == "POST":
            usuario = get_db().execute(
                "SELECT * FROM usuario WHERE correo = ? AND documento = ?",
                (request.form.get("correo", "").strip().lower(), request.form.get("documento", "").strip())).fetchone()
            if usuario is None:
                flash("No encontramos un usuario con esos datos.", "error")
            elif len(request.form.get("contrasena", "")) < 6:
                flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
            else:
                get_db().execute("UPDATE usuario SET contrasena_hash = ? WHERE id_usuario = ?",
                                 (generate_password_hash(request.form["contrasena"]), usuario["id_usuario"]))
                get_db().commit()
                flash("Contraseña restablecida. Ya puedes iniciar sesión.", "success")
                return redirect(url_for("login"))
        return render_template("recuperar.html")

    # ------------------------------------------------------------------ R. 2 (perfil del usuario)
    @app.route("/perfil", methods=["GET", "POST"])
    @login_requerido
    def perfil():
        if request.method == "POST":
            errores = validar_datos_usuario(request.form, False)
            if not errores:
                try:
                    get_db().execute(
                        "UPDATE usuario SET nombre = ?, documento = ?, correo = ?, tipo_vinculacion = ?,"
                        " placa_vehiculo = ? WHERE id_usuario = ?",
                        (request.form["nombre"].strip(), request.form["documento"].strip(),
                         request.form["correo"].strip().lower(), request.form["tipo_vinculacion"],
                         request.form["placa_vehiculo"].strip().upper(), g.usuario["id_usuario"]))
                    get_db().commit()
                    flash("Datos actualizados correctamente.", "success")
                    return redirect(url_for("perfil"))
                except sqlite3.IntegrityError:
                    errores.append("Ese documento o correo ya pertenece a otro usuario.")
            for error in errores:
                flash(error, "error")
        return render_template("perfil.html")

    @app.route("/panel")
    @login_requerido
    def panel():
        if g.usuario["rol"] == "administrador":
            return redirect(url_for("admin_panel"))
        reservas = get_db().execute(
            "SELECT COUNT(*) FROM reserva WHERE id_usuario = ? AND estado = 'activa'",
            (g.usuario["id_usuario"],)).fetchone()[0]
        libres = len(reglas.listar_espacios(estado="disponible"))
        return render_template("panel.html", reservas_activas=reservas, libres=libres)

    # ------------------------------------------------------------------ R. 4
    @app.route("/disponibilidad")
    @login_requerido
    def disponibilidad():
        filtros = {c: request.args.get(c, "") for c in ("zona", "tipo_vehiculo", "estado")}
        fecha, desde, hasta = reglas.ventana_por_defecto()
        fecha = request.args.get("fecha") or fecha
        desde = request.args.get("desde") or desde
        hasta = request.args.get("hasta") or hasta
        if reglas.validar_consulta(fecha, desde, hasta):
            flash("Revisa la fecha y las horas: la hora final debe ser posterior a la inicial.", "error")
            fecha, desde, hasta = reglas.ventana_por_defecto()
        espacios = reglas.listar_espacios(**filtros, fecha=fecha, desde=desde, hasta=hasta)
        zonas = [f["zona"] for f in get_db().execute("SELECT DISTINCT zona FROM espacio ORDER BY zona")]
        return render_template("disponibilidad.html", espacios=espacios, filtros=filtros, zonas=zonas,
                               fecha=fecha, desde=desde, hasta=hasta)

    @app.route("/informacion")
    @login_requerido
    def informacion():
        tarifas = get_db().execute(
            "SELECT * FROM tarifa WHERE vigente = 1 ORDER BY tipo_vehiculo, tipo_vinculacion").fetchall()
        return render_template("informacion.html", tarifas=tarifas, apertura=reglas.HORA_APERTURA,
                               cierre=reglas.HORA_CIERRE)

    # ------------------------------------------------------------------ R. 5
    @app.route("/reservar/<int:id_espacio>", methods=["GET", "POST"])
    @login_requerido
    def reservar(id_espacio):
        espacio = get_db().execute("SELECT * FROM espacio WHERE id_espacio = ?", (id_espacio,)).fetchone()
        if espacio is None:
            flash("El espacio no existe.", "error")
            return redirect(url_for("disponibilidad"))
        tarifa = reglas.buscar_tarifa(espacio["tipo_vehiculo"], g.usuario["tipo_vinculacion"])
        if request.method == "POST":
            fecha, inicio, fin = (request.form.get(c, "") for c in ("fecha", "hora_inicio", "hora_fin"))
            error = reglas.validar_horario(fecha, inicio, fin)
            if error is None and espacio["estado"] == "fuera_de_servicio":
                error = "Ese espacio está fuera de servicio."
            if error is None and tarifa is None:
                error = "No hay una tarifa vigente para tu tipo de vinculación."
            if error:
                flash(error, "error")
            else:
                conexion = get_db()
                conexion.execute("BEGIN IMMEDIATE")  # bloquea la base para revisar y guardar sin que otro se cruce
                if reglas.hay_cruce(id_espacio, fecha, inicio, fin):
                    conexion.rollback()
                    flash("El espacio ya está reservado en ese horario. Elige otro espacio u otra hora.", "error")
                else:
                    valor = reglas.calcular_valor(tarifa["valor_hora"], inicio, fin)
                    codigo = "RES-" + secrets.token_hex(3).upper()
                    conexion.execute(
                        "INSERT INTO reserva (id_usuario, id_espacio, id_tarifa, fecha, hora_inicio, hora_fin,"
                        " codigo_confirmacion, valor_total) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (g.usuario["id_usuario"], id_espacio, tarifa["id_tarifa"], fecha, inicio, fin, codigo, valor))
                    conexion.commit()
                    flash(f"Reserva confirmada. Tu código es {codigo}.", "success")
                    return redirect(url_for("mis_reservas"))
        return render_template("reservar.html", espacio=espacio, tarifa=tarifa, hoy=datetime.now().strftime("%Y-%m-%d"),
                               previo={c: request.values.get(c, "") for c in ("fecha", "desde", "hasta")})

    def consultar_reservas(solo_usuario=None):
        consulta = ("SELECT r.*, e.codigo AS espacio, u.nombre AS usuario FROM reserva r"
                    " JOIN espacio e ON e.id_espacio = r.id_espacio JOIN usuario u ON u.id_usuario = r.id_usuario")
        parametros = []
        if solo_usuario:
            consulta += " WHERE r.id_usuario = ?"
            parametros.append(solo_usuario)
        return get_db().execute(consulta + " ORDER BY r.fecha DESC, r.hora_inicio DESC", parametros).fetchall()

    @app.route("/mis-reservas")
    @login_requerido
    def mis_reservas():
        return render_template("reservas.html", reservas=consultar_reservas(g.usuario["id_usuario"]), admin=False)

    @app.route("/reservas/<int:id_reserva>/cancelar", methods=["POST"])
    @login_requerido
    def cancelar_reserva(id_reserva):
        reserva = get_db().execute("SELECT * FROM reserva WHERE id_reserva = ?", (id_reserva,)).fetchone()
        es_admin = g.usuario["rol"] == "administrador"
        if reserva is None or (not es_admin and reserva["id_usuario"] != g.usuario["id_usuario"]):
            flash("No se encontró la reserva.", "error")
        elif reserva["estado"] != "activa":
            flash("Solo se pueden cancelar reservas activas.", "error")
        elif reglas.pago_aprobado(id_reserva) and not es_admin:
            flash("La reserva ya fue pagada; contacta al administrador para cancelarla.", "error")
        else:
            get_db().execute("UPDATE reserva SET estado = 'cancelada' WHERE id_reserva = ?", (id_reserva,))
            get_db().commit()
            flash("Reserva cancelada correctamente.", "success")
        return redirect(url_for("admin_reservas" if es_admin else "mis_reservas"))

    # ------------------------------------------------------------------ R. 7
    @app.route("/pagar/<int:id_reserva>", methods=["GET", "POST"])
    @login_requerido
    def pagar(id_reserva):
        reserva = get_db().execute(
            "SELECT * FROM reserva WHERE id_reserva = ? AND id_usuario = ?",
            (id_reserva, g.usuario["id_usuario"])).fetchone()
        if reserva is None or reserva["estado"] == "cancelada":
            flash("No se encontró una reserva pagable.", "error")
            return redirect(url_for("mis_reservas"))
        if reglas.pago_aprobado(id_reserva):
            flash("Esta reserva ya está pagada.", "error")
            return redirect(url_for("historial"))
        if request.method == "POST":
            tarjeta = re.sub(r"\D", "", request.form.get("tarjeta", ""))
            if len(tarjeta) < 12:
                flash("Ingresa un número de tarjeta simulado de al menos 12 dígitos.", "error")
            else:
                aprobado = not tarjeta.endswith("0000")
                comprobante = "COMP-" + secrets.token_hex(4).upper() if aprobado else "RECHAZADO"
                get_db().execute(
                    "INSERT INTO pago (id_reserva, monto, estado, fecha_pago, comprobante) VALUES (?, ?, ?, ?, ?)",
                    (id_reserva, reserva["valor_total"], "pagado" if aprobado else "rechazado",
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), comprobante))
                get_db().commit()
                if aprobado:
                    flash(f"Pago exitoso. Comprobante {comprobante}.", "success")
                    return redirect(url_for("historial"))
                flash("El pago fue rechazado. Intenta con otra tarjeta.", "error")
        return render_template("pagar.html", reserva=reserva)

    @app.route("/historial")
    @login_requerido
    def historial():
        pagos = get_db().execute(
            "SELECT p.*, r.codigo_confirmacion FROM pago p JOIN reserva r ON r.id_reserva = p.id_reserva"
            " WHERE r.id_usuario = ? ORDER BY p.id_pago DESC", (g.usuario["id_usuario"],)).fetchall()
        return render_template("historial.html", reservas=consultar_reservas(g.usuario["id_usuario"]), pagos=pagos)

    # ------------------------------------------------------------------ Administrador
    @app.route("/admin")
    @admin_requerido
    def admin_panel():
        conteos = {t: get_db().execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                   for t in ("usuario", "espacio", "reserva", "tarifa", "pago")}
        return render_template("admin_panel.html", conteos=conteos)

    @app.route("/admin/usuarios")
    @admin_requerido
    def admin_usuarios():
        return render_template("admin_usuarios.html",
                               usuarios=get_db().execute("SELECT * FROM usuario ORDER BY nombre").fetchall())

    @app.route("/admin/usuarios/<int:id_usuario>/editar", methods=["GET", "POST"])
    @admin_requerido
    def admin_usuario_editar(id_usuario):
        usuario = get_db().execute("SELECT * FROM usuario WHERE id_usuario = ?", (id_usuario,)).fetchone()
        if usuario is None:
            flash("El usuario no existe.", "error")
            return redirect(url_for("admin_usuarios"))
        if request.method == "POST":
            errores = validar_datos_usuario(request.form, False)
            if request.form.get("rol") not in ("usuario", "administrador"):
                errores.append("Selecciona un rol válido.")
            if not errores:
                try:
                    get_db().execute(
                        "UPDATE usuario SET nombre = ?, documento = ?, correo = ?, tipo_vinculacion = ?,"
                        " placa_vehiculo = ?, rol = ? WHERE id_usuario = ?",
                        (request.form["nombre"].strip(), request.form["documento"].strip(),
                         request.form["correo"].strip().lower(), request.form["tipo_vinculacion"],
                         request.form["placa_vehiculo"].strip().upper(), request.form["rol"], id_usuario))
                    get_db().commit()
                    flash("Usuario actualizado correctamente.", "success")
                    return redirect(url_for("admin_usuarios"))
                except sqlite3.IntegrityError:
                    errores.append("Ese documento o correo ya pertenece a otro usuario.")
            for error in errores:
                flash(error, "error")
        return render_template("admin_usuario_editar.html", usuario=usuario)

    @app.route("/admin/usuarios/<int:id_usuario>/eliminar", methods=["POST"])
    @admin_requerido
    def admin_usuario_eliminar(id_usuario):
        if id_usuario == g.usuario["id_usuario"]:
            flash("No puedes eliminar tu propio usuario.", "error")
        elif get_db().execute("SELECT 1 FROM reserva WHERE id_usuario = ?", (id_usuario,)).fetchone():
            flash("No se puede eliminar un usuario que tiene reservas registradas.", "error")
        else:
            get_db().execute("DELETE FROM usuario WHERE id_usuario = ?", (id_usuario,))
            get_db().commit()
            flash("Usuario eliminado correctamente.", "success")
        return redirect(url_for("admin_usuarios"))

    @app.route("/admin/espacios", methods=["GET", "POST"])
    @admin_requerido
    def admin_espacios():
        if request.method == "POST":
            codigo, zona = request.form.get("codigo", "").strip().upper(), request.form.get("zona", "").strip().upper()
            if not codigo or not zona or request.form.get("tipo_vehiculo") not in TIPOS_VEHICULO:
                flash("Completa código, zona y tipo de vehículo.", "error")
            else:
                try:
                    get_db().execute("INSERT INTO espacio (codigo, zona, tipo_vehiculo) VALUES (?, ?, ?)",
                                     (codigo, zona, request.form["tipo_vehiculo"]))
                    get_db().commit()
                    flash("Espacio registrado correctamente.", "success")
                except sqlite3.IntegrityError:
                    flash("Ya existe un espacio con ese código.", "error")
        return render_template("admin_espacios.html", espacios=reglas.listar_espacios())

    @app.route("/admin/espacios/<int:id_espacio>/editar", methods=["GET", "POST"])
    @admin_requerido
    def admin_espacio_editar(id_espacio):
        espacio = get_db().execute("SELECT * FROM espacio WHERE id_espacio = ?", (id_espacio,)).fetchone()
        if espacio is None:
            flash("El espacio no existe.", "error")
            return redirect(url_for("admin_espacios"))
        if request.method == "POST":
            if (request.form.get("estado") not in reglas.ESTADOS_ESPACIO
                    or request.form.get("tipo_vehiculo") not in TIPOS_VEHICULO
                    or not request.form.get("zona", "").strip()):
                flash("Revisa los datos del espacio.", "error")
            else:
                get_db().execute("UPDATE espacio SET zona = ?, tipo_vehiculo = ?, estado = ? WHERE id_espacio = ?",
                                 (request.form["zona"].strip().upper(), request.form["tipo_vehiculo"],
                                  request.form["estado"], id_espacio))
                get_db().commit()
                flash("Espacio actualizado correctamente.", "success")
                return redirect(url_for("admin_espacios"))
        return render_template("admin_espacio_editar.html", espacio=espacio)

    @app.route("/admin/espacios/<int:id_espacio>/eliminar", methods=["POST"])
    @admin_requerido
    def admin_espacio_eliminar(id_espacio):
        if reglas.tiene_reservas_activas(id_espacio):
            flash("No se puede eliminar un espacio con reservas activas.", "error")
        elif get_db().execute("SELECT 1 FROM reserva WHERE id_espacio = ?", (id_espacio,)).fetchone():
            flash("El espacio tiene historial de reservas; márcalo como fuera de servicio.", "error")
        else:
            get_db().execute("DELETE FROM espacio WHERE id_espacio = ?", (id_espacio,))
            get_db().commit()
            flash("Espacio eliminado correctamente.", "success")
        return redirect(url_for("admin_espacios"))

    @app.route("/admin/reservas")
    @admin_requerido
    def admin_reservas():
        return render_template("reservas.html", reservas=consultar_reservas(), admin=True)

    @app.route("/admin/reservas/<int:id_reserva>/editar", methods=["GET", "POST"])
    @admin_requerido
    def admin_reserva_editar(id_reserva):
        reserva = get_db().execute("SELECT * FROM reserva WHERE id_reserva = ?", (id_reserva,)).fetchone()
        if reserva is None or reserva["estado"] != "activa":
            flash("Solo se pueden modificar reservas activas.", "error")
            return redirect(url_for("admin_reservas"))
        if request.method == "POST":
            fecha, inicio, fin = (request.form.get(c, "") for c in ("fecha", "hora_inicio", "hora_fin"))
            error = reglas.validar_horario(fecha, inicio, fin)
            if error is None and reglas.hay_cruce(reserva["id_espacio"], fecha, inicio, fin, excluir=id_reserva):
                error = "El espacio ya está reservado en ese horario."
            if error:
                flash(error, "error")
            else:
                tarifa = get_db().execute("SELECT * FROM tarifa WHERE id_tarifa = ?", (reserva["id_tarifa"],)).fetchone()
                get_db().execute(
                    "UPDATE reserva SET fecha = ?, hora_inicio = ?, hora_fin = ?, valor_total = ? WHERE id_reserva = ?",
                    (fecha, inicio, fin, reglas.calcular_valor(tarifa["valor_hora"], inicio, fin), id_reserva))
                get_db().commit()
                flash("Reserva modificada correctamente.", "success")
                return redirect(url_for("admin_reservas"))
        return render_template("admin_reserva_editar.html", reserva=reserva)

    @app.route("/admin/tarifas", methods=["GET", "POST"])
    @admin_requerido
    def admin_tarifas():
        if request.method == "POST":
            try:
                valor = int(request.form.get("valor_hora", ""))
            except ValueError:
                valor = 0
            if (valor <= 0 or request.form.get("tipo_vehiculo") not in TIPOS_VEHICULO
                    or request.form.get("tipo_vinculacion") not in TIPOS_VINCULACION):
                flash("Ingresa un valor por hora positivo y selecciona vehículo y vinculación.", "error")
            else:
                get_db().execute("UPDATE tarifa SET vigente = 0 WHERE tipo_vehiculo = ? AND tipo_vinculacion = ?",
                                 (request.form["tipo_vehiculo"], request.form["tipo_vinculacion"]))
                get_db().execute("INSERT INTO tarifa (tipo_vehiculo, tipo_vinculacion, valor_hora) VALUES (?, ?, ?)",
                                 (request.form["tipo_vehiculo"], request.form["tipo_vinculacion"], valor))
                get_db().commit()
                flash("Tarifa registrada; reemplaza a la anterior de esa combinación.", "success")
        tarifas = get_db().execute(
            "SELECT * FROM tarifa WHERE vigente = 1 ORDER BY tipo_vehiculo, tipo_vinculacion").fetchall()
        return render_template("admin_tarifas.html", tarifas=tarifas)

    @app.route("/admin/pagos")
    @admin_requerido
    def admin_pagos():
        pagos = get_db().execute(
            "SELECT p.*, r.codigo_confirmacion, u.nombre FROM pago p JOIN reserva r ON r.id_reserva = p.id_reserva"
            " JOIN usuario u ON u.id_usuario = r.id_usuario ORDER BY p.id_pago DESC").fetchall()
        return render_template("admin_pagos.html", pagos=pagos)

    @app.route("/admin/reportes")
    @admin_requerido
    def admin_reportes():
        desde, hasta = request.args.get("desde", ""), request.args.get("hasta", "")
        reporte, consultado = None, bool(desde and hasta)
        if consultado:
            try:
                datetime.strptime(desde, "%Y-%m-%d"), datetime.strptime(hasta, "%Y-%m-%d")
            except ValueError:
                flash("Las fechas del reporte no son válidas.", "error")
                consultado = False
            else:
                if desde > hasta:
                    flash("La fecha inicial no puede ser posterior a la final.", "error")
                    consultado = False
                else:
                    reporte = reglas.generar_reporte(desde, hasta)
                    if reporte is None:
                        flash("No hay datos para el rango de fechas consultado.", "error")
        return render_template("admin_reportes.html", reporte=reporte, desde=desde, hasta=hasta)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
