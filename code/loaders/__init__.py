"""Per-dataset converters into one canonical format.

Two output shapes, because the project asks two different questions.

  events.csv           (agent_id, task_id, timestep)
                       -> bench.colony_from_events() -> division of labour,
                          specialization, flexibility
                       written by: beesbook, mersch, dornhaus

  interaction_log.csv  (sender, recipient, mtype)
                       -> orglib.measure -> centralization, emergent hubs,
                          structure recovery
                       written by: gernat

Both are plain CSV on purpose. The point of the exercise is that a real colony
and a synthetic organization enter the SAME instrument through the SAME door,
so the file that a biologist's tracking rig eventually produces should be
readable by a text editor and diffable in git.
"""
from . import common  # noqa: F401

__all__ = ["common", "beesbook", "gernat", "mersch", "dornhaus"]
