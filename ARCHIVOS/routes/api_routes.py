from flask import Blueprint, jsonify, request
from flask_login import login_required
from flask import current_app

from ..utils import get_effective_user_id, check_papeleria_owner
from ..database import papeleria_repository, tramite_repository, gasto_repository, analytics_repository

api_bp = Blueprint('api', __name__, url_prefix='/api')


from flask_caching import Cache
from flask import current_app


def _get_cache_decorator(timeout=300):
    """Devuelve un decorador cached si la extensión de caché está disponible.

    Si no hay un objeto de caché con método `cached`, devuelve un decorador identidad
    que deja la función sin cambios (fallback seguro en desarrollo).
    """
    cache_obj = getattr(current_app, 'cache', None) or current_app.extensions.get('cache')
    if cache_obj and hasattr(cache_obj, 'cached'):
        return cache_obj.cached(timeout=timeout)

    def _identity(f):
        return f

    return _identity


@api_bp.route('/dashboard-charts')
@login_required
def dashboard_charts_data():
    """Endpoint para obtener datos de gráficos del dashboard."""
    effective_user_id = get_effective_user_id()
    
    # Obtener parámetros de fecha si existen
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    # 1. Top Papelerías
    top_papelerias = papeleria_repository.get_top_by_ganancia(
        effective_user_id, 
        limit=10,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )
    top_papelerias_data = {'labels': [p['nombre'] for p in top_papelerias], 'data': [p['ganancia_total'] or 0 for p in top_papelerias]}

    # 2. Resumen Mensual
    summary_result = tramite_repository.get_monthly_summary(
        effective_user_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )
    monthly_summary_data = summary_result['monthly_data']
    
    monthly_summary = {
        'labels': [row['month'] for row in monthly_summary_data],
        'ingresos': [row['ingresos'] for row in monthly_summary_data],
        'costos': [row['gastos'] for row in monthly_summary_data],
        'ganancias': [row['ganancias'] for row in monthly_summary_data],
        'totals': summary_result['totals']
    }

    # 3. Distribución de Trámites
    dist_data = tramite_repository.get_tramites_distribution(
        effective_user_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )
    tramites_dist = {'labels': [row['tramite_label'] for row in dist_data], 'data': [row['total_count'] for row in dist_data]}

    # 4. Distribución de Gastos
    gastos_data = gasto_repository.get_gastos_distribution(
        effective_user_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )
    gastos_dist = {'labels': [row['categoria'] for row in gastos_data], 'data': [row['total_monto'] for row in gastos_data]}

    return jsonify({
        'topPapelerias': top_papelerias_data,
        'monthlySummary': monthly_summary,
        'tramitesDistribution': tramites_dist,
        'gastosDistribution': gastos_dist
    })

@api_bp.route('/test-charts')
def test_charts_data():
    """Endpoint de prueba sin autenticación para verificar gráficos."""
    # Datos de prueba hardcodeados
    return jsonify({
        'topPapelerias': {
            'labels': ['PAPELERIA LOCA', 'PAPELEROA ANGEL', 'PAPELERIA LOE'],
            'data': [870.00, 390.00, 0.00]
        },
        'monthlySummary': {
            'labels': ['2024-01', '2024-02', '2024-03'],
            'ingresos': [1000.00, 1200.00, 800.00],
            'costos': [200.00, 300.00, 150.00],
            'ganancias': [800.00, 900.00, 650.00],
            'totals': {
                'total_ingresos': 3000.00,
                'total_gastos': 650.00,
                'total_ganancia': 2350.00
            }
        },
        'tramitesDistribution': {
            'labels': ['ACTA DE NACIMIENTO', 'ACTA DE MATRIMONIO'],
            'data': [29, 13]
        },
        'gastosDistribution': {
            'labels': ['PAPELERIA'],
            'data': [2400.00]
        }
    })

@api_bp.route('/papeleria-charts/<int:papeleria_id>')
@login_required
@check_papeleria_owner
def papeleria_charts_data(papeleria_id):
    """Endpoint único para los gráficos de la página de detalle de papelería."""
    effective_user_id = get_effective_user_id()
    # 1. Distribución de trámites para esta papelería
    dist_data = tramite_repository.get_tramites_distribution_for_papeleria(papeleria_id, effective_user_id)
    tramites_dist = {'labels': [row['tramite_label'] for row in dist_data], 'data': [row['total_count'] for row in dist_data]}
    # 2. Resumen mensual para esta papelería
    summary_result = tramite_repository.get_monthly_summary_for_papeleria(papeleria_id, effective_user_id)
    monthly_summary_data = summary_result['monthly_data']
    
    monthly_summary = {
        'labels': [row['month'] for row in monthly_summary_data],
        'ingresos': [row['ingresos'] for row in monthly_summary_data],
        'costos': [row['gastos'] for row in monthly_summary_data],
        'ganancias': [row['ganancias'] for row in monthly_summary_data],
        'totals': summary_result['totals']
    }
    
    return jsonify({'tramitesDistribution': tramites_dist, 'monthlySummary': monthly_summary})

@api_bp.route('/gastos-summary')
@login_required
def gastos_summary_data():
    """Endpoint para obtener el resumen de gastos para gráficos."""
    effective_user_id = get_effective_user_id()
    
    # Obtener filtros de la query string
    fecha_inicio = request.args.get('fecha_inicio') or None
    fecha_fin = request.args.get('fecha_fin') or None
    categoria = request.args.get('categoria') or None
    
    summary = gasto_repository.get_gastos_summary(
        user_id=effective_user_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        categoria=categoria
    )
    return jsonify(summary)

@api_bp.route('/get-precio-costo/<int:papeleria_id>/<tramite_nombre>')
@login_required
def get_precio_costo(papeleria_id, tramite_nombre):
    """
    Endpoint optimizado para obtener tanto el precio predefinido para una papelería
    como el costo por defecto de un trámite en una sola llamada.
    """
    effective_user_id = get_effective_user_id()
    
    precio = papeleria_repository.get_default_precio(papeleria_id, tramite_nombre, effective_user_id)
    costo = tramite_repository.get_costo_for_tramite(tramite_nombre, effective_user_id)
    
    return jsonify({
        'precio': f"{precio:.2f}" if precio is not None else '',
        'costo': f"{costo:.2f}" if costo is not None else '0.00'
    })

@api_bp.route('/analytics-avanzado')
@login_required
def analytics_avanzado():
    """Endpoint para obtener análisis avanzados y métricas predictivas."""
    effective_user_id = get_effective_user_id()
    
    return jsonify({
        'meta_progress': analytics_repository.get_meta_mensual_progress(effective_user_id),
        'mejor_mes': analytics_repository.get_mejor_mes_historico(effective_user_id),
        'dia_productivo': analytics_repository.get_dias_mas_productivos(effective_user_id),
        'margen_promedio': analytics_repository.get_margen_promedio(effective_user_id),
        'costo_promedio_tramite': analytics_repository.get_costo_promedio_tramite(effective_user_id),
        'roi_papelerias': analytics_repository.get_roi_por_papeleria(effective_user_id),
        'rentabilidad_tramites': analytics_repository.get_rentabilidad_por_tramite(effective_user_id)
    })

@api_bp.route('/buscar')
@login_required
def buscar():
    """Búsqueda global en trámites, papelerías, gastos y proveedores."""
    # Rate limiting desactivado para búsqueda
    
    from database import tramite_repository, papeleria_repository, gasto_repository
    from flask import request, url_for
    
    query = request.args.get('q', '').lower().strip()
    effective_user_id = get_effective_user_id()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    results = []
    
    # Buscar en trámites (últimos 100)
    tramites = tramite_repository.get_all_tramites(effective_user_id, limit=100)
    for tramite in tramites:
        # Buscar en nombre del trámite, papelería o fecha
        if (query in tramite['tramite'].lower() or 
            query in tramite['papeleria'].lower() or
            query in str(tramite['fecha'])):
            results.append({
                'type': 'tramite',
                'type_label': 'Trámite',
                'title': tramite['tramite'],
                'subtitle': f"{tramite['papeleria']} - {tramite['fecha']} - ${tramite['ganancia']:.2f}",
                'url': url_for('main.index', _anchor='tramites')
            })
    
    # Buscar en papelerías
    papelerias = papeleria_repository.get_all_papelerias(effective_user_id)
    for papeleria in papelerias:
        if query in papeleria['nombre'].lower():
            results.append({
                'type': 'papeleria',
                'type_label': 'Papelería',
                'title': papeleria['nombre'],
                'subtitle': f"Precios configurados: {len(papeleria.get('precios', []))}",
                'url': url_for('papeleria.ver_papeleria', id=papeleria['id'])
            })
    
    # Buscar en gastos (últimos 100)
    gastos = gasto_repository.get_all_gastos(effective_user_id, limit=100)
    for gasto in gastos:
        if (query in gasto['concepto'].lower() or 
            (gasto.get('proveedor') and query in gasto['proveedor'].lower())):
            results.append({
                'type': 'gasto',
                'type_label': 'Gasto',
                'title': gasto['concepto'],
                'subtitle': f"${gasto['monto']:.2f} - {gasto['fecha']} - {gasto.get('proveedor', 'Sin proveedor')}",
                'url': url_for('gastos.index', _anchor='gastos')
            })
    
    # Limitar resultados a 50
    results = results[:50]
    
    return jsonify(results)

@api_bp.route('/notificaciones')
@login_required
def get_notificaciones():
    """Obtener todas las notificaciones del usuario."""
    # Por ahora devolvemos un array vacío
    # En el futuro se pueden implementar notificaciones reales desde la BD
    return jsonify([])

@api_bp.route('/notificaciones/<int:notif_id>/marcar-leida', methods=['POST'])
@login_required
def marcar_notificacion_leida(notif_id):
    """Marcar una notificación como leída."""
    # Por ahora solo retornamos éxito
    return jsonify({'success': True})

@api_bp.route('/notificaciones/marcar-todas-leidas', methods=['POST'])
@login_required
def marcar_todas_leidas():
    """Marcar todas las notificaciones como leídas."""
    # Por ahora solo retornamos éxito
    return jsonify({'success': True})
