# Tests/ — Unit tests

| File | Covers |
|------|--------|
| `test_ADM.py` | The ADM engine: `ADM_Construction` (`ADM`, `Node`, `SubADMNode`, `EvaluationNode`, `GatedBLF`), `inventive_step_ADM` traversal, and the `UI.CLI`. ~90% coverage. Run by CI. |
| `test_batched_hybrid_system.py` | The batched LLM runner's helpers. |

## Running

Tests import the ADM modules by path, so run from this directory:

```bash
uv run --no-project python -m unittest test_ADM.py -v
```

CI (`.github/workflows/main.yml`) installs only the lightweight `test` dependency group
(`pythonds`, `pydot`) — the heavy vLLM/torch stack is not needed for these tests.
