"""
Tests para el módulo de gastos.
"""
import pytest
from datetime import date
from ARCHIVOS.models import db, User, Gasto, Proveedor


class TestGastosRoutes:
    """Tests para las rutas de gastos."""
    
    def test_gastos_page_requires_login(self, client):
        """Verificar que la página de gastos requiere autenticación."""
        response = client.get('/gastos')
        assert response.status_code in [302, 401, 308]  # Redirect to login or unauthorized
    
    def test_gastos_page_loads_for_logged_user(self, client, app, init_database):
        """Verificar que la página de gastos carga para usuario autenticado."""
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        response = client.get('/gastos', follow_redirects=True)
        assert response.status_code == 200
    
    def test_proveedores_page_loads(self, client, app, init_database):
        """Test que la página de proveedores carga."""
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        # La ruta es /proveedores (no /gastos/proveedores)
        response = client.get('/proveedores')
        assert response.status_code == 200


class TestGastoRepository:
    """Tests para el repositorio de gastos."""
    
    def test_crear_proveedor(self, app, init_database):
        """Test crear un proveedor en la base de datos."""
        with app.app_context():
            from ARCHIVOS.database import proveedor_repository
            
            proveedor = proveedor_repository.add('Proveedor Test', 1)
            
            assert proveedor is not None
            assert proveedor.nombre == 'PROVEEDOR TEST'
    
    def test_crear_gasto(self, app, init_database):
        """Test crear un gasto en la base de datos."""
        with app.app_context():
            from ARCHIVOS.database import gasto_repository, proveedor_repository
            from ARCHIVOS.models import Gasto
            
            # Crear proveedor primero
            proveedor = proveedor_repository.add('Proveedor Gasto', 1)
            
            # Crear gasto (el método add no retorna el gasto, verificamos con query)
            gasto_repository.add(
                proveedor_id=proveedor.id,
                descripcion='Gasto de prueba',
                monto=150.50,
                fecha=date.today().strftime('%Y-%m-%d'),
                categoria='PAPELERIA',
                user_id=1
            )
            
            # Verificar que el gasto se creó
            gasto = Gasto.query.filter_by(descripcion='Gasto de prueba').first()
            assert gasto is not None
            assert gasto.monto == 150.50
            assert gasto.categoria == 'PAPELERIA'
    
    def test_total_gastos(self, app, init_database):
        """Test obtener el total de gastos de un usuario."""
        with app.app_context():
            from ARCHIVOS.database import gasto_repository, proveedor_repository
            
            proveedor = proveedor_repository.add('Proveedor Total', 1)
            
            gasto_repository.add(
                proveedor_id=proveedor.id,
                descripcion='Gasto A',
                monto=300,
                fecha=date.today().strftime('%Y-%m-%d'),
                categoria='OTROS',
                user_id=1
            )
            
            total = gasto_repository.get_total_gastos(1)
            assert total >= 300
    
    def test_distribucion_gastos(self, app, init_database):
        """Test obtener distribución de gastos por categoría."""
        with app.app_context():
            from ARCHIVOS.database import gasto_repository, proveedor_repository
            
            proveedor = proveedor_repository.add('Proveedor Dist', 1)
            
            gasto_repository.add(
                proveedor_id=proveedor.id,
                descripcion='Gasto Cat 1',
                monto=100,
                fecha=date.today().strftime('%Y-%m-%d'),
                categoria='PAPELERIA',
                user_id=1
            )
            
            gasto_repository.add(
                proveedor_id=proveedor.id,
                descripcion='Gasto Cat 2',
                monto=200,
                fecha=date.today().strftime('%Y-%m-%d'),
                categoria='SERVICIOS',
                user_id=1
            )
            
            dist = gasto_repository.get_gastos_distribution(1)
            assert len(dist) > 0
