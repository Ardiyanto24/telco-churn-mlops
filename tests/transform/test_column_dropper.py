import pandas as pd

from churn_prediction.transform.column_dropper import ColumnDropper


def test_drops_configured_columns():
    df = pd.DataFrame({"gender": ["Male"], "total_charges": [100.0], "tenure": [5]})
    dropper = ColumnDropper(cols_to_drop=["gender", "total_charges"])
    out = dropper.fit_transform(df)
    assert list(out.columns) == ["tenure"]


def test_missing_column_does_not_error():
    df = pd.DataFrame({"tenure": [5]})
    dropper = ColumnDropper(cols_to_drop=["gender", "total_charges"])
    out = dropper.fit_transform(df)
    assert list(out.columns) == ["tenure"]
    assert dropper.cols_dropped_ == []
    assert dropper.cols_missing_ == ["gender", "total_charges"]


def test_default_uses_constants_drop_cols():
    df = pd.DataFrame({"gender": ["Male"], "total_charges": [1.0], "tenure": [5]})
    out = ColumnDropper().fit_transform(df)
    assert "gender" not in out.columns
    assert "total_charges" not in out.columns
    assert "tenure" in out.columns


def test_get_feature_names_out_filters_dropped_columns():
    # M1.4 Task 2 (audit Checkpoint 1, Temuan 1): 0% coverage sebelumnya,
    # kedua cabang (input_features=None dan normal) tidak pernah dipanggil.
    dropper = ColumnDropper(cols_to_drop=["gender", "total_charges"])
    dropper.fit(pd.DataFrame({"gender": ["Male"], "total_charges": [1.0], "tenure": [5]}))

    assert dropper.get_feature_names_out(None) is None
    assert dropper.get_feature_names_out(["gender", "total_charges", "tenure"]) == ["tenure"]
