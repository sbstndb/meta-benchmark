# Usage

## CLI Reference

### Required

| Option | Description |
|--------|-------------|
| `--exe PATH` | Path to Google Benchmark executable |

### Meta-Repetition Control

| Option | Default | Description |
|--------|---------|-------------|
| `--min-meta-reps N` | 5 | Minimum runs before stability check |
| `--max-meta-reps N` | 30 | Hard cap on total runs |
| `--rel-ci-threshold PCT` | 0.03 | Target relative CI half-width (0.03 = 3%) |

### Benchmark Execution

| Option | Default | Description |
|--------|---------|-------------|
| `--min-time-sec SEC` | 0.05 | Forwarded to `--benchmark_min_time` |
| `--warmup-sec SEC` | - | Forwarded to `--benchmark_min_warmup_time` |
| `--repetitions N` | - | Forwarded to `--benchmark_repetitions` |
| `--base-filter REGEX` | - | Filter benchmarks by regex |
| `--gb-arg VALUE` | - | Extra args for benchmark (repeatable) |
| `--timeout SEC` | 14400 | Timeout per run (4 hours) |

### Output

| Option | Default | Description |
|--------|---------|-------------|
| `--output FILE` | meta_results.json | Summary JSON output |
| `--save-raw DIR` | - | Store raw JSON per run |

### Performance & Logging

| Option | Description |
|--------|-------------|
| `--pin-core N` | Pin to CPU core (Linux native, Windows/FreeBSD need psutil) |
| `--no-live` | Disable live progress |
| `-v, --verbose` | Debug logging |
| `-q, --quiet` | Warnings/errors only |

## Output Format

```json
{
  "version": 1,
  "params": { "rel_ci_threshold": 0.03, "min_meta_reps": 5, "max_meta_reps": 30 },
  "cases": {
    "BM_Example/8": {
      "count": 7,
      "mean_ns": 120.4,
      "stddev_ns": 3.5,
      "rel_ci95_half": 0.020,
      "stable": true
    }
  }
}
```

## Building Sample Benchmarks

```bash
cmake -S benchmarks -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j
meta-benchmark --exe ./build/sample_benchmarks
```

Requires: C++20 compiler, CMake 3.20+
