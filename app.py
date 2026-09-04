import pymysql
import random
from flask import Flask, request

app = Flask(__name__)

# 🚨 FALLO 1: Credenciales de BD en texto plano (Bandit / Gitleaks)
DB_HOST = "servidor-bd-ejemplo"
DB_USER = "root"
DB_PASS = "admin_adso_2026_secreto"
DB_NAME = "legacydb"

@app.route("/")
def home():
    try:
        conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME)
        conn.close()
        return "<h1>API Legacy TechNova - Funcionando (Más o menos)</h1>"
    except Exception as e:
        return f"<h1>Sistema Caído</h1><p>{e}</p>", 500

@app.route("/buscar")
def buscar_usuario():
    usuario_id = request.args.get("id", "1")
    query_peligrosa = "SELECT * FROM usuarios WHERE id = " + usuario_id
    return f"Simulando consulta: {query_peligrosa}"

@app.route("/health")
def health_check():
    if random.random() < 0.3:
        resultado = 1 / 0 
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5050, debug=True)