import pytest
import pandas as pd

from quantflow.indicators.base import Condition, IndicatorBase


class _ConcreteIndicator(IndicatorBase):
    """Simple concrete indicator used for testing IndicatorBase behavior."""

    @property
    def name(self) -> str:
        return "testindicator"

    @property
    def params(self) -> dict:
        return {}

    def get_required_fields(self) -> list:
        return ["A"]

    def get_output_fields(self) -> list:
        return ["A"]

    @property
    def lookback_bars(self) -> int:
        return 1

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        # No-op calculation for testing
        return df.copy()

    def get_signal_conditions(self) -> list:
        # Default: no signal conditions
        return []


def test_condition_greater_than_field():
    df = pd.DataFrame({"A": [1, 4, 3], "B": [0, 4, 5]})
    c = Condition(field="A", operator=">", value="B")
    assert [c.evaluate(df, i) for i in range(len(df))] == [True, False, False]


def test_condition_greater_than_constant():
    df = pd.DataFrame({"A": [1, 4, 3], "B": [0, 4, 5]})
    c = Condition(field="A", operator=">", value=2)
    assert [c.evaluate(df, i) for i in range(len(df))] == [False, True, True]


def test_condition_less_than_field():
    df = pd.DataFrame({"A": [1, 4, 3], "B": [0, 4, 5]})
    c = Condition(field="A", operator="<", value="B")
    assert [c.evaluate(df, i) for i in range(len(df))] == [False, False, True]


def test_condition_greater_equal_and_less_equal():
    df = pd.DataFrame({"A": [2, 3, 1], "B": [1, 4, 1]})
    c_ge = Condition(field="A", operator=">=", value="B")
    c_le = Condition(field="A", operator="<=", value="B")
    assert [c_ge.evaluate(df, i) for i in range(len(df))] == [True, False, True]
    assert [c_le.evaluate(df, i) for i in range(len(df))] == [False, True, True]


def test_condition_equal():
    df = pd.DataFrame({"A": [1, 2, 3]})
    c = Condition(field="A", operator="==", value=2)
    assert [c.evaluate(df, i) for i in range(len(df))] == [False, True, False]


def test_condition_cross_up():
    df = pd.DataFrame({"A": [1, 3, 5], "B": [2, 1, 4]})
    c = Condition(field="A", operator="cross_up", value="B")
    # row 0: False (no previous row)
    # row 1: 3 > 1 and 1 <= 2 -> True
    # row 2: 5 > 4 but 3 <= 1 is False -> False
    assert [c.evaluate(df, i) for i in range(len(df))] == [False, True, False]


def test_condition_cross_down():
    df = pd.DataFrame({"A": [5, 1, 3], "B": [2, 2, 4]})
    c = Condition(field="A", operator="cross_down", value="B")
    # row 0: False
    # row 1: 1 < 2 and 5 >= 2 -> True
    # row 2: 3 < 4 and 1 >= 2 -> False
    assert [c.evaluate(df, i) for i in range(len(df))] == [False, True, False]


def test_condition_cross_up_row0_false():
    df = pd.DataFrame({"A": [1], "B": [0]})
    c = Condition(field="A", operator="cross_up", value="B")
    assert c.evaluate(df, 0) is False


def test_condition_field_missing_returns_false():
    df = pd.DataFrame({"A": [1, 2, 3]})
    c = Condition(field="X", operator=">", value=0)
    assert all(not c.evaluate(df, i) for i in range(len(df)))


def test_condition_unknown_operator_returns_false():
    df = pd.DataFrame({"A": [1, 2, 3]})
    c = Condition(field="A", operator="!=", value=1)
    assert all(not c.evaluate(df, i) for i in range(len(df)))


def test_condition_greater_equal_constant():
    df = pd.DataFrame({"A": [1, 2, 3]})
    c = Condition(field="A", operator=">=", value=2)
    assert [c.evaluate(df, i) for i in range(len(df))] == [False, True, True]


def test_condition_less_equal_constant():
    df = pd.DataFrame({"A": [1, 2, 3]})
    c = Condition(field="A", operator="<=", value=2)
    assert [c.evaluate(df, i) for i in range(len(df))] == [True, True, False]


def test_get_signals_with_conditions_all_false():
    class _IndicatorHighThreshold(IndicatorBase):
        @property
        def name(self) -> str:
            return "highthr"

        @property
        def params(self) -> dict:
            return {}

        def get_required_fields(self) -> list:
            return ["A"]

        def get_output_fields(self) -> list:
            return ["A"]

        @property
        def lookback_bars(self) -> int:
            return 1

        def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
            return df.copy()

        def get_signal_conditions(self) -> list:
            return [Condition(field="A", operator=">", value=100)]

    ind = _IndicatorHighThreshold()
    df = pd.DataFrame({"A": [0, 10, 50]})
    out = ind.get_signals(df)
    assert out["highthr_signal"].tolist() == [False, False, False]


def test_indicatorbase_is_abstract():
    with pytest.raises(TypeError):
        IndicatorBase()  # type: ignore


def test_indicator_validate_input_true_and_false():
    ind = _ConcreteIndicator()
    df_ok = pd.DataFrame({"A": [1, 2]})
    df_bad = pd.DataFrame({"B": [1, 2]})
    assert ind.validate_input(df_ok) is True
    assert ind.validate_input(df_bad) is False


def test_get_signal_conditions_default_empty():
    ind = _ConcreteIndicator()
    assert ind.get_signal_conditions() == []


def test_get_signals_no_conditions_creates_false_column():
    ind = _ConcreteIndicator()
    df = pd.DataFrame({"A": [0, 1, 2]})
    out = ind.get_signals(df)
    assert "testindicator_signal" in out.columns
    assert out["testindicator_signal"].tolist() == [False, False, False]


def test_get_signals_with_conditions_true():
    class _IndicatorWithCondition(IndicatorBase):
        @property
        def name(self) -> str:
            return "condtest"

        @property
        def params(self) -> dict:
            return {}

        def get_required_fields(self) -> list:
            return ["A"]

        def get_output_fields(self) -> list:
            return ["A"]

        @property
        def lookback_bars(self) -> int:
            return 1

        def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
            return df.copy()

        def get_signal_conditions(self) -> list:
            return [Condition(field="A", operator=">", value=0)]

    ind = _IndicatorWithCondition()
    df = pd.DataFrame({"A": [-1, 1, 2]})
    out = ind.get_signals(df)
    assert out["condtest_signal"].tolist() == [False, True, True]
