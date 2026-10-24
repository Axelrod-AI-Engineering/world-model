"""Reject drift outside the two documented Railway persistence gaps (the service source is declared in IaC).

Each environment owns its own services: dev the world model and the ingestion service, production the data service."""

import json
import sys

SERVICES = {"dev": ("world-model", "world-model-ingestion"), "production": ("world-model-data",)}


def verify(plan):
    target = plan.get("currentEnvironment", {})
    services = SERVICES.get(target.get("environmentName"))
    if not plan.get("ok") or target.get("projectId") != "ee19a1df-2ce5-4193-932a-6139f034bbce" or services is None:
        raise ValueError("Expected a successful Axelrod dev or production plan")
    allowed = {
        'deploy.restartPolicyType (null → "ON_FAILURE")',
        'deploy.sleepApplication (null → false)',
    }
    seen = set()
    changes = plan.get("changeSet", {}).get("changes")
    if not isinstance(changes, list):
        raise ValueError("Missing change set")
    for change in changes:
        details = change.get("details")
        if (change.get("kind") != "resource.update"
                or change.get("severity") != "safe"
                or not change.get("summary", "").startswith(tuple(f"Update {name} " for name in services))
                or not isinstance(details, list) or not details):
            raise ValueError(f"Unexpected drift: {change.get('summary')}")
        for detail in details:
            if detail not in allowed or detail in seen:
                raise ValueError(f"Unexpected or duplicate drift: {detail}")
            seen.add(detail)


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as source:
        verify(json.load(source))
    print("Verified: only documented Railway persistence gaps remain.")
