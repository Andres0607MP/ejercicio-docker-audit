import os
from unittest.mock import patch, MagicMock
import pytest
from app import app

os.environ.setdefault("DB_HOST", "db")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "appuser")
os.environ.setdefault("DB_PASS", "change_me")
os.environ.setdefault("DB_NAME", "legacydb")
os.environ.setdefault("PORT", "5050")


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"


@patch("app.get_db_connection")
def test_home_ok(mock_db, client):
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    response = client.get("/")
    assert response.status_code == 200
    assert "API Legacy TechNova - Funcionando" in response.get_data(as_text=True)


@patch("app.get_db_connection")
def test_home_error_no_expone_excepcion(mock_db, client):
    mock_db.side_effect = Exception("Connection refused")
    response = client.get("/")
    assert response.status_code == 500
    text = response.get_data(as_text=True)
    assert "Sistema temporalmente no disponible" in text
    assert "Connection refused" not in text


def test_buscar_id_valido(client):
    response = client.get("/buscar?id=42")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Búsqueda de usuario" in text
    assert "42" in text


def test_buscar_id_no_numerico(client):
    response = client.get("/buscar?id=1; DROP TABLE usuarios")
    assert response.status_code == 400
    text = response.get_data(as_text=True)
    assert "Solicitud inválida" in text


def test_no_sql_string_concatenation():
    from app import buscar_usuario
    import inspect
    source = inspect.getsource(buscar_usuario)
    assert '" + usuario_id' not in source
    assert "' + usuario_id" not in source
    assert "%s" in source


def test_error_no_expone_excepcion(client):
    response = client.get("/nonexistent")
    assert response.status_code == 404
    text = response.get_data(as_text=True)
    assert "Recurso no encontrado" in text
    assert "Traceback" not in text
