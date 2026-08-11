import pandas as pd

from churn_prediction.transform.structural_encoder import StructuralEncoder
from churn_prediction.transform import constants


def test_maps_all_four_values():
    df = pd.DataFrame(
        {
            "online_security": ["Yes", "No", "No internet service", "Yes"],
            "multiple_lines": ["Yes", "No phone service", "No", "No"],
            "untouched_col": ["a", "b", "c", "d"],
        }
    )
    enc = StructuralEncoder(cols=["online_security", "multiple_lines"])
    out = enc.fit_transform(df)

    assert out["online_security"].tolist() == [1, 0, -1, 1]
    assert out["multiple_lines"].tolist() == [1, -1, 0, 0]
    # kolom di luar `cols` tidak tersentuh
    assert out["untouched_col"].tolist() == ["a", "b", "c", "d"]


def test_only_cols_present_are_touched():
    df = pd.DataFrame({"online_security": ["Yes", "No"]})
    # kolom 'multiple_lines' diminta tapi tidak ada di df -- tidak boleh error
    enc = StructuralEncoder(cols=["online_security", "multiple_lines"])
    out = enc.fit_transform(df)
    assert enc.cols_present_ == ["online_security"]
    assert out["online_security"].tolist() == [1, 0]


def test_all_structural_cols_from_constants():
    row = {c: "Yes" for c in constants.STRUCTURAL_COLS}
    df = pd.DataFrame([row])
    enc = StructuralEncoder(cols=constants.STRUCTURAL_COLS)
    out = enc.fit_transform(df)
    for c in constants.STRUCTURAL_COLS:
        assert out[c].iloc[0] == 1
