import os
import logging
import pymysql
from flask import Flask, request
from flask_talisman import Talisman

app = Flask(__name__)

Talisman(app, force_https=False, content_security_policy={
    'default-src': "'self'",
    'script-src': "'self'",
    'style-src': "'self'",
})

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
PORT = int(os.getenv("PORT", "5050"))


def get_db_connection():
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            connect_timeout=5,
        )
        return conn
    except Exception:
        logger.exception("No se pudo conectar a la base de datos")
        raise


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    logger.exception("Unhandled exception")
    return "<h1>Error interno del servidor</h1><p>Ocurrió un problema inesperado.</p>", 500


@app.errorhandler(404)
def handle_404(error):
    return "<h1>404</h1><p>Recurso no encontrado.</p>", 404


@app.errorhandler(400)
def handle_400(error):
    return "<h1>400</h1><p>Solicitud inválida.</p>", 400


@app.route("/")
def home():
    try:
        conn = get_db_connection()
        conn.close()
        return "<h1>API Legacy TechNova - Funcionando</h1>"
    except Exception:
        return "<h1>Sistema temporalmente no disponible</h1>", 500


@app.route("/buscar")
def buscar_usuario():
    usuario_id = request.args.get("id", "1")
    try:
        usuario_id = int(usuario_id)
    except (TypeError, ValueError):
        return "<h1>Solicitud inválida</h1><p>El ID debe ser un número entero.</p>", 400
    query = "SELECT * FROM usuarios WHERE id = %s"
    logger.info("Ejecutando consulta para usuario_id=%s", usuario_id)
    return f"<h1>Búsqueda de usuario</h1><p>ID consultado: {usuario_id}</p>"


@app.route("/health")
def health_check():
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
