"""Tests for _serialize_df NaN handling in run_engine."""
import json
import math
import pandas as pd


class TestSerializeNaN:
    """Verify NaN values in indicator DataFrames serialize to valid JSON."""

    def _serialize_df(self, df):
        """Copy of _serialize_df logic from run_engine._exec_stock_scan."""
        out = []
        for row in df.to_dict(orient="records"):
            clean = {}
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    clean[k] = v.isoformat()
                elif hasattr(v, "item"):
                    try:
                        val = v.item()
                        if isinstance(val, float) and math.isnan(val):
                            val = None
                        clean[k] = val
                    except Exception:
                        clean[k] = str(v)
                elif isinstance(v, float):
                    import math as _math
                    clean[k] = None if _math.isnan(v) else v
                else:
                    clean[k] = v
            out.append(clean)
        return out

    def test_nan_converted_to_none(self):
        """NaN values become None, not 'NaN'."""
        df = pd.DataFrame({"close": [100.0], "J": [float("nan")]})
        data = self._serialize_df(df)
        assert data[0]["J"] is None

    def test_serialized_json_is_valid(self):
        """Output can be json.loads without error."""
        df = pd.DataFrame({"close": [100.0], "K": [float("nan")]})
        data = self._serialize_df(df)
        result = json.dumps(data)
        parsed = json.loads(result)
        assert parsed[0]["K"] is None

    def test_multiple_rows_with_nan(self):
        """NaN handled across all rows."""
        df = pd.DataFrame({
            "close": [100.0, 200.0],
            "K": [50.0, float("nan")],
            "D": [float("nan"), 40.0],
        })
        data = self._serialize_df(df)
        assert data[0]["D"] is None
        assert data[0]["K"] == 50.0
        assert data[1]["K"] is None
        assert data[1]["D"] == 40.0

    def test_boolean_values_preserved(self):
        """Boolean columns (is_bull_zone) stay boolean."""
        df = pd.DataFrame({
            "close": [100.0],
            "is_bull_zone": [True],
        })
        data = self._serialize_df(df)
        assert data[0]["is_bull_zone"] is True

    def test_normal_values_unchanged(self):
        """Non-NaN float values stay as numbers."""
        df = pd.DataFrame({
            "close": [100.0],
            "K": [53.4],
            "D": [49.2],
            "J": [58.0],
        })
        data = self._serialize_df(df)
        assert data[0]["K"] == 53.4
        assert data[0]["D"] == 49.2
        assert data[0]["J"] == 58.0

    def test_full_roundtrip(self):
        """DataFrame → serialize → json.dumps → json.loads preserves data."""
        df = pd.DataFrame({
            "close": [100.0, 200.0],
            "K": [53.4, float("nan")],
            "is_bull_zone": [True, False],
        })
        serialized = self._serialize_df(df)
        result = json.loads(json.dumps(serialized))
        assert len(result) == 2
        assert result[0]["close"] == 100.0
        assert result[0]["K"] == 53.4
        assert result[0]["is_bull_zone"] is True
        assert result[1]["close"] == 200.0
        assert result[1]["K"] is None
        assert result[1]["is_bull_zone"] is False
