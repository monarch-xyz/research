from __future__ import annotations

from studies.oracle_dominance_v1.utils.env import oracle_gist_base_url
from studies.oracle_dominance_v1.utils.http import json_get


def fetch_oracle_metadata(chain_ids: list[int]) -> dict[tuple[int, str], dict]:
    base_url = oracle_gist_base_url()
    metadata: dict[tuple[int, str], dict] = {}
    for chain_id in sorted(set(chain_ids)):
        payload = json_get(f"{base_url}/oracles.{chain_id}.json")
        for oracle in payload.get("oracles", []):
            metadata[(chain_id, oracle["address"].lower())] = oracle
    return metadata
