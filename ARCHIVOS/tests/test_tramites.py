"""
Tests para el módulo de trámites.
"""
import pytest
from datetime import date, timedelta
from ARCHIVOS.models import db, User, Papeleria, Tramite, TramiteCosto


class TestTramitesRoutes:
    """Tests para las rutas de trámites."""
    
    def test_registrar_tramite(self, client, app, init_database):
        """Test registrar un nuevo trámite."""
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        # La ruta es /registrar-tramite (POST) no /papeleria/1/registrar-tramite
        response = client.post('/registrar-tramite', data={
            'papeleria_id': 1,
            'tramite': 'ACTA DE NACIMIENTO',
            'precio': '50.00',
            'costo': '25.00',
            'cantidad': '1',
            'fecha': date.today().strftime('%Y-%m-%d')
        }, follow_redirects=True)
        
        # Puede redirigir o devolver 200
        assert response.status_code in [200, 302]
    
    def test_ver_detalle_papeleria(self, client, app, init_database):
        """Test ver detalle de una papelería con trámites."""
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['_fresh'] = True
        
        response = client.get('/papeleria/1')
        assert response.status_code == 200


class TestTramiteRepository:
    """Tests para el repositorio de trámites."""
    
    def test_crear_tramite_bulk(self, app, init_database):
        """Test crear trámites en la base de datos."""
        with app.app_context():
            from ARCHIVOS.database import tramite_repository
            
            tramite_repository.add_bulk(
                papeleria_id=1,
                tramite='ACTA DE MATRIMONIO',
                user_id=1,
                fecha=date.today().strftime('%Y-%m-%d'),
                precio=80.00,
                costo=40.00,
                cantidad=1
            )
            
            tramite = Tramite.query.filter_by(tramite='ACTA DE MATRIMONIO').first()
            assert tramite is not None
            assert tramite.precio == 80.00
    
    def test_crear_multiples_tramites_bulk(self, app, init_database):
        """Test crear múltiples trámites de un solo tipo."""
        with app.app_context():
            from ARCHIVOS.database import tramite_repository
            
            tramite_repository.add_bulk(
                papeleria_id=1,
                tramite='CONSTANCIA BULK',
                user_id=1,
                fecha=date.today().strftime('%Y-%m-%d'),
                precio=25.00,
                costo=10.00,
                cantidad=3
            )
            
            tramites = Tramite.query.filter_by(tramite='CONSTANCIA BULK', user_id=1).all()
            assert len(tramites) == 3
    
    def test_resumen_mensual(self, app, init_database):
        """Test obtener resumen mensual de trámites."""
        with app.app_context():
            from ARCHIVOS.database import tramite_repository
            
            # Crear algunos trámites
            tramite_repository.add_bulk(
                papeleria_id=1,
                tramite='RESUMEN 1',
                user_id=1,
                fecha=date.today().strftime('%Y-%m-%d'),
                precio=100.00,
                costo=50.00,
                cantidad=1
            )
            
            summary = tramite_repository.get_monthly_summary(1)
            
            assert 'monthly_data' in summary
            assert 'totals' in summary
    
    def test_distribucion_tramites(self, app, init_database):
        """Test obtener distribución de trámites por tipo."""
        with app.app_context():
            from ARCHIVOS.database import tramite_repository
            
            # Crear trámites de diferentes tipos
            tramite_repository.add_bulk(
                papeleria_id=1,
                tramite='TIPO A',
                user_id=1,
                fecha=date.today().strftime('%Y-%m-%d'),
                precio=50.00,
                costo=25.00,
                cantidad=3
            )
            
            tramite_repository.add_bulk(
                papeleria_id=1,
                tramite='TIPO B',
                user_id=1,
                fecha=date.today().strftime('%Y-%m-%d'),
                precio=30.00,
                costo=15.00,
                cantidad=2
            )
            
            dist = tramite_repository.get_tramites_distribution(1)
            
            assert len(dist) > 0


class TestTramiteCostos:
    """Tests para costos predefinidos de trámites."""
    
    def test_establecer_costo_tramite(self, app, init_database):
        """Test establecer costo predefinido para un trámite."""
        with app.app_context():
            from ARCHIVOS.database import tramite_repository
            
            tramite_repository.set_costo('ACTA DE DEFUNCION', 35.00, 1)
            
            costo = tramite_repository.get_costo_for_tramite('ACTA DE DEFUNCION', 1)
            assert costo == 35.00
    
    def test_actualizar_costo_tramite(self, app, init_database):
        """Test actualizar costo predefinido."""
        with app.app_context():
            from ARCHIVOS.database import tramite_repository
            
            tramite_repository.set_costo('RFC', 20.00, 1)
            tramite_repository.set_costo('RFC', 25.00, 1)
            
            costo = tramite_repository.get_costo_for_tramite('RFC', 1)
            assert costo == 25.00
