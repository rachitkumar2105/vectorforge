# vectorforge (engine)

The VectorForge engine: hand-written HNSW, IVF-Flat and int8 quantization, memory-mapped
segments, a crc32-checked write-ahead log, and a FastAPI query service. Python + NumPy only.

See the repository README for setup, the benchmark and the showcase site.

```bash
pip install -e ".[dev]"
pytest --cov=vectorforge
VECTORFORGE_ADMIN_KEY=<32+ random chars> python -c "from vectorforge.service.app import main; main()"
```
