### Meta Benchmark Runner (Google Benchmark meta-repetitions)

A Python tool to run Google Benchmark binaries with statistical meta-repetitions, automatically re-running only unstable cases until results stabilize.

## Installation

```bash
# Basic installation
pip install meta-benchmark

# With cross-platform CPU affinity support (recommended)
pip install meta-benchmark[affinity]
```

Or install from source:
```bash
git clone https://github.com/sbstndb/meta-benchmark.git
cd meta-benchmark
pip install -e .
```

## How it works

Concise algorithm overview:

- Run each benchmark case for `--min-meta-reps`.
- Compute statistics on `real_time` and check if the relative CI half-width ≤ `--rel-ci-threshold`.
- While some cases are unstable and total runs < `--max-meta-reps`:
  - Re-run only the unstable cases via `--benchmark_filter` and update stats.
- Stop when all cases are stable or the cap is reached; write/update `--output`.

```
[min-meta-reps] → [CI check] → [re-run unstable only] ↻ until [all stable] or [max-meta-reps]
```


#### 1) Prerequisites (runner)
- Python 3.9+
- Git (optional, for cloning)

No Python dependencies are required beyond the standard library. Optional: install `psutil` for cross-platform CPU affinity support (Linux, Windows, FreeBSD).


#### 2) Build the sample benchmarks (optional)
Prerequisites for building the samples:
- C++20 compiler (e.g., GCC 11+ or Clang 13+)
- CMake 3.20+
- Git

Build steps:
```bash
# From repository root
cmake -S benchmarks -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j
# The benchmark executable will be here:
#   build/sample_benchmarks
```


#### 3) Run the meta runner on the sample
```bash
# Using the installed package
meta-benchmark \
  --exe ./build/sample_benchmarks \
  --min-meta-reps 5 \
  --max-meta-reps 30 \
  --rel-ci-threshold 0.03 \
  --min-time-sec 0.05 \
  --output meta_results.json \
  --save-raw raw_runs

# Or using the compatibility wrapper
python3 main.py --exe ./build/sample_benchmarks
```

**Core options:**
- `--min-meta-reps`: minimal number of meta-repetitions before stability can be evaluated (default: 5)
- `--max-meta-reps`: hard cap to stop re-running (default: 30)
- `--rel-ci-threshold`: relative 95% CI half-width target, e.g., 0.03 = 3% (default: 0.03)
- `--min-time-sec`: forwarded to Google Benchmark as `--benchmark_min_time` (default: 0.05)
- `--warmup-sec`: optional warmup time (seconds), forwarded as `--benchmark_min_warmup_time`
- `--save-raw`: directory where each raw JSON output per run is stored
- `--timeout`: timeout in seconds for each benchmark run (default: 14400 = 4 hours)

**Logging options:**
- `-v, --verbose`: enable debug logging for troubleshooting
- `-q, --quiet`: suppress info messages, only show warnings and errors

The tool will:
- Run the executable once (optionally filtered), collect `real_time` for each benchmark case
- Repeat runs on unstable cases using `--benchmark_filter`
- Stop when all cases are stable or when `--max-meta-reps` is reached
- Write a summary JSON to `--output` (snapshot updated every iteration)


Alternatively, run the package module directly:
```bash
python3 -m meta_benchmark \
  --exe ./build/sample_benchmarks \
  --min-meta-reps 40 \
  --max-meta-reps 200 \
  --rel-ci-threshold 0.03 \
  --min-time-sec 0.05 \
  --output meta_results.json \
  --save-raw raw_runs
```


#### 4) CPU affinity (reduce noise)
Pin the benchmark process to a specific CPU core to reduce scheduling noise:
```bash
meta-benchmark --exe ./build/sample_benchmarks --pin-core 0
```

**Platform support:**
- **Linux**: Native support via `os.sched_setaffinity`, or via `psutil` if installed
- **Windows/FreeBSD**: Requires `psutil` (`pip install meta-benchmark[affinity]`)
- **macOS**: CPU affinity is not supported (warning logged, benchmark runs normally)

#### 5) Restrict to a subset of tests
If you only want to consider a subset of benchmarks from the start, use `--base-filter` (regular expression understood by Google Benchmark):
```bash
meta-benchmark --exe ./build/sample_benchmarks --base-filter "BM_String.*"
```


#### 6) Pass extra Google Benchmark flags
Use `--gb-arg` multiple times to forward arguments to the benchmark executable:
```bash
meta-benchmark \
  --exe ./build/sample_benchmarks \
  --gb-arg --benchmark_counters_tabular=false \
  --gb-arg --benchmark_report_aggregates_only=false
```

Optional: enforce Google Benchmark repetitions (by default, repetitions are not set, GB defaults apply):
```bash
meta-benchmark --exe ./build/sample_benchmarks --repetitions 10
```


#### 7) Output format
`meta_results.json` contains, per benchmark case name:
- `count`: number of meta-repetitions run
- `mean_ns`, `stddev_ns`: statistics over meta-repetitions (nanoseconds)
- `rel_ci95_half`: relative 95% confidence interval half-width
- `stable`: whether the case met the target

Example snippet:
```json
{
  "version": 1,
  "params": { "rel_ci_threshold": 0.03, "min_meta_reps": 5, "max_meta_reps": 30 },
  "cases": {
    "BM_StringConstruction/8": {
      "count": 7,
      "mean_ns": 120.4,
      "stddev_ns": 3.5,
      "rel_ci95_half": 0.020,
      "stable": true
    }
  }
}
```


#### 8) Notes
- The tool ignores aggregate rows from Google Benchmark JSON (e.g., `aggregate_name` like `mean` or `median`). It uses only per-run `real_time` values.
- Times are normalized to nanoseconds regardless of the benchmark's `time_unit`.
- For small sample sizes, the Student t critical value is used (table for df=1..30). For n > 30, z = 1.96 is used.
- Live one-line progress is enabled by default; disable with `--no-live`.
- By default, the runner passes to Google Benchmark: `--benchmark_counters_tabular=false` and `--benchmark_enable_random_interleaving=true`.
- Each benchmark run has a 4-hour timeout by default (configurable with `--timeout`).


#### 9) Project layout
- `main.py`: compatibility wrapper delegating to the package in `src/`
- `src/meta_benchmark/`: Python package
  - `cli.py`: CLI entry point and main loop
  - `runner.py`: subprocess runner and `MetaConfig` dataclass
  - `stats.py`: statistics computation and `CaseStats` data structure
  - `filters.py`: benchmark filter regex helpers
  - `io_utils.py`: JSON output and summary writer
  - `progress.py`: live progress display
  - `constants.py`: default values and exit codes
  - `exceptions.py`: custom `BenchmarkError` exception
  - `cpu_affinity.py`: cross-platform CPU pinning
  - `logging_config.py`: logging setup
  - `__main__.py`: allows `python -m meta_benchmark`
- `benchmarks/`: sample C++ benchmarks and CMake build
- `benchmarks/CMakeLists.txt`: top-level CMake file for samples (configure with `cmake -S benchmarks -B build`)


#### 10) Tips
- If your benchmarks are very fast, increase `--min-time-sec` to reduce noise.
- `--warmup-sec` can improve stability for cold caches/branch predictors at the cost of time.
- You can combine `--base-filter` to select your suite and let the meta-runner manage the stability.
- Use `--pin-core 0` to reduce scheduling noise (requires `psutil` on Windows).
- Use `-v` to debug issues or `-q` to reduce output in CI/CD pipelines.


#### 11) License
MIT License. See `LICENSE` for details.
