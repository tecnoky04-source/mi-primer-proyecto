# database.py - Repositories for DocuExpress
"""
Este módulo implementa el Patrón Repositorio para el acceso a datos.
Cada repositorio es responsable de la lógica de negocio de un único modelo,
asegurando un código limpio, mantenible y desacoplado de la capa de rutas.
"""

from .models import db, User, Papeleria, Tramite, Gasto, Proveedor, TramiteCosto, PapeleriaPrecio
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, case
from datetime import datetime
import logging

from .constants import TRAMITES_PREDEFINIDOS

class UserRepository:
    """
    Repository for User related operations.
    """
    def create(self, username, password, role='employee'):
        """Creates a new user."""
        if User.query.filter_by(username=username).first():
            raise ValueError(f"El usuario '{username}' ya existe.")
        
        new_user = User(username=username, role=role)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        return new_user

    def get_by_username(self, username):
        """Gets a user by username."""
        return User.query.filter_by(username=username).first()

    def get_by_id(self, user_id):
        """Gets a user by id."""
        return db.session.get(User, user_id)

    def get_all_except(self, admin_user_id):
        """Gets all users except the given admin."""
        return User.query.filter(User.id != admin_user_id).order_by(User.username).all()

    def update_password(self, user_id, new_password):
        """Updates a user's password."""
        user = self.get_by_id(user_id)
        if user:
            user.set_password(new_password)
            db.session.commit()
    def update(self, user_id, username, role, password=None):
        """Updates a user's details."""
        user = self.get_by_id(user_id)
        if user:
            user.username = username
            user.role = role
            if password:
                user.set_password(password)
            db.session.commit()
            return user
        return None

    def delete(self, user_id):
        """Deletes a user."""
        user = self.get_by_id(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            return True
        return False

class PapeleriaRepository:
    """Repository for Papeleria and PapeleriaPrecio related operations."""

    def add(self, nombre, user_id):
        """
        Adds a new papeleria. It checks for active duplicates but allows reactivating
        a soft-deleted papeleria with the same name.
        """
        normalized_nombre = nombre.strip().upper()

        # 1. Verificar si ya existe una papelería ACTIVA con el mismo nombre.
        existing_active = Papeleria.query.filter_by(
            nombre=normalized_nombre, user_id=user_id, is_active=True
        ).first()

        if existing_active:
            raise ValueError(f"La papelería '{nombre}' ya existe y está activa.")

        # 2. Verificar si existe una papelería INACTIVA con el mismo nombre (soft-deleted)
        existing_inactive = Papeleria.query.filter_by(
            nombre=normalized_nombre, user_id=user_id, is_active=False
        ).first()

        if existing_inactive:
            # Reactivar la papelería existente
            existing_inactive.is_active = True
            db.session.commit()
            return existing_inactive

        # 3. Si no existe ninguna (ni activa ni inactiva), crear una nueva.
        try:
            new_papeleria = Papeleria(nombre=normalized_nombre, user_id=user_id, is_active=True)
            db.session.add(new_papeleria)
            db.session.commit()
            return new_papeleria
        except IntegrityError as e:
            db.session.rollback()
            logging.error(f"Error de integridad al crear papelería '{normalized_nombre}': {e}")
            raise ValueError(f"Error inesperado al crear la papelería. Es posible que ya exista un registro con este nombre.")

    def get_papelerias_and_totals_for_user(self, user_id, search_term=None):
        """
        Lists all papelerias for a user with their stats and calculates grand totals.
        This is more efficient as it runs in a single query.
        """
        # Subquery to get stats per papeleria
        papeleria_stats_sq = db.session.query(
            Tramite.papeleria_id,
            func.count(Tramite.id).label('cuantos'),
            func.sum(Tramite.precio).label('total_ingresos'),
            func.sum(Tramite.costo).label('total_costos')
        ).filter(Tramite.user_id == user_id).group_by(Tramite.papeleria_id).subquery()

        # Main query to get papelerias and join the stats
        query = db.session.query(
            Papeleria.id,
            Papeleria.nombre,
            func.coalesce(papeleria_stats_sq.c.cuantos, 0).label('cuantos'),
            func.coalesce(papeleria_stats_sq.c.total_ingresos, 0).label('total_ingresos'),
            func.coalesce(papeleria_stats_sq.c.total_costos, 0).label('total_costos'),
            (func.coalesce(papeleria_stats_sq.c.total_ingresos, 0) - func.coalesce(papeleria_stats_sq.c.total_costos, 0)).label('ganancia_total')
        ).filter(Papeleria.is_active == True).outerjoin(papeleria_stats_sq, Papeleria.id == papeleria_stats_sq.c.papeleria_id)\
         .filter(Papeleria.user_id == user_id)

        if search_term:
            query = query.filter(Papeleria.nombre.like(f'%{search_term}%'))

        papelerias = query.order_by(Papeleria.nombre).all()
        
        # Calculate totals from the retrieved papelerias list
        total_cuantos = sum(p.cuantos for p in papelerias)
        total_ingresos = sum(p.total_ingresos for p in papelerias)
        total_costos = sum(p.total_costos for p in papelerias)
        total_ganancia = total_ingresos - total_costos

        totales = {
            'cuantos': total_cuantos,
            'total_ingresos': total_ingresos,
            'total_costos': total_costos,
            'ganancia': total_ganancia
        }
        
        return {'papelerias': papelerias, 'totales': totales}
    
    def get_totales_comparativa(self, user_id):
        """Retorna totales del mes actual vs mes anterior con porcentajes de cambio."""
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        # Mes actual
        hoy = date.today()
        inicio_mes_actual = hoy.replace(day=1)
        
        # Mes anterior
        inicio_mes_anterior = inicio_mes_actual - relativedelta(months=1)
        fin_mes_anterior = inicio_mes_actual - relativedelta(days=1)
        
        # Datos mes actual
        datos_actual = db.session.query(
            func.sum(Tramite.precio).label('ingresos'),
            func.sum(Tramite.costo).label('costos')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(
            Tramite.user_id == user_id,
            Papeleria.is_active == True,
            Tramite.fecha >= inicio_mes_actual
        ).first()
        
        # Datos mes anterior
        datos_anterior = db.session.query(
            func.sum(Tramite.precio).label('ingresos'),
            func.sum(Tramite.costo).label('costos')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(
            Tramite.user_id == user_id,
            Papeleria.is_active == True,
            Tramite.fecha >= inicio_mes_anterior,
            Tramite.fecha <= fin_mes_anterior
        ).first()
        
        # Calcular valores
        ingresos_actual = float(datos_actual.ingresos or 0)
        costos_actual = float(datos_actual.costos or 0)
        ganancia_actual = ingresos_actual - costos_actual
        
        ingresos_anterior = float(datos_anterior.ingresos or 0)
        costos_anterior = float(datos_anterior.costos or 0)
        ganancia_anterior = ingresos_anterior - costos_anterior
        
        # Calcular porcentajes de cambio
        def calcular_porcentaje(actual, anterior):
            if anterior == 0:
                return 100 if actual > 0 else 0
            return round(((actual - anterior) / anterior) * 100, 1)
        
        return {
            'ganancia_actual': ganancia_actual,
            'ganancia_anterior': ganancia_anterior,
            'cambio_ganancia': ganancia_actual - ganancia_anterior,
            'porcentaje_ganancia': calcular_porcentaje(ganancia_actual, ganancia_anterior),
            'ingresos_porcentaje': calcular_porcentaje(ingresos_actual, ingresos_anterior),
            'costos_porcentaje': calcular_porcentaje(costos_actual, costos_anterior)
        }

    def get_top_by_ganancia(self, user_id, limit=10, fecha_inicio=None, fecha_fin=None):
        """Gets top papelerias by total profit, optionally filtered by date range."""
        query = db.session.query(
            Papeleria.nombre,
            (func.sum(func.coalesce(Tramite.precio, 0)) - func.sum(func.coalesce(Tramite.costo, 0))).label('ganancia_total') # type: ignore
        ).outerjoin(Tramite, Papeleria.id == Tramite.papeleria_id)\
         .filter(Papeleria.user_id == user_id)\
         .filter(Papeleria.is_active == True)
        
        # Aplicar filtro de fecha si se proporciona
        if fecha_inicio and fecha_fin:
            query = query.filter(Tramite.fecha >= fecha_inicio, Tramite.fecha <= fecha_fin)
        
        query = query.group_by(Papeleria.id, Papeleria.nombre)\
         .order_by(db.desc('ganancia_total'))\
         .limit(limit)
        
        # Convert rows to dictionaries
        return [row._asdict() for row in query.all()]

    def update_name(self, papeleria_id, nuevo_nombre, user_id):
        """Updates the name of a papeleria."""
        papeleria = Papeleria.query.filter_by(id=papeleria_id, user_id=user_id, is_active=True).first()
        if papeleria:
            papeleria.nombre = nuevo_nombre.strip().upper()
            db.session.commit()

    def delete(self, papeleria_id, user_id):
        """Soft deletes a papeleria by setting is_active to False."""
        papeleria = Papeleria.query.filter_by(id=papeleria_id, user_id=user_id, is_active=True).first()
        if papeleria:
            papeleria.is_active = False
            db.session.commit()

    def exists_with_name(self, nombre, user_id, papeleria_id_to_exclude=None):
        """Checks if an *active* papeleria with the given name already exists for the user."""
        query = Papeleria.query.filter_by(nombre=nombre.strip().upper(), user_id=user_id, is_active=True)
        if papeleria_id_to_exclude:
            query = query.filter(Papeleria.id != papeleria_id_to_exclude)
        return query.first() is not None

    def get_name(self, papeleria_id, user_id):
        """Gets the name of a papeleria."""
        papeleria = Papeleria.query.filter_by(id=papeleria_id, user_id=user_id, is_active=True).first()
        return papeleria.nombre if papeleria else None

    def set_precios_bulk(self, papeleria_id, precios_data, user_id):
        """
        Sets or updates multiple prices for a papeleria in a single, efficient transaction.
        'precios_data' is a dictionary of {'tramite_name': 'price_string'}.
        """
        logging.info(f"set_precios_bulk iniciado para papeleria_id={papeleria_id}")
        if not Papeleria.query.filter_by(id=papeleria_id, user_id=user_id, is_active=True).first():
            logging.warning("Intento de acceso no autorizado o papelería no existe.")
            return None, ["La papelería no existe o no tienes permiso."]

        errors = []
        valid_precios = {}
        for tramite, precio_str in precios_data.items():
            # Ignorar campos vacíos
            if not precio_str or not str(precio_str).strip():
                continue
            
            try:
                # Permitir precios de 0 pero no negativos
                precio = float(precio_str)
                if precio < 0:
                    errors.append(f"El precio para '{tramite}' no puede ser negativo.")
                else:
                    valid_precios[tramite] = precio
            except (ValueError, TypeError):
                errors.append(f"El precio para '{tramite}' ('{precio_str}') no es un número válido.")

        if errors:
            logging.warning(f"Errores de validación: {errors}")
            return None, errors

        try:
            logging.info("Validación exitosa. Iniciando transacción de base de datos.")
            # 1. Obtener precios existentes en una sola consulta para eficiencia
            existing_precios_objs = PapeleriaPrecio.query.filter_by(papeleria_id=papeleria_id).all()
            existing_precios_map = {p.tramite: p for p in existing_precios_objs}

            # 2. Iterar sobre los precios validados y actualizar o crear según sea necesario
            logging.info(f"Procesando {len(valid_precios)} precios válidos.")
            for tramite, precio in valid_precios.items():
                precio_obj = existing_precios_map.get(tramite)
                if precio_obj:
                    # Actualizar precio existente
                    precio_obj.precio = precio
                else:
                    # Crear nuevo registro de precio
                    new_precio = PapeleriaPrecio(papeleria_id=papeleria_id, tramite=tramite, precio=precio)
                    db.session.add(new_precio)
            
            # 3. Confirmar todos los cambios en la base de datos
            logging.info(f"A punto de hacer commit para {len(valid_precios)} precios.")
            db.session.commit()
            logging.info("Commit exitoso.")

        except Exception as e:
            logging.error(f"Excepción durante el commit: {e}", exc_info=True)
            db.session.rollback()
            return None, [f"Error al guardar en la base de datos. Detalles: {e}"]

        logging.info("set_precios_bulk completado exitosamente.")
        # Devolver precios actualizados y una lista de errores vacía en caso de éxito
        return valid_precios, []

    def get_default_precio(self, papeleria_id, tramite, user_id):
        """Gets the default price for a tramite."""
        precio_obj = PapeleriaPrecio.query.join(Papeleria).filter(
            PapeleriaPrecio.papeleria_id == papeleria_id, Papeleria.is_active == True,
            PapeleriaPrecio.tramite == tramite,
            Papeleria.user_id == user_id
        ).first()
        return precio_obj.precio if precio_obj else None

    def get_precios_para_papeleria(self, papeleria_id, user_id):
        """Gets all prices and costs for a given papeleria."""
        
        costos_generales = {c.tramite: c.costo for c in TramiteCosto.query.filter_by(user_id=user_id).all()}
        precios_especificos = {p.tramite: p.precio for p in PapeleriaPrecio.query.join(Papeleria).filter(PapeleriaPrecio.papeleria_id == papeleria_id, Papeleria.is_active == True).all()}
        
        todos_los_tramites = sorted(list(set(TRAMITES_PREDEFINIDOS) | set(costos_generales.keys()) | set(precios_especificos.keys())))
        
        return {tramite: {'costo_general': costos_generales.get(tramite), 'precio_especifico': precios_especificos.get(tramite)} for tramite in todos_los_tramites}

    def total_por_papeleria(self, papeleria_id, user_id, fecha_inicio=None, fecha_fin=None):
        """Calculates totals for a specific papeleria."""
        query = db.session.query(
            func.count(Tramite.id).label('cuantos'), # type: ignore
            func.sum(func.coalesce(Tramite.precio, 0)).label('total_ingresos'),
            func.sum(func.coalesce(Tramite.costo, 0)).label('total_costos')
        ).filter(Tramite.papeleria_id == papeleria_id, Tramite.user_id == user_id)

        if fecha_inicio and fecha_fin:
            query = query.filter(Tramite.fecha.between(fecha_inicio, fecha_fin))

        result = query.one()
        
        ingresos = float(result.total_ingresos or 0)
        costos = float(result.total_costos or 0)
        
        return {
            'cuantos': result.cuantos or 0,
            'total_ingresos': ingresos,
            'total_costos': costos,
            'ganancia': ingresos - costos
        }
    
    def get_all_papelerias(self, user_id):
        """Gets all active papelerias for search functionality."""
        papelerias = db.session.query(
            Papeleria.id,
            Papeleria.nombre
        ).filter(
            Papeleria.user_id == user_id,
            Papeleria.is_active == True
        ).order_by(Papeleria.nombre).all()
        
        result = []
        for p in papelerias:
            # Contar precios configurados
            precios_count = PapeleriaPrecio.query.filter_by(papeleria_id=p.id).count()
            result.append({
                'id': p.id,
                'nombre': p.nombre,
                'precios': [{'tramite': '', 'precio': 0}] * precios_count  # Lista simulada para el count
            })
        
        return result

class TramiteRepository:
    """Repository for Tramite and TramiteCosto related operations."""

    def add_bulk(self, papeleria_id, tramite, user_id, fecha, precio, costo, cantidad):
        """Registers multiple tramites in a single transaction."""
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")

        for _ in range(cantidad):
            new_tramite = Tramite(
                papeleria_id=papeleria_id,
                tramite=tramite,
                user_id=user_id,
                fecha=fecha_dt,
                precio=float(precio),
                costo=float(costo)
            )
            db.session.add(new_tramite)
        db.session.commit()

    def get_by_id(self, tramite_id, user_id):
        """Gets a single tramite by its ID."""
        return Tramite.query.filter_by(id=tramite_id, user_id=user_id).first()

    def update(self, tramite_id, user_id, fecha, tramite, precio, costo):
        """Updates an existing tramite."""
        tramite_obj = self.get_by_id(tramite_id, user_id)
        if tramite_obj:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
            tramite_obj.fecha = fecha_dt
            tramite_obj.tramite = tramite
            tramite_obj.precio = float(precio)
            tramite_obj.costo = float(costo)
            db.session.commit()

    def delete(self, tramite_id, user_id):
        """Deletes a tramite and returns the associated papeleria_id."""
        tramite = self.get_by_id(tramite_id, user_id)
        if tramite:
            papeleria_id = tramite.papeleria_id
            db.session.delete(tramite)
            db.session.commit()
            return papeleria_id
        return None

    def get_details_for_papeleria(self, papeleria_id, user_id, fecha_inicio=None, fecha_fin=None, page=1, per_page=20):
        """Gets a paginated list of tramites for a specific papeleria."""
        query = Tramite.query.join(Papeleria).filter(Tramite.papeleria_id == papeleria_id, Tramite.user_id == user_id, Papeleria.is_active == True)

        if fecha_inicio and fecha_fin:
            query = query.filter(Tramite.fecha.between(fecha_inicio, fecha_fin))

        pagination = query.order_by(Tramite.fecha.desc(), Tramite.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
        return pagination.items, pagination.total, pagination.pages

    def get_total_general(self, user_id, fecha_inicio=None, fecha_fin=None):
        """Calculates grand totals for a user."""
        query = db.session.query(
            func.count(Tramite.id).label('cuantos'), # type: ignore
            func.sum(func.coalesce(Tramite.precio, 0)).label('total_ingresos'),
            func.sum(func.coalesce(Tramite.costo, 0)).label('total_costos')
        ).filter(Tramite.user_id == user_id)

        if fecha_inicio and fecha_fin:
            query = query.filter(Tramite.fecha.between(fecha_inicio, fecha_fin))

        result = query.one()
        ingresos = float(result.total_ingresos or 0)
        costos = float(result.total_costos or 0)
        return {
            'cuantos': result.cuantos or 0,
            'total_ingresos': ingresos,
            'total_costos': costos,
            'ganancia': ingresos - costos
        }

    def get_tramites_hoy(self, user_id):
        """Returns the number of tramites registered today."""
        hoy_str = datetime.now().strftime("%Y-%m-%d")
        return Tramite.query.filter(Tramite.fecha == hoy_str, Tramite.user_id == user_id).count()
    
    def get_all_tramites(self, user_id, limit=100):
        """Gets recent tramites for search functionality."""
        tramites = db.session.query(
            Tramite.id,
            Tramite.tramite,
            Tramite.fecha,
            Tramite.precio,
            Tramite.costo,
            (Tramite.precio - Tramite.costo).label('ganancia'),
            Papeleria.nombre.label('papeleria')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(Tramite.user_id == user_id, Papeleria.is_active == True)\
         .order_by(Tramite.fecha.desc(), Tramite.id.desc())\
         .limit(limit)\
         .all()
        
        return [{
            'id': t.id,
            'tramite': t.tramite,
            'fecha': t.fecha.strftime('%Y-%m-%d') if hasattr(t.fecha, 'strftime') else str(t.fecha),
            'precio': float(t.precio),
            'costo': float(t.costo),
            'ganancia': float(t.ganancia),
            'papeleria': t.papeleria
        } for t in tramites]
    
    def get_tramites_comparativa(self, user_id):
        """Retorna trámites de hoy vs ayer y el porcentaje de cambio."""
        from datetime import timedelta
        hoy = datetime.now().date()
        ayer = hoy - timedelta(days=1)
        
        tramites_hoy = Tramite.query.filter(
            Tramite.fecha == hoy.strftime("%Y-%m-%d"), 
            Tramite.user_id == user_id
        ).count()
        
        tramites_ayer = Tramite.query.filter(
            Tramite.fecha == ayer.strftime("%Y-%m-%d"), 
            Tramite.user_id == user_id
        ).count()
        
        cambio = tramites_hoy - tramites_ayer
        porcentaje = ((cambio / tramites_ayer) * 100) if tramites_ayer > 0 else (100 if tramites_hoy > 0 else 0)
        
        return {
            'hoy': tramites_hoy,
            'ayer': tramites_ayer,
            'cambio': cambio,
            'porcentaje': round(porcentaje, 1)
        }

    def export_all_as_csv(self, user_id):
        """Exports all tramites for a user to be used in a CSV."""
        return db.session.query(
            Papeleria.nombre.label('papeleria'),
            Tramite.tramite,
            Tramite.fecha,
            Tramite.precio,
            Tramite.costo,
            (Tramite.precio - Tramite.costo).label('ganancia')
        ).join(Papeleria, (Tramite.papeleria_id == Papeleria.id) & (Papeleria.is_active == True))\
         .filter(Tramite.user_id == user_id)\
         .order_by(Tramite.fecha.desc())\
         .all()

    def get_all_costos(self, user_id):
        """Gets all defined tramite costs for a user."""
        costos = TramiteCosto.query.filter_by(user_id=user_id).all()
        return {c.tramite: c.costo for c in costos}

    def get_costo_for_tramite(self, tramite, user_id):
        """Gets the cost for a specific tramite."""
        costo = TramiteCosto.query.filter_by(tramite=tramite, user_id=user_id).first()
        return costo.costo if costo else None

    def set_costo(self, tramite, costo, user_id):
        """Sets or updates the default cost for a tramite."""
        costo_obj = TramiteCosto.query.filter_by(tramite=tramite, user_id=user_id).first()
        if costo_obj:
            costo_obj.costo = float(costo)
        else:
            costo_obj = TramiteCosto(tramite=tramite, costo=float(costo), user_id=user_id)
            db.session.add(costo_obj)
        db.session.commit()

    def get_distinct_tramites(self, user_id):
        """Gets a list of all unique tramite names for a user."""
        return [r[0] for r in db.session.query(Tramite.tramite).filter_by(user_id=user_id).distinct().order_by(Tramite.tramite).all()]

    def update_old_costos(self, user_id):
        """Updates the cost of old tramites (where cost is 0) using default cost values."""
        costos_default = self.get_all_costos(user_id)
        if not costos_default:
            return 0
        
        count = 0
        for tramite, costo in costos_default.items():
            updated_rows = Tramite.query.filter_by(tramite=tramite, costo=0, user_id=user_id).update({'costo': costo})
            count += updated_rows
        
        db.session.commit()
        return count

    def get_monthly_summary(self, user_id, fecha_inicio=None, fecha_fin=None):
        """
        Calculates a comprehensive monthly financial summary for the last 12 months.

        This function gathers data from both Tramites (income and costs) and Gastos (expenses)
        to provide a full picture of finances. It ensures that all 12 months in the period
        are present in the result, even if no activity was recorded.

        Args:
            user_id: The ID of the user for whom to generate the summary.
            fecha_inicio: Optional start date for custom range (YYYY-MM-DD string)
            fecha_fin: Optional end date for custom range (YYYY-MM-DD string)

        Returns:
            A dictionary containing:
            - 'monthly_data': A list of dictionaries, one for each of the last 12 months.
              Each dictionary contains 'month', 'ingresos', 'gastos', and 'ganancias'.
            - 'totals': A dictionary with 'total_ingresos', 'total_gastos', and 'total_ganancia'
              for the entire 12-month period.
        """
        from datetime import date, datetime
        from dateutil.relativedelta import relativedelta
        from collections import defaultdict

        # 1. Generate the date range
        if fecha_inicio and fecha_fin:
            # Usar rango personalizado
            start_date = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            end_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            start_date = start_date.replace(day=1)
        else:
            # Usar últimos 12 meses por defecto
            end_date = date.today()
            start_date = end_date - relativedelta(months=11)
            start_date = start_date.replace(day=1)

        months = []
        current_date = start_date
        while current_date <= end_date:
            months.append(current_date.strftime('%Y-%m'))
            current_date += relativedelta(months=1)

        # 2. Get data from Tramites (Ingresos and Costos)
        tramites_query = db.session.query(
            func.strftime('%Y-%m', Tramite.fecha).label('month'),
            func.sum(Tramite.precio).label('total_ingresos'),
            func.sum(Tramite.costo).label('total_costos_tramite')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(
            Tramite.user_id == user_id,
            Papeleria.is_active == True,
            Tramite.fecha >= start_date,
            Tramite.fecha <= end_date
        ).group_by('month').all()

        # 3. Get data from Gastos
        gastos_query = db.session.query(
            func.strftime('%Y-%m', Gasto.fecha).label('month'),
            func.sum(Gasto.monto).label('total_gastos_generales')
        ).filter(
            Gasto.user_id == user_id,
            Gasto.fecha >= start_date,
            Gasto.fecha <= end_date
        ).group_by('month').all()

        # 4. Process and combine data
        monthly_summary = defaultdict(lambda: {'ingresos': 0, 'gastos': 0})

        for row in tramites_query:
            monthly_summary[row.month]['ingresos'] += row.total_ingresos
            monthly_summary[row.month]['gastos'] += row.total_costos_tramite

        for row in gastos_query:
            monthly_summary[row.month]['gastos'] += row.total_gastos_generales
        
        # 5. Build final list and calculate totals
        final_data = []
        total_ingresos = 0
        total_gastos = 0

        for month_str in months:
            data = monthly_summary[month_str]
            ingresos = data['ingresos']
            gastos = data['gastos']
            ganancias = ingresos - gastos
            
            final_data.append({
                'month': month_str,
                'ingresos': ingresos,
                'gastos': gastos,
                'ganancias': ganancias
            })
            
            total_ingresos += ingresos
            total_gastos += gastos
            
        total_ganancia = total_ingresos - total_gastos

        return {
            'monthly_data': final_data,
            'totals': {
                'total_ingresos': total_ingresos,
                'total_gastos': total_gastos,
                'total_ganancia': total_ganancia
            }
        }


    def get_tramites_distribution(self, user_id, limit=10, fecha_inicio=None, fecha_fin=None):
        """Gets the distribution of tramites by count, optionally filtered by date range."""
        query = db.session.query(
            Tramite.tramite.label('tramite_label'),
            func.count(Tramite.id).label('total_count')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(Tramite.user_id == user_id)\
         .filter(Papeleria.is_active == True)
        
        # Aplicar filtro de fecha si se proporciona
        if fecha_inicio and fecha_fin:
            query = query.filter(Tramite.fecha >= fecha_inicio, Tramite.fecha <= fecha_fin)
        
        query = query.group_by(Tramite.tramite)\
         .order_by(db.desc('total_count'))\
         .limit(limit)
        return [row._asdict() for row in query.all()]

    def get_tramites_distribution_for_papeleria(self, papeleria_id, user_id, limit=10):
        """Gets the distribution of tramites for a specific papeleria."""
        query = db.session.query(
            Tramite.tramite.label('tramite_label'), # type: ignore
            func.count(Tramite.id).label('total_count')
        ).filter(Tramite.user_id == user_id, Tramite.papeleria_id == papeleria_id)\
         .group_by(Tramite.tramite)\
         .order_by(db.desc('total_count'))\
         .limit(limit)
        return [row._asdict() for row in query.all()]

    def get_monthly_summary_for_papeleria(self, papeleria_id, user_id):
        """
        Calculates a comprehensive monthly financial summary for a specific papeleria
        over the last 12 months.

        Args:
            papeleria_id: The ID of the papeleria.
            user_id: The ID of the user.

        Returns:
            A dictionary with 'monthly_data' and 'totals'.
        """
        from datetime import date
        from dateutil.relativedelta import relativedelta
        from collections import defaultdict

        # 1. Generate the last 12 months
        end_date = date.today()
        start_date = end_date - relativedelta(months=11)
        start_date = start_date.replace(day=1)

        months = []
        current_date = start_date
        while current_date <= end_date:
            months.append(current_date.strftime('%Y-%m'))
            current_date += relativedelta(months=1)

        # 2. Get data from Tramites for this specific papeleria
        tramites_query = db.session.query(
            func.strftime('%Y-%m', Tramite.fecha).label('month'), # type: ignore
            func.sum(Tramite.precio).label('total_ingresos'),
            func.sum(Tramite.costo).label('total_costos')
        ).filter(
            Tramite.user_id == user_id,
            Tramite.papeleria_id == papeleria_id,
            Tramite.fecha >= start_date,
            Tramite.fecha <= end_date
        ).group_by('month').all()

        # 3. Process data
        monthly_summary = defaultdict(lambda: {'ingresos': 0, 'gastos': 0})
        for row in tramites_query:
            monthly_summary[row.month]['ingresos'] = row.total_ingresos
            monthly_summary[row.month]['gastos'] = row.total_costos

        # 4. Build final list and calculate totals
        final_data = []
        total_ingresos = 0
        total_gastos = 0

        for month_str in months:
            data = monthly_summary[month_str]
            ingresos = data['ingresos']
            gastos = data['gastos']
            ganancias = ingresos - gastos
            
            final_data.append({
                'month': month_str,
                'ingresos': ingresos,
                'gastos': gastos,
                'ganancias': ganancias
            })
            
            total_ingresos += ingresos
            total_gastos += gastos
            
        total_ganancia = total_ingresos - total_gastos

        return {
            'monthly_data': final_data,
            'totals': {
                'total_ingresos': total_ingresos,
                'total_gastos': total_gastos,
                'total_ganancia': total_ganancia
            }
        }

# Instantiate repositories
user_repository = UserRepository()
papeleria_repository = PapeleriaRepository()
tramite_repository = TramiteRepository()

class ProveedorRepository:
    """Repository for Proveedor related operations."""

    def add(self, nombre, user_id):
        try:
            new_proveedor = Proveedor(nombre=nombre.strip().upper(), user_id=user_id)
            db.session.add(new_proveedor)
            db.session.commit()
            return new_proveedor
        except IntegrityError:
            db.session.rollback()
            return None

    def get_all(self, user_id):
        return Proveedor.query.filter_by(user_id=user_id).order_by(Proveedor.nombre).all()

    def get_by_id(self, proveedor_id, user_id):
        return Proveedor.query.filter_by(id=proveedor_id, user_id=user_id).first()

    def update(self, proveedor_id, nombre, user_id):
        proveedor = self.get_by_id(proveedor_id, user_id)
        if proveedor:
            proveedor.nombre = nombre.strip().upper()
            db.session.commit()

    def delete(self, proveedor_id, user_id):
        proveedor = self.get_by_id(proveedor_id, user_id)
        if proveedor:
            db.session.delete(proveedor)
            db.session.commit()

    def is_in_use(self, proveedor_id, user_id):
        return Gasto.query.filter_by(proveedor_id=proveedor_id, user_id=user_id).first() is not None

class GastoRepository:
    """Repository for Gasto related operations."""

    def add(self, proveedor_id, descripcion, monto, fecha, categoria, user_id, receipt_filename=None):
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
        new_gasto = Gasto(
            proveedor_id=proveedor_id,
            descripcion=descripcion,
            monto=float(monto),
            fecha=fecha_dt,
            categoria=categoria,
            user_id=user_id,
            receipt_filename=receipt_filename
        )
        db.session.add(new_gasto)
        db.session.commit()

    def get_all(self, user_id, page=1, per_page=20, fecha_inicio=None, fecha_fin=None, categoria=None):
        query = Gasto.query.filter_by(user_id=user_id)

        if fecha_inicio and fecha_fin:
            query = query.filter(Gasto.fecha.between(fecha_inicio, fecha_fin))

        if categoria:
            query = query.filter_by(categoria=categoria)
        
        pagination = query.join(Proveedor).order_by(Gasto.fecha.desc(), Gasto.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
        return pagination.items, pagination.total
    
    def get_all_gastos(self, user_id, limit=100):
        """Gets recent gastos for search functionality."""
        gastos = db.session.query(
            Gasto.id,
            Gasto.descripcion.label('concepto'),
            Gasto.monto,
            Gasto.fecha,
            Gasto.categoria,
            Proveedor.nombre.label('proveedor')
        ).join(Proveedor, Gasto.proveedor_id == Proveedor.id)\
         .filter(Gasto.user_id == user_id)\
         .order_by(Gasto.fecha.desc(), Gasto.id.desc())\
         .limit(limit)\
         .all()
        
        return [{
            'id': g.id,
            'concepto': g.concepto,
            'monto': float(g.monto),
            'fecha': g.fecha.strftime('%Y-%m-%d') if hasattr(g.fecha, 'strftime') else str(g.fecha),
            'categoria': g.categoria,
            'proveedor': g.proveedor
        } for g in gastos]

    def get_total_gastos(self, user_id):
        """Calculates the total amount of all expenses for a user."""
        return db.session.query(func.sum(Gasto.monto)).filter_by(user_id=user_id).scalar() or 0

    def get_by_id(self, gasto_id, user_id):
        return Gasto.query.filter_by(id=gasto_id, user_id=user_id).first()

    def update(self, gasto_id, user_id, proveedor_id, descripcion, monto, fecha, categoria, receipt_filename=None):
        gasto = self.get_by_id(gasto_id, user_id)
        if gasto:
            gasto.proveedor_id = proveedor_id
            gasto.descripcion = descripcion
            gasto.monto = float(monto)
            gasto.fecha = datetime.strptime(fecha, "%Y-%m-%d")
            gasto.categoria = categoria
            gasto.receipt_filename = receipt_filename
            db.session.commit()

    def delete(self, gasto_id, user_id):
        gasto = self.get_by_id(gasto_id, user_id)
        if gasto:
            db.session.delete(gasto)
            db.session.commit()

    def does_receipt_belong_to_user(self, filename, user_id):
        return Gasto.query.filter_by(receipt_filename=filename, user_id=user_id).first() is not None

    def get_gastos_distribution(self, user_id, fecha_inicio=None, fecha_fin=None):
        """Gets the distribution of gastos by categoria, optionally filtered by date range."""
        query = db.session.query(
            Gasto.categoria,
            func.sum(Gasto.monto).label('total_monto')
        ).filter(Gasto.user_id == user_id)
        
        # Aplicar filtro de fecha si se proporciona
        if fecha_inicio and fecha_fin:
            query = query.filter(Gasto.fecha >= fecha_inicio, Gasto.fecha <= fecha_fin)
        
        query = query.group_by(Gasto.categoria)\
         .order_by(db.desc('total_monto'))
        return [row._asdict() for row in query.all()]

    def get_gastos_summary(self, user_id, fecha_inicio=None, fecha_fin=None, categoria=None):
        """Gets a summary of gastos based on filters."""
        query = db.session.query(
            func.sum(Gasto.monto).label('total')
        ).filter(Gasto.user_id == user_id)

        if fecha_inicio and fecha_fin:
            query = query.filter(Gasto.fecha.between(fecha_inicio, fecha_fin))
        if categoria:
            query = query.filter(Gasto.categoria == categoria)
        
        total = query.scalar() or 0
        return {'total': total}


# ==================== REPOSITORIO DE ANÁLISIS AVANZADO ====================
class AnalyticsRepository:
    """Repositorio para análisis predictivo y métricas avanzadas."""
    
    def get_meta_mensual_progress(self, user_id, meta_objetivo=10000):
        """Calcula el progreso hacia la meta mensual."""
        from datetime import date, timedelta
        from dateutil.relativedelta import relativedelta
        
        hoy = date.today()
        inicio_mes = hoy.replace(day=1)
        
        # Ganancia actual del mes
        resultado = db.session.query(
            func.sum(Tramite.precio - Tramite.costo).label('ganancia_actual')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(
            Tramite.user_id == user_id,
            Papeleria.is_active == True,
            Tramite.fecha >= inicio_mes
        ).first()
        
        ganancia_actual = float(resultado.ganancia_actual or 0)
        porcentaje = (ganancia_actual / meta_objetivo * 100) if meta_objetivo > 0 else 0
        
        # Calcular días restantes hasta el próximo DOMINGO (día de corte)
        # weekday(): 0=Lunes, 1=Martes, 2=Miércoles, 3=Jueves, 4=Viernes, 5=Sábado, 6=Domingo
        dia_actual = hoy.weekday()  # Hoy es miércoles = 2
        
        if dia_actual == 6:  # Si hoy es domingo
            dias_hasta_domingo = 0
        else:
            # Días hasta el próximo domingo: 6 - dia_actual
            dias_hasta_domingo = 6 - dia_actual
        
        # Calcular proyección basada en el mes completo
        dias_transcurridos = (hoy - inicio_mes).days + 1
        dias_en_mes = (hoy.replace(day=28) + relativedelta(days=4)).replace(day=1) - relativedelta(days=1)
        dias_totales = dias_en_mes.day
        
        proyeccion = (ganancia_actual / dias_transcurridos * dias_totales) if dias_transcurridos > 0 else 0
        
        return {
            'ganancia_actual': ganancia_actual,
            'meta_objetivo': meta_objetivo,
            'porcentaje': round(porcentaje, 1),
            'proyeccion': round(proyeccion, 2),
            'dias_restantes': dias_hasta_domingo,  # Cambiado: ahora es hasta el próximo domingo
            'falta': max(0, meta_objetivo - ganancia_actual)
        }
    
    def get_mejor_mes_historico(self, user_id):
        """Obtiene el mejor mes histórico."""
        resultado = db.session.query(
            func.strftime('%Y-%m', Tramite.fecha).label('mes'),
            func.sum(Tramite.precio - Tramite.costo).label('ganancia')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(
            Tramite.user_id == user_id,
            Papeleria.is_active == True
        ).group_by('mes')\
         .order_by(db.desc('ganancia'))\
         .first()
        
        if resultado:
            return {
                'mes': resultado.mes,
                'ganancia': float(resultado.ganancia)
            }
        return None
    
    def get_dias_mas_productivos(self, user_id):
        """Identifica los días de la semana más productivos."""
        # SQLite: 0=Domingo, 1=Lunes, ..., 6=Sábado
        dias_nombres = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
        
        resultado = db.session.query(
            func.strftime('%w', Tramite.fecha).label('dia_semana'),
            func.sum(Tramite.precio - Tramite.costo).label('ganancia_total'),
            func.count(Tramite.id).label('cantidad_tramites')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(
            Tramite.user_id == user_id,
            Papeleria.is_active == True
        ).group_by('dia_semana')\
         .order_by(db.desc('ganancia_total'))\
         .all()
        
        if resultado:
            top_dia = resultado[0]
            dia_num = int(top_dia.dia_semana)
            return {
                'dia_nombre': dias_nombres[dia_num],
                'ganancia': float(top_dia.ganancia_total),
                'tramites': top_dia.cantidad_tramites
            }
        return None
    
    def get_hora_pico(self, user_id):
        """Calcula la hora pico de actividad (requiere timestamp, estimado)."""
        # Por simplicidad, retorna basado en trámites por día
        resultado = db.session.query(
            func.strftime('%H', Tramite.fecha).label('hora'),
            func.count(Tramite.id).label('cantidad')
        ).filter(Tramite.user_id == user_id)\
         .group_by('hora')\
         .order_by(db.desc('cantidad'))\
         .first()
        
        if resultado and resultado.hora:
            return f"{resultado.hora}:00"
        return "10:00"  # Default
    
    def get_margen_promedio(self, user_id):
        """Calcula el margen de ganancia promedio."""
        resultado = db.session.query(
            func.sum(Tramite.precio).label('total_ingresos'),
            func.sum(Tramite.costo).label('total_costos')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(
            Tramite.user_id == user_id,
            Papeleria.is_active == True
        ).first()
        
        if resultado and resultado.total_ingresos:
            ingresos = float(resultado.total_ingresos or 0)
            costos = float(resultado.total_costos or 0)
            margen = ((ingresos - costos) / ingresos * 100) if ingresos > 0 else 0
            return round(margen, 1)
        return 0
    
    def get_costo_promedio_tramite(self, user_id):
        """Calcula el costo promedio por trámite."""
        resultado = db.session.query(
            func.avg(Tramite.costo).label('promedio')
        ).filter(Tramite.user_id == user_id).first()
        
        return round(float(resultado.promedio or 0), 2)
    
    def get_roi_por_papeleria(self, user_id):
        """Calcula ROI por papelería."""
        resultado = db.session.query(
            Papeleria.nombre,
            func.sum(Tramite.precio).label('ingresos'),
            func.sum(Tramite.costo).label('costos'),
            ((func.sum(Tramite.precio) - func.sum(Tramite.costo)) / func.sum(Tramite.costo) * 100).label('roi')
        ).join(Tramite, Papeleria.id == Tramite.papeleria_id)\
         .filter(
            Papeleria.user_id == user_id,
            Papeleria.is_active == True
        ).group_by(Papeleria.id, Papeleria.nombre)\
         .having(func.sum(Tramite.costo) > 0)\
         .order_by(db.desc('roi'))\
         .limit(5)\
         .all()
        
        return [{'nombre': r.nombre, 'roi': round(float(r.roi), 1)} for r in resultado]
    
    def get_rentabilidad_por_tramite(self, user_id):
        """Analiza rentabilidad por tipo de trámite."""
        resultado = db.session.query(
            Tramite.tramite,
            func.count(Tramite.id).label('cantidad'),
            func.avg(Tramite.precio - Tramite.costo).label('margen_promedio'),
            func.sum(Tramite.precio - Tramite.costo).label('ganancia_total')
        ).join(Papeleria, Tramite.papeleria_id == Papeleria.id)\
         .filter(
            Tramite.user_id == user_id,
            Papeleria.is_active == True
        ).group_by(Tramite.tramite)\
         .order_by(db.desc('ganancia_total'))\
         .all()
        
        return [{
            'tramite': r.tramite,
            'cantidad': r.cantidad,
            'margen_promedio': round(float(r.margen_promedio or 0), 2),
            'ganancia_total': round(float(r.ganancia_total or 0), 2)
        } for r in resultado]


proveedor_repository = ProveedorRepository()
tramite_repository = TramiteRepository()
gasto_repository = GastoRepository()
analytics_repository = AnalyticsRepository()
