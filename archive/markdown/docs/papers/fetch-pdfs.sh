#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${ROOT}/pdf"
mkdir -p "${OUT}"
ids=(2502.05352 2501.06706 2606.29193 2606.08590 2604.21199 2605.12729 2509.05303 2607.20478 2608.02672 2604.12040 2607.26791 2601.22130 2407.13244 2403.06749 2603.15798 2408.04682 2406.12045 2403.07718 2407.05291 2510.27287 2505.18878 2404.07972 2308.03688 2511.10049 2604.12290 2603.20807 2504.07164 2606.12736)
for id in "${ids[@]}"; do
  url="https://arxiv.org/pdf/${id}"
  dst="${OUT}/${id}.pdf"
  tmp="${dst}.tmp"
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 --retry-delay 1 --output "${tmp}" "${url}"
  test -s "${tmp}"
  mv "${tmp}" "${dst}"
done
( cd "${OUT}" && sha256sum ./*.pdf > SHA256SUMS )
echo "fetched ${#ids[@]} papers into ${OUT}" >&2
