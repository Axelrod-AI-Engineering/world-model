#!/bin/bash
# Core's apply-gap workaround, constrained to this repo's dev service.
set -euo pipefail
CLI=(npx --yes -p node@22 -p @railway/cli@5.64.2 railway)
VARIABLES='{"serviceId":"027bcc28-9089-4fe2-bcd9-ec1cfcc9807e","environmentId":"422fbce4-6b2c-4e60-b40f-15275e19f6d6","input":{"restartPolicyType":"ON_FAILURE","sleepApplication":false}}'
QUERY='query($serviceId: String!, $environmentId: String!) { serviceInstance(serviceId: $serviceId, environmentId: $environmentId) { restartPolicyType sleepApplication } }'
MUTATION='mutation($serviceId: String!, $environmentId: String, $input: ServiceInstanceUpdateInput!) { serviceInstanceUpdate(serviceId: $serviceId, environmentId: $environmentId, input: $input) }'
result="$("${CLI[@]}" api --compact "$MUTATION" --variables "$VARIABLES")"
jq -e '.data.serviceInstanceUpdate == true' <<< "$result" >/dev/null
result="$("${CLI[@]}" api --compact "$QUERY" --variables "$VARIABLES")"
jq -e '.data.serviceInstance.restartPolicyType == "ON_FAILURE" and .data.serviceInstance.sleepApplication == false' <<< "$result" >/dev/null
echo 'Verified world-model dev: ON_FAILURE and App Sleep off.'
