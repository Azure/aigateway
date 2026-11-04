#!/usr/bin/env sh
# Copyright (c) Microsoft Corporation. Licensed under the MIT License.
# MIT License
#
# Copyright (c) Microsoft Corporation.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE

set -eu
EXTENSION_NAME="aigateway"
EXPECTED_API_VERSION="2025-09-01-preview"
PUBLIC_WHEEL_URL="https://github.com/Azure/ai-gateway/releases/download/cli-v1.0.0b22/aigateway-1.0.0b22-py3-none-any.whl"
EXPECTED_SHA256="3363ee0efde6ec22f445fd11f2b6b625867c1ab49b8ab76108f6e1bfa920060a"
UNINSTALL=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h)
      echo "Usage: install.sh [--uninstall|-u] [--help|-h]"
      echo "Installs the pinned public aigateway 1.0.0b22 wheel; no source overrides."
      exit 0
      ;;
    --uninstall|-u) UNINSTALL=1; shift ;;
    *) echo "ERROR: Unknown option: $1. Source overrides are not supported." >&2; exit 2 ;;
  esac
done

if ! command -v az >/dev/null 2>&1; then
  echo "ERROR: Azure CLI ('az') not found." >&2
  echo "Install it first: https://learn.microsoft.com/cli/azure/install-azure-cli" >&2
  exit 1
fi

if [ "$UNINSTALL" -eq 1 ]; then
  INSTALLED_NAME="$(az extension list --query "[?name=='$EXTENSION_NAME'].name" --output tsv)"
  if [ "$INSTALLED_NAME" = "$EXTENSION_NAME" ]; then
    az extension remove --name "$EXTENSION_NAME"
    echo "Uninstalled '$EXTENSION_NAME'."
  elif [ -z "$INSTALLED_NAME" ]; then
    echo "'$EXTENSION_NAME' is not installed; nothing to do."
  else
    echo "ERROR: Unexpected extension list response; refusing to uninstall." >&2
    exit 1
  fi
  exit 0
fi

if [ -z "$PUBLIC_WHEEL_URL" ] || [ -z "$EXPECTED_SHA256" ]; then
  echo "ERROR: Public release is not activated; no approved wheel URL/SHA-256 pair is embedded." >&2
  exit 2
fi
if env | grep -q '^AIGATEWAY_INSTALL_'; then
  echo "ERROR: AIGATEWAY_INSTALL_* overrides are not supported by this pinned public installer." >&2
  exit 2
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aigateway-install.XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup 0
trap 'cleanup; exit 130' 1 2 15
DOWNLOAD_DIR="$TMP_DIR/artifact"
mkdir -p "$DOWNLOAD_DIR"

verify_sha256() {
  asset_name="$1"
  asset_file="$2"
  expected_digest="$3"
  case "$expected_digest" in
    *[!0-9A-Fa-f]*)
      echo "ERROR: Invalid expected SHA-256 digest for '$asset_name'." >&2
      return 1
      ;;
  esac
  if [ "${#expected_digest}" -ne 64 ]; then
    echo "ERROR: Invalid expected SHA-256 digest for '$asset_name'." >&2
    return 1
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    actual_digest="$(sha256sum "$asset_file")"
  elif command -v shasum >/dev/null 2>&1; then
    actual_digest="$(shasum -a 256 "$asset_file")"
  else
    echo "ERROR: sha256sum or shasum is required for verification." >&2
    return 1
  fi
  actual_digest="${actual_digest%% *}"
  expected_digest="$(printf '%s' "$expected_digest" | tr 'A-F' 'a-f')"
  actual_digest="$(printf '%s' "$actual_digest" | tr 'A-F' 'a-f')"
  if [ "$actual_digest" != "$expected_digest" ]; then
    echo "ERROR: SHA-256 verification failed for '$asset_name'." >&2
    return 1
  fi
}

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required for public downloads." >&2
  exit 1
fi
WHEEL_NAME="${PUBLIC_WHEEL_URL##*/}"
case "$WHEEL_NAME" in
  aigateway-*-py3-none-any.whl) ;;
  *)
    echo "ERROR: Public wheel URL must end with an exact aigateway wheel filename." >&2
    exit 2
    ;;
esac
WHEEL_FILE="$DOWNLOAD_DIR/$WHEEL_NAME"
EFFECTIVE_URL_FILE="$TMP_DIR/effective-url.txt"
curl --fail --location --show-error --proto '=https' --tlsv1.2 \
  --output "$WHEEL_FILE" --write-out '%{url_effective}' \
  "$PUBLIC_WHEEL_URL" >"$EFFECTIVE_URL_FILE"
EFFECTIVE_URL="$(cat "$EFFECTIVE_URL_FILE")"
case "$EFFECTIVE_URL" in
  https://*) ;;
  *)
    echo "ERROR: Public wheel download did not finish at an HTTPS URL." >&2
    exit 1
    ;;
esac

set -- "$DOWNLOAD_DIR"/aigateway-*.whl
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "ERROR: Expected exactly one aigateway-*.whl in public URL." >&2
  exit 1
fi
WHEEL_FILE="$1"
WHEEL_NAME="${WHEEL_FILE##*/}"
case "$WHEEL_NAME" in
  aigateway-*-py3-none-any.whl) ;;
  *)
    echo "ERROR: Unexpected wheel filename '$WHEEL_NAME'." >&2
    exit 1
    ;;
esac
EXPECTED_VERSION="${WHEEL_NAME#aigateway-}"
EXPECTED_VERSION="${EXPECTED_VERSION%-py3-none-any.whl}"
case "$EXPECTED_VERSION" in
  ""|*[!A-Za-z0-9.+_-]*)
    echo "ERROR: Unsafe extension version in wheel filename '$WHEEL_NAME'." >&2
    exit 1
    ;;
esac

if grep -EIqi '<html|<!doctype' "$WHEEL_FILE"; then
  echo "ERROR: Public wheel download looks like an HTML page, not a wheel." >&2
  exit 1
fi
verify_sha256 "$WHEEL_NAME" "$WHEEL_FILE" "$EXPECTED_SHA256"

# Azure CLI skips --upgrade for an equal version, even if its bytes differ.
INSTALLED_VERSION="$(az extension list --query "[?name=='$EXTENSION_NAME'].version" --output tsv)"
if [ "$INSTALLED_VERSION" = "$EXPECTED_VERSION" ]; then
  az extension remove --name "$EXTENSION_NAME"
fi

az extension add \
  --upgrade \
  --yes \
  --source "$WHEEL_FILE" \
  --output none

az_value() {
  query="$1"
  stderr_file="$TMP_DIR/az-version.stderr"
  if value="$(az aigateway version --query "$query" --output tsv 2>"$stderr_file")"; then
    rm -f "$stderr_file"
    printf '%s\n' "$value"
    return 0
  else
    status=$?
  fi
  cat "$stderr_file" >&2
  rm -f "$stderr_file"
  return "$status"
}

ACTUAL_NAME="$(az_value extensionName)"
ACTUAL_VERSION="$(az_value extensionVersion)"
ACTUAL_API_VERSION="$(az_value apiVersion)"
if [ "$ACTUAL_NAME" != "$EXTENSION_NAME" ]; then
  echo "ERROR: Installed extension name '$ACTUAL_NAME' is not '$EXTENSION_NAME'." >&2
  exit 1
fi
if [ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "ERROR: Installed version '$ACTUAL_VERSION' does not match wheel '$EXPECTED_VERSION'." >&2
  exit 1
fi
if [ "$ACTUAL_API_VERSION" != "$EXPECTED_API_VERSION" ]; then
  echo "ERROR: Supported API '$ACTUAL_API_VERSION' does not match '$EXPECTED_API_VERSION'." >&2
  exit 1
fi

echo "Installed '$EXTENSION_NAME' $ACTUAL_VERSION successfully."
echo "Verify with: az aigateway version"
