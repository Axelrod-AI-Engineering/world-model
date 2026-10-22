"""The learning task hands the engine's shared process through."""

from __future__ import annotations

from axelrod_wm.learning.task import LearningTask


def test_the_task_reads_the_engines_shared_process(m1_engine):
    task = LearningTask(m1_engine)
    assert task.shared is m1_engine.shared
