"""Deployment gates must reject unrelated and destructive changes."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "railway_drift", Path(__file__).resolve().parents[1] / ".railway/verify-railway-drift.py"
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def plan(changes, environment="dev"):
    return {
        "ok": True,
        "currentEnvironment": {
            "projectId": "ee19a1df-2ce5-4193-932a-6139f034bbce",
            "environmentName": environment,
        },
        "changeSet": {"changes": changes},
    }


def test_clean_and_known_persistence_gaps():
    _module.verify(plan([]))
    _module.verify(plan([{
        "kind": "resource.update", "severity": "safe",
        "summary": "Update world-model deploy.restartPolicyType, deploy.sleepApplication",
        "details": ['deploy.restartPolicyType (null → "ON_FAILURE")',
                    'deploy.sleepApplication (null → false)'],
    }]))


def test_each_environment_owns_its_own_services():
    gap = ['deploy.sleepApplication (null → false)']

    def update(name):
        return {"kind": "resource.update", "severity": "safe", "summary": f"Update {name} deploy.sleepApplication",
                "details": list(gap)}

    _module.verify(plan([update("world-model-ingestion")]))
    _module.verify(plan([update("world-model-data")], "production"))
    with pytest.raises(ValueError):
        _module.verify(plan([update("world-model-data")]))
    with pytest.raises(ValueError):
        _module.verify(plan([update("world-model")], "production"))


@pytest.mark.parametrize("change", [
    {"kind": "resource.delete", "severity": "destructive", "summary": "Delete world-model"},
    {"kind": "resource.update", "severity": "safe", "summary": "Update web source.type",
     "details": ['source.type ("github" → "empty")']},
    # unlinking this service from its repository is never a leftover: the source is declared in IaC
    {"kind": "resource.update", "severity": "safe", "summary": "Update world-model source.repo, source.type",
     "details": ['source.repo ("Axelrod-AI-Engineering/world-model" → null)', 'source.type ("github" → "empty")']},
    {"kind": "resource.update", "severity": "safe", "summary": "Update world-model volume",
     "details": ["volume.mountPath"]},
])
def test_rejects_unrelated_or_destructive_drift(change):
    with pytest.raises(ValueError):
        _module.verify(plan([change]))


def test_rejects_wrong_environment():
    wrong = plan([])
    wrong["currentEnvironment"]["environmentName"] = "staging"
    with pytest.raises(ValueError):
        _module.verify(wrong)
