"""Observed write atomicity of the pinned FalkorDB release (design decision D21).

The approval contract relies on one Cypher statement either fully applying or not
at all. These tests record what the pinned image actually does; mutation statements
are still written so that no runtime error can occur after their first write.
"""

import pytest
from helpers.graphq import cypher, scalar
from redis.exceptions import ResponseError


async def test_runtime_error_after_a_write_rolls_the_statement_back(graph):
    await cypher(graph, "CREATE (:Marker {id: 'm'})", write=True)
    with pytest.raises(ResponseError, match="Division by zero"):
        await cypher(graph, "UNWIND [1, 0] AS d CREATE (:Tmp {d: d}) WITH d RETURN 10 / d", write=True)
    assert await scalar(graph, "MATCH (t:Tmp) RETURN count(t)") == 0


async def test_unmatched_compare_and_set_writes_nothing(graph):
    await cypher(graph, "CREATE (:Workspace {id: 'ws', context_revision: 5})", write=True)
    rows = await cypher(
        graph,
        "MATCH (w:Workspace {id: 'ws'}) WHERE w.context_revision = $expected "
        "CREATE (:Decision {id: 'd1'}) SET w.context_revision = w.context_revision + 1 RETURN w.context_revision",
        {"expected": 4},
        write=True,
    )
    assert rows == []
    assert await scalar(graph, "MATCH (d:Decision) RETURN count(d)") == 0
    assert await scalar(graph, "MATCH (w:Workspace) RETURN w.context_revision") == 5
