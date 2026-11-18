# Sistema Inteligente de Gestión de Parqueaderos

Aplicación web hecha con Python (Flask) y SQLite. Ingeniería del Software 2026-2.

## Cuentas de prueba
- Administrador: `admin@universidad.edu` / `Admin123`
- Usuario: se crea desde "Crear una cuenta".
- Pago simulado: cualquier número de 12 o más dígitos (por ejemplo `4111 1111 1111 1111`). Si termina en `0000`, el pago se rechaza.

## Ejecutar en el computador
```
pip install -r requirements.txt
python app.py
```
Abre http://localhost:5000

## Pruebas automáticas
```
pip install pytest
python -m pytest -q
```

## Publicar gratis en Render (URL pública)
1. Sube esta carpeta a un repositorio de GitHub.
2. En render.com: New > Web Service > conecta el repositorio.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Plan Free. Cuando termine, Render te da la URL (termina en `.onrender.com`).

Nota: en el plan gratuito la base de datos SQLite se reinicia cuando el servicio se reinicia; los datos iniciales (administrador, espacios y tarifas) se vuelven a crear solos. La primera visita puede tardar cerca de un minuto si el servicio estaba dormido: ábrelo unos minutos antes de exponer.

## Publicar en Replit
Crea un Repl de Python, sube estos archivos y pulsa Run (el comando de ejecución es `python app.py`). Luego usa Deploy para obtener la URL.
