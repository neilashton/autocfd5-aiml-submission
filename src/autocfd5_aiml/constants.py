from __future__ import annotations

from pathlib import Path

EVALUATOR_VERSION = "autocfd5-aiml-evaluator-v1.1.4"
DATASET_REPOSITORY = "neashton/drivaerml"
DATASET_REVISION = "7a5c0948ce27be709b1116a3a190f806e7a8f79f"
DATASET_TYPE = "dataset"
SUPPORT_RELEASE_TAG = "support-v1"
SUPPORT_ASSET_NAME = "autocfd5-drivaerml-native-profile-support-v1.zip"
SUPPORT_ASSET_SHA256 = "5ebcf744be53016bd158236d1f4af3290ff399b323c0e11a49c37ea9a6c686f6"
SUPPORT_INDEX_SHA256 = "f47f8c3ed7a56632b0c02a3aec793e4cd823d5d04d5264d00fcd419bf11c0f4f"
SCORING_CONTRACT_SHA256 = (
    "89a5f040ba7b6960e4a9cfd7d81dee437765dcfabc97c2aece595a833c9f68a4"
)
REGIONAL_DIAGNOSTICS_CONTRACT_SHA256 = (
    "2bfd372817989112642056e4c76cfb418dbdcee445c57ee20ca37ee9ca158583"
)
U_INF_M_PER_S = 38.889
PREDICTION_SCOPE_FULL = "surface_and_volume"
PREDICTION_SCOPE_SURFACE_ONLY = "surface_only"
PREDICTION_SCOPES = frozenset(
    {PREDICTION_SCOPE_FULL, PREDICTION_SCOPE_SURFACE_ONLY}
)

SURFACE_ONLY_UNAVAILABLE_COMPONENTS = frozenset(
    {
        "volume_velocity_rel_l2",
        "volume_pressure_rel_l2",
        "velocity_profile_r2",
    }
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def contract_root() -> Path:
    checkout_contract = repository_root() / "contract"
    if checkout_contract.is_dir():
        return checkout_contract
    return Path(__file__).resolve().parent / "contract"
