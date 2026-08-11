import pandas as pd

from churn_prediction.transform.binary_encoder import BinaryEncoder
from churn_prediction.transform import constants


def test_maps_yes_no_to_1_0():
    df = pd.DataFrame(
        {
            "partner": ["Yes", "No"],
            "dependents": ["No", "Yes"],
            "untouched": ["x", "y"],
        }
    )
    enc = BinaryEncoder(cols=["partner", "dependents"])
    out = enc.fit_transform(df)
    assert out["partner"].tolist() == [1, 0]
    assert out["dependents"].tolist() == [0, 1]
    assert out["untouched"].tolist() == ["x", "y"]


def test_default_uses_constants_binary_cols():
    df = pd.DataFrame({c: ["Yes"] for c in constants.BINARY_COLS})
    out = BinaryEncoder().fit_transform(df)
    for c in constants.BINARY_COLS:
        assert out[c].iloc[0] == 1
