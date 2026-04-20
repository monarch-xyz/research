from __future__ import annotations

from studies.oracle_dominance_v1.config import MONARCH_MARKETS_PAGE_SIZE
from studies.oracle_dominance_v1.utils.env import monarch_api_key, monarch_api_url
from studies.oracle_dominance_v1.utils.http import json_post


MONARCH_MARKETS_QUERY = """
query EnvioMarketsPage($limit: Int!, $offset: Int!, $zeroAddress: String!) {
  Market(
    where: {
      collateralToken: { _neq: $zeroAddress }
      irm: { _neq: $zeroAddress }
    }
    limit: $limit
    offset: $offset
    order_by: [{ chainId: asc }, { marketId: asc }]
  ) {
    chainId
    marketId
    collateralToken
    oracle
  }
}
"""


def fetch_monarch_market_universe() -> dict[tuple[int, str], str]:
    api_url = monarch_api_url()
    api_key = monarch_api_key()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    zero_address = "0x0000000000000000000000000000000000000000"

    markets: dict[tuple[int, str], str] = {}
    offset = 0
    while True:
        result = json_post(
            api_url,
            {
                "query": MONARCH_MARKETS_QUERY,
                "variables": {
                    "limit": MONARCH_MARKETS_PAGE_SIZE,
                    "offset": offset,
                    "zeroAddress": zero_address,
                },
            },
            headers=headers,
        )
        rows = result.get("data", {}).get("Market", [])
        if not rows:
            break

        for row in rows:
            chain_id = int(row["chainId"])
            unique_key = row["marketId"].lower()
            oracle_address = (row.get("oracle") or "").lower()
            if oracle_address:
                markets[(chain_id, unique_key)] = oracle_address

        if len(rows) < MONARCH_MARKETS_PAGE_SIZE:
            break
        offset += len(rows)

    return markets
