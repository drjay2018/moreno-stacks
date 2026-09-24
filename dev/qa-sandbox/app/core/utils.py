def dt_args(request, search_cols, sort_cols=None, active_prefix=""):
    """
    Parsea los argumentos de DataTables Server-Side Processing desde el request de Flask
    y construye dinámicamente las sentencias WHERE y ORDER BY.
    """
    is_dt = 'draw' in request.args
    order_clause = ""
    
    if is_dt:
        draw = request.args.get('draw', 1, type=int)
        offset = request.args.get('start', 0, type=int)
        raw_limit = request.args.get('length', 10, type=int)
        limit = min(raw_limit, 500) if raw_limit > 0 else 500
        buscar = request.args.get('search[value]', '').strip()
        
        if sort_cols:
            order_col_idx = request.args.get('order[0][column]', type=int)
            order_dir = request.args.get('order[0][dir]', 'asc').upper()
            if order_dir not in ['ASC', 'DESC']:
                order_dir = 'ASC'
            if order_col_idx is not None and 0 <= order_col_idx < len(sort_cols):
                col = sort_cols[order_col_idx]
                if col:
                    order_clause = f"ORDER BY {col} {order_dir}"
    else:
        draw = None
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('per_page', 10, type=int), 200)  # Cap máximo 200
        offset = (page - 1) * limit
        buscar = request.args.get('buscar', '').strip()
    
    where = ""
    params = {}
    
    if buscar:
        clauses = [f"{col} LIKE :b" for col in search_cols]
        where = "WHERE (" + " OR ".join(clauses) + ")"
        params['b'] = f"%{buscar}%"
    
    return is_dt, draw, where, params, limit, offset, order_clause
