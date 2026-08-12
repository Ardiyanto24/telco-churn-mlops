"""Unit test ``inference.registry`` -- Milestone 1.5 Checkpoint 2.

Tiap test memakai tracking URI SQLite terisolasi di ``tmp_path`` (bukan
``constants.DEFAULT_TRACKING_URI`` yang dipakai jalur "nyata" repo) --
supaya nomor versi yang diregistrasi (1, 2, ...) bisa diprediksi/diuji
ulang tanpa terganggu state dari run test sebelumnya.

Skip otomatis kalau artifact asli (`artifacs/`) tidak ada.
"""

from pathlib import Path

import pandas as pd
import pytest

from churn_prediction.inference import registry
from churn_prediction.transform.artifact_loader import DEFAULT_PREPROCESSOR_PATH

pytestmark = pytest.mark.skipif(
    not registry.DEFAULT_MODEL_PATH.exists() or not DEFAULT_PREPROCESSOR_PATH.exists(),
    reason="butuh artifacs/model/model_final.joblib dan artifacs/proprocessor/preprocessor.joblib",
)


def _sample_raw_df():
    return pd.DataFrame([
        dict(
            gender="Female", senior_citizen=0, partner="Yes", dependents="No",
            tenure=29, phone_service="Yes", multiple_lines="No",
            internet_service="DSL", online_security="Yes", online_backup="No",
            device_protection="No", tech_support="No", streaming_tv="No", streaming_movies="No",
            contract="One year", paperless_billing="Yes",
            payment_method="Mailed check", monthly_charges=60.10, total_charges=1653.85,
        ),
    ])


def _tracking_uri(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path.as_posix()}/mlruns_test.db"


def _band_row_df():
    """Baris id=2 dari telco_customers_source (Supabase) -- probability churn
    verified ~0.566 lewat model_final.joblib+preprocessor asli. Sengaja dipilih
    karena jatuh DI ANTARA threshold versi 2 uji (0.5) dan versi 1 (0.6238,
    Keputusan #2/#3 di decisions.md) -- baris ini menghasilkan churn_label
    BERBEDA tergantung versi yang dimuat, bukti load_model_by_version()
    benar-benar version-aware (bukan cache/selalu-versi-terakhir)."""
    return pd.DataFrame([dict(
        gender="Male", senior_citizen=0, partner="Yes", dependents="No",
        tenure=58, phone_service="Yes", multiple_lines="Yes",
        internet_service="Fiber optic", online_security="No", online_backup="Yes",
        device_protection="No", tech_support="No", streaming_tv="Yes", streaming_movies="Yes",
        contract="Month-to-month", paperless_billing="Yes",
        payment_method="Electronic check", monthly_charges=100.40, total_charges=5841.35,
    )])


def test_build_bundle_returns_pipeline_model_threshold():
    bundle = registry.build_bundle()
    assert set(bundle.keys()) == {"pipeline", "model", "threshold"}
    assert bundle["threshold"] == 0.6238
    assert hasattr(bundle["pipeline"], "transform")
    assert hasattr(bundle["model"], "predict_proba")


def test_register_and_load_roundtrip_version_1(tmp_path):
    tracking_uri = _tracking_uri(tmp_path)
    bundle = registry.build_bundle()

    info = registry.register_model(bundle, tracking_uri=tracking_uri)
    assert str(info.registered_model_version) == "1"

    loaded = registry.load_model_by_version("1", tracking_uri=tracking_uri)
    out = loaded.predict(_sample_raw_df())

    assert list(out.columns) == ["churn_probability", "churn_label"]
    assert out["churn_probability"].between(0, 1).all()
    expected_label = int(out["churn_probability"].iloc[0] >= 0.6238)
    assert out["churn_label"].iloc[0] == expected_label


def test_load_by_version_returns_version_appropriate_results(tmp_path):
    """KK3 -- bukti utama Milestone 1.5: mekanisme load-by-version benar-benar
    mengambil versi yang diminta, bukan cache/selalu-versi-terakhir.

    Versi 1 = bundle sungguhan (threshold 0.6238). Versi 2 = bundle uji sengaja
    berbeda (model SAMA, threshold 0.5 -- Keputusan #2, BUKAN kandidat produksi
    sungguhan). Pada baris input yang SAMA (id=2, probability ~0.566): kedua
    versi harus menghasilkan probability IDENTIK (model sama) tapi churn_label
    BERBEDA (0.566 < 0.6238 tapi >= 0.5).
    """
    tracking_uri = _tracking_uri(tmp_path)

    bundle_v1 = registry.build_bundle(threshold=0.6238)
    info_v1 = registry.register_model(bundle_v1, tracking_uri=tracking_uri)
    assert str(info_v1.registered_model_version) == "1"

    bundle_v2 = registry.build_bundle(threshold=0.5)
    info_v2 = registry.register_model(bundle_v2, tracking_uri=tracking_uri)
    assert str(info_v2.registered_model_version) == "2"

    df = _band_row_df()
    out_v1 = registry.load_model_by_version("1", tracking_uri=tracking_uri).predict(df)
    out_v2 = registry.load_model_by_version("2", tracking_uri=tracking_uri).predict(df)

    proba_v1 = out_v1["churn_probability"].iloc[0]
    proba_v2 = out_v2["churn_probability"].iloc[0]
    assert 0.5 < proba_v1 < 0.6238, f"probability {proba_v1} di luar band uji -- fixture perlu diperbarui"
    assert proba_v1 == pytest.approx(proba_v2)

    label_v1 = out_v1["churn_label"].iloc[0]
    label_v2 = out_v2["churn_label"].iloc[0]
    assert label_v1 == 0  # 0.566 < threshold versi 1 (0.6238)
    assert label_v2 == 1  # 0.566 >= threshold versi 2 (0.5)
    assert label_v1 != label_v2


def test_load_active_model_matches_load_by_version_for_aliased_version(tmp_path):
    """KK M2.1 -- round-trip via alias: load_active_model() (alias "champion")
    dan load_model_by_version() untuk versi yang SAMA harus menghasilkan
    prediksi identik pada sample yang sama."""
    tracking_uri = _tracking_uri(tmp_path)
    bundle = registry.build_bundle()
    info = registry.register_model(bundle, tracking_uri=tracking_uri)

    registry.set_active_alias(info.registered_model_version, alias="champion", tracking_uri=tracking_uri)

    df = _sample_raw_df()
    out_alias = registry.load_active_model(alias="champion", tracking_uri=tracking_uri).predict(df)
    out_version = registry.load_model_by_version(
        info.registered_model_version, tracking_uri=tracking_uri
    ).predict(df)

    pd.testing.assert_frame_equal(out_alias, out_version)


def test_load_active_model_reflects_alias_reassignment(tmp_path):
    """Alias bukan cache statis -- setelah alias "champion" dipindah dari versi 1
    ke versi 2 (threshold berbeda), load_active_model() berikutnya harus
    mengambil versi 2, bukan versi 1 yang lama (bukti mekanisme "versi aktif"
    benar-benar version-aware seperti load_model_by_version() di KK3 M1.5)."""
    tracking_uri = _tracking_uri(tmp_path)

    bundle_v1 = registry.build_bundle(threshold=0.6238)
    info_v1 = registry.register_model(bundle_v1, tracking_uri=tracking_uri)
    bundle_v2 = registry.build_bundle(threshold=0.5)
    info_v2 = registry.register_model(bundle_v2, tracking_uri=tracking_uri)

    df = _band_row_df()

    registry.set_active_alias(info_v1.registered_model_version, alias="champion", tracking_uri=tracking_uri)
    out_v1_active = registry.load_active_model(alias="champion", tracking_uri=tracking_uri).predict(df)
    label_when_v1_active = out_v1_active["churn_label"].iloc[0]

    registry.set_active_alias(info_v2.registered_model_version, alias="champion", tracking_uri=tracking_uri)
    out_v2_active = registry.load_active_model(alias="champion", tracking_uri=tracking_uri).predict(df)
    label_when_v2_active = out_v2_active["churn_label"].iloc[0]

    assert label_when_v1_active == 0  # 0.566 < threshold v1 (0.6238)
    assert label_when_v2_active == 1  # 0.566 >= threshold v2 (0.5)
    assert label_when_v1_active != label_when_v2_active
