# Meta Benchmark

Run Google Benchmark binaries with statistical meta-repetitions. Automatically re-runs only unstable cases until results stabilize.

## Installation

```bash
pip install meta-benchmark

# With CPU affinity support
pip install meta-benchmark[affinity]
```

## Quick Start

```bash
meta-benchmark --exe ./build/my_benchmarks
```

## How It Works

1. Run each benchmark for `--min-meta-reps` (default: 5)
2. Check if 95% CI half-width ≤ `--rel-ci-threshold` (default: 3%)
3. Re-run only unstable cases
4. Stop when all stable or `--max-meta-reps` reached

## Key Options

| Option | Default | Description |
|--------|---------|-------------|
| `--exe` | required | Benchmark executable |
| `--min-meta-reps` | 5 | Min runs before stability check |
| `--max-meta-reps` | 30 | Max total runs |
| `--rel-ci-threshold` | 0.03 | Target CI width (3%) |
| `--pin-core` | - | Pin to CPU core |
| `--output` | meta_results.json | Output file |

Full CLI reference: [docs/usage.md](docs/usage.md)

## Context

This project is part of a tooling initiative for the [CMAP](https://cmap.ip-paris.fr/) / [hpc@maths](https://music-hpc.music.polytechnique.fr/) team at École Polytechnique.

## License

MIT
