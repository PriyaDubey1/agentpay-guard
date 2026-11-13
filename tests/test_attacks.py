import pytest

from attacks.harness import Harness
from attacks.scenarios import SCENARIOS


@pytest.mark.parametrize("s", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_scenario(s):
    h = Harness()
    try:
        passed, detail = s["fn"](h)
    finally:
        h.close()
    assert passed, detail
