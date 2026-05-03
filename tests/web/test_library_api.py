"""Tests for Library API endpoints."""
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestLibraryStrategiesEndpoint:
    def test_endpoint_exists(self):
        from quantflow.web.api.library import router

        assert "/api/library/strategies" in [r.path for r in router.routes]
        assert "/api/library/indicators" in [r.path for r in router.routes]
        assert "/api/library/indicators/params" in [r.path for r in router.routes]

    def test_returns_strategy_list(self):
        from quantflow.web.api.library import router

        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/library/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data
        assert len(data["strategies"]) >= 4

    def test_strategy_has_all_fields(self):
        from quantflow.web.api.library import router

        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/library/strategies").json()
        required = {"id", "name", "type", "description", "min_lookback_days", "required_indicators"}
        for strat in resp["strategies"]:
            missing = required - set(strat.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_strategy_types_correct(self):
        from quantflow.web.api.library import router

        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/library/strategies").json()
        by_type = {s["type"] for s in resp["strategies"]}
        assert "buy" in by_type
        assert "sell" in by_type

    def test_strategy_descriptions_not_empty(self):
        # Ensure every strategy has a non-trivial description to catch missing docstrings
        from quantflow.web.api.library import router

        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/library/strategies").json()
        for strat in resp.get("strategies", []):
            assert "description" in strat
            assert isinstance(strat["description"], str)
            assert len(strat["description"]) > 10


class TestLibraryIndicatorsEndpoint:
    def test_returns_indicator_list(self):
        from quantflow.web.api.library import router

        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/library/indicators")
        assert resp.status_code == 200
        data = resp.json()
        assert "indicators" in data
        assert len(data["indicators"]) == 8

    def test_indicator_has_all_fields(self):
        from quantflow.web.api.library import router

        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/library/indicators").json()
        required = {"name", "category", "params", "required_fields", "output_fields", "lookback_bars"}
        for ind in resp["indicators"]:
            missing = required - set(ind.keys())
            assert not missing, f"Missing keys: {missing}"


class TestLibraryIndicatorParamsEndpoint:
    def test_update_params(self, tmp_path):
        from quantflow.web.api import library as library_module

        test_yaml = tmp_path / "indicators.yaml"
        test_yaml.write_text("indicators:\n  KDJ:\n    enabled: true\n    params:\n      n: 9\n      m1: 3\n      m2: 3\n")

        with patch.object(library_module, "INDICATORS_YAML", test_yaml):
            app = FastAPI()
            app.include_router(library_module.router)
            resp = TestClient(app).put("/api/library/indicators/params", json={
                "name": "KDJ",
                "params": {"n": 12, "m1": 3, "m2": 3},
            })
            assert resp.status_code == 200
            assert resp.json()["success"] is True

            with open(test_yaml) as f:
                data = yaml.safe_load(f)
            assert data["indicators"]["KDJ"]["params"]["n"] == 12

    def test_update_params_preserves_yaml_structure(self, tmp_path):
        # Create a YAML with multiple indicators and patch INDICATORS_YAML
        from quantflow.web.api import library as library_module
        test_yaml = tmp_path / "indicators.yaml"
        test_yaml.write_text(
            "indicators:\n  KDJ:\n    enabled: true\n    params:\n      n: 9\n      m1: 3\n      m2: 3\n  MACD:\n    enabled: false\n    params:\n      fast: 12\n      slow: 26\n      signal: 9\n"
        )

        with patch.object(library_module, "INDICATORS_YAML", test_yaml):
            app = FastAPI()
            app.include_router(library_module.router)
            resp = TestClient(app).put("/api/library/indicators/params", json={
                "name": "KDJ",
                "params": {"n": 12, "m1": 3, "m2": 3},
            })
            assert resp.status_code == 200
            assert resp.json()["success"] is True

            # Read back YAML and verify structure and values
            data = yaml.safe_load(test_yaml.read_text())
            assert data["indicators"]["KDJ"]["params"]["n"] == 12
            # MACD unchanged
            assert data["indicators"]["MACD"]["enabled"] is False
            assert data["indicators"]["MACD"]["params"]["fast"] == 12
            # Structure remains nested under indicators -> KDJ -> {enabled, params}
            assert isinstance(data["indicators"]["KDJ"], dict)
            assert "enabled" in data["indicators"]["KDJ"]
            assert "params" in data["indicators"]["KDJ"]
            # Valid YAML parse against non-string expansions
            _ = yaml.safe_load(test_yaml.read_text())

    def test_indicator_params_roundtrip_preserves_fields(self, tmp_path):
        # Ensure that non-scalar list parameters are preserved as YAML lists
        from quantflow.web.api import library as library_module
        test_yaml = tmp_path / "indicators.yaml"
        test_yaml.write_text(
            "indicators:\n  VolumeMA:\n    enabled: true\n    params:\n      periods: [5, 10, 20]\n"
        )

        with patch.object(library_module, "INDICATORS_YAML", test_yaml):
            app = FastAPI()
            app.include_router(library_module.router)
            resp = TestClient(app).put("/api/library/indicators/params", json={
                "name": "VolumeMA",
                "params": {"periods": [10, 20, 30]},
            })
            assert resp.status_code == 200
            assert resp.json()["success"] is True

            data = yaml.safe_load(test_yaml.read_text())
            periods = data["indicators"]["VolumeMA"]["params"]["periods"]
            assert isinstance(periods, list)
            assert periods == [10, 20, 30]

    def test_indicator_params_read_after_write(self, tmp_path):
        """GET after PUT reflects updated params immediately."""
        from quantflow.web.api import library as library_module
        test_yaml = tmp_path / "indicators.yaml"
        test_yaml.write_text(
            "indicators:\n  KDJ:\n    enabled: true\n    params:\n      n: 9\n      m1: 3\n      m2: 3\n"
        )

        with patch.object(library_module, "INDICATORS_YAML", test_yaml):
            app = FastAPI()
            app.include_router(library_module.router)
            client = TestClient(app)

            # Step 1: GET confirms initial params
            resp = client.get("/api/library/indicators").json()
            kdj = next(i for i in resp["indicators"] if i["name"] == "KDJ")
            assert kdj["params"]["n"] == 9

            # Step 2: PUT to change n from 9 to 15
            resp = client.put("/api/library/indicators/params", json={
                "name": "KDJ",
                "params": {"n": 15, "m1": 3, "m2": 3},
            })
            assert resp.status_code == 200

            # Step 3: GET again - params must reflect the new value
            resp = client.get("/api/library/indicators").json()
            kdj = next(i for i in resp["indicators"] if i["name"] == "KDJ")
            assert kdj["params"]["n"] == 15

            # Step 4: Verify YAML file has the updated value
            with open(test_yaml) as f:
                data = yaml.safe_load(f)
            assert data["indicators"]["KDJ"]["params"]["n"] == 15
