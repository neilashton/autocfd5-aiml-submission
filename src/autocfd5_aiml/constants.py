from __future__ import annotations

from pathlib import Path

EVALUATOR_VERSION = "autocfd5-aiml-evaluator-v1"
DATASET_REPOSITORY = "neashton/drivaerml"
DATASET_REVISION = "7a5c0948ce27be709b1116a3a190f806e7a8f79f"
DATASET_TYPE = "dataset"
SUPPORT_RELEASE_TAG = "support-v1"
SUPPORT_ASSET_NAME = "autocfd5-drivaerml-native-profile-support-v1.zip"
SUPPORT_ASSET_SHA256 = "5ebcf744be53016bd158236d1f4af3290ff399b323c0e11a49c37ea9a6c686f6"
SUPPORT_INDEX_SHA256 = "f47f8c3ed7a56632b0c02a3aec793e4cd823d5d04d5264d00fcd419bf11c0f4f"
U_INF_M_PER_S = 38.889


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def contract_root() -> Path:
    checkout_contract = repository_root() / "contract"
    if checkout_contract.is_dir():
        return checkout_contract
    return Path(__file__).resolve().parent / "contract"
