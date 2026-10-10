"""Deployment gates must reject unrelated and destructive changes."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "railway_drift", Path(__file__).resolve().parents[2] / "scripts/verify-railway-drift.py"
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def plan(changes):
    return {
        "ok": True,
        "currentEnvironment": {
            "projectId": "ee19a1df-2ce5-4193-932a-6139f034bbce",
            "environmentName": "dev",
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


@pytest.mark.parametrize("change", [
    {"kind": "resource.delete", "severity": "destructive", "summary": "Delete world-model"},
    {"kind": "resource.update", "severity": "safe", "summary": "Update web source.type",
     "details": ['source.type ("github" → "empty")']},
    {"kind": "resource.update", "severity": "safe", "summary": "Update world-model volume",
     "details": ["volume.mountPath"]},
])
def test_rejects_unrelated_or_destructive_drift(change):
    with pytest.raises(ValueError):
        _module.verify(plan([change]))


def test_rejects_wrong_environment():
    wrong = plan([])
    wrong["currentEnvironment"]["environmentName"] = "production"
    with pytest.raises(ValueError):
        _module.verify(wrong)
