from app import app

def test_health_check():
    cliente = app.test_client()
    for _ in range(5):
        respuesta = cliente.get('/health')
        assert respuesta.status_code == 200, "El servicio de salud es inestable"