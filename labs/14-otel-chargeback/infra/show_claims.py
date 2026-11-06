"""Print the claims of a Microsoft Entra access token that matter for chargeback.

The token is decoded locally. Nothing is sent anywhere, and the signature isn't checked.

Usage:
    az account get-access-token --resource https://azure-api.net/aigateway --query accessToken -o tsv \
        | python show_claims.py [extra-claim ...]

Examples:
    ... | python show_claims.py
    ... | python show_claims.py cost_center roles
"""

import base64
import json
import sys

DEFAULT_CLAIMS = ["aud", "ver", "tid", "oid", "appid", "azp", "idtyp"]


def decode_payload(token: str) -> dict:
    parts = token.strip().split(".")
    if len(parts) != 3:
        sys.exit("That doesn't look like a JWT access token (expected three dot-separated parts).")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def main() -> None:
    token = sys.stdin.read()
    if not token.strip():
        sys.exit("Pipe an access token into this script. See the usage in the file header.")
    claims = decode_payload(token)
    for name in DEFAULT_CLAIMS + sys.argv[1:]:
        value = claims.get(name, "(not in token)")
        print(f"{name:<12} {json.dumps(value) if not isinstance(value, str) else value}")


if __name__ == "__main__":
    main()
