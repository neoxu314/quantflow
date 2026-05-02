def test_create_app():
    """App includes all routes."""
    from quantflow.web.server import create_app

    app = create_app()
    routes = [r.path for r in app.routes]

    assert "/api/config" in routes
    assert "/api/strategies" in routes
    assert "/api/watchlists" in routes
    assert "/api/watchlists/{filename:path}" in routes
    assert "/api/watchlists/search" in routes
    assert "/api/tasks" in routes
    assert "/api/tasks/{task_id}" in routes
