"""
Tests para el módulo de papelerías.
"""
import pytest
from ARCHIVOS.models import db, User, Papeleria, PapeleriaPrecio


class TestPapeleriasRoutes:
    """Tests para las rutas de papelerías."""
    
    def test_index_requires_login(self, client):
        """Verificar que el dashboard requiere autenticación."""
        response = client.get('/')
        assert response.status_code in [302, 401]
    
    def test_index_loads_for_logged_user(self, client, app, init_database):
        """Verificar que el dashboard carga para usuario autenticado."""
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        response = client.get('/')
        assert response.status_code == 200
    
    def test_ver_papeleria(self, client, app, init_database):
        """Test ver detalle de una papelería."""
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        response = client.get('/papeleria/1')
        assert response.status_code == 200


class TestPapeleriaRepository:
    """Tests para el repositorio de papelerías."""
    
    def test_crear_papeleria(self, app, init_database):
        """Test crear una papelería en la base de datos."""
        with app.app_context():
            from ARCHIVOS.database import papeleria_repository
            
            papeleria = papeleria_repository.add('Papeleria Repository Test', 1)
            
            assert papeleria is not None
            assert papeleria.nombre == 'PAPELERIA REPOSITORY TEST'
            assert papeleria.is_active == True
    
    def test_soft_delete_papeleria(self, app, init_database):
        """Test soft delete de una papelería."""
        with app.app_context():
            from ARCHIVOS.database import papeleria_repository
            
            papeleria = papeleria_repository.add('Papeleria A Eliminar', 1)
            papeleria_id = papeleria.id
            
            # Soft delete (el método no retorna nada, verificamos con query)
            papeleria_repository.delete(papeleria_id, 1)
            
            # Verificar que está inactiva
            papeleria_deleted = db.session.get(Papeleria, papeleria_id)
            assert papeleria_deleted.is_active == False
    
    def test_reactivar_papeleria(self, app, init_database):
        """Test reactivar una papelería eliminada."""
        with app.app_context():
            from ARCHIVOS.database import papeleria_repository
            
            # Crear y eliminar
            papeleria = papeleria_repository.add('Papeleria Reactivar', 1)
            papeleria_repository.delete(papeleria.id, 1)
            
            # Reactivar creando con el mismo nombre
            reactivada = papeleria_repository.add('Papeleria Reactivar', 1)
            
            assert reactivada.is_active == True
    
    def test_obtener_papelerias_con_totales(self, app, init_database):
        """Test obtener papelerías con totales."""
        with app.app_context():
            from ARCHIVOS.database import papeleria_repository
            
            # Crear papelería
            papeleria_repository.add('Papeleria Totales', 1)
            
            # Obtener papelerías
            result = papeleria_repository.get_papelerias_and_totals_for_user(1)
            
            assert 'papelerias' in result
            assert 'totales' in result


class TestPapeleriaPrecios:
    """Tests para precios de papelerías."""
    
    def test_establecer_precio_tramite(self, app, init_database):
        """Test establecer precio predefinido para un trámite."""
        with app.app_context():
            from ARCHIVOS.database import papeleria_repository
            
            # Crear papelería
            papeleria = papeleria_repository.add('Papeleria Precios', 1)
            
            # Establecer precio usando set_precios_bulk con diccionario {tramite: precio}
            papeleria_repository.set_precios_bulk(papeleria.id, {'ACTA DE NACIMIENTO': 50.00}, 1)
            
            # Verificar
            precio = papeleria_repository.get_default_precio(papeleria.id, 'ACTA DE NACIMIENTO', 1)
            assert precio == 50.00
    
    def test_actualizar_precio_tramite(self, app, init_database):
        """Test actualizar precio predefinido."""
        with app.app_context():
            from ARCHIVOS.database import papeleria_repository
            
            papeleria = papeleria_repository.add('Papeleria Actualizar', 1)
            
            # Establecer precio inicial
            papeleria_repository.set_precios_bulk(papeleria.id, {'CURP': 30.00}, 1)
            
            # Actualizar
            papeleria_repository.set_precios_bulk(papeleria.id, {'CURP': 45.00}, 1)
            
            # Verificar
            precio = papeleria_repository.get_default_precio(papeleria.id, 'CURP', 1)
            assert precio == 45.00
