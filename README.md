### Meta Benchmark Runner (Google Benchmark meta-repetitions)

This repository provides:
- A Python tool (`main.py`) to run Google Benchmark binaries with meta-repetitions, re-running only unstable cases using Google Benchmark's `--benchmark_filter`.

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

No Python dependencies are required beyond the standard library.


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
# From repository root (compat wrapper)
python3 main.py \
  --exe ./build/sample_benchmarks \
  --min-meta-reps 5 \
  --max-meta-reps 30 \
  --rel-ci-threshold 0.03 \
  --min-time-sec 0.05 \
  --output meta_results.json \
  --save-raw raw_runs
```
- `--min-meta-reps`: minimal number of meta-repetitions before stability can be evaluated
- `--max-meta-reps`: hard cap to stop re-running
- `--rel-ci-threshold`: relative 95% CI half-width target (e.g., 0.03 = 3%)
- `--min-time-sec`: forwarded to Google Benchmark as `--benchmark_min_time`
- `--warmup-sec`: optional warmup time (seconds), forwarded as `--benchmark_min_warmup_time`; no warmup by default
- `--save-raw`: directory where each raw JSON output per run is stored

The tool will:
- Run the executable once (optionally filtered), collect `real_time` for each benchmark case
- Repeat runs on unstable cases using `--benchmark_filter`
- Stop when all cases are stable or when `--max-meta-reps` is reached
- Write a summary JSON to `--output` (snapshot updated every iteration)


Alternatively, run the package module directly:
```bash
PYTHONPATH=src python3 -m meta_benchmark \
  --exe ./build/sample_benchmarks \
  --min-meta-reps 40 \
  --max-meta-reps 200 \
  --rel-ci-threshold 0.03 \
  --min-time-sec 0.05 \
  --output meta_results.json \
  --save-raw raw_runs
```

#### 4) Restrict to a subset of tests
If you only want to consider a subset of benchmarks from the start, use `--base-filter` (regular expression understood by Google Benchmark):
```bash
python3 main.py --exe ./build/sample_benchmarks --base-filter "BM_String.*"
```


#### 5) Pass extra Google Benchmark flags
Use `--gb-arg` multiple times to forward arguments to the benchmark executable:
```bash
python3 main.py \
  --exe ./build/sample_benchmarks \
  --gb-arg --benchmark_counters_tabular=false \
  --gb-arg --benchmark_report_aggregates_only=false
```

Optional: enforce Google Benchmark repetitions (by default, repetitions are not set, GB defaults apply):
```bash
python3 main.py --exe ./build/sample_benchmarks --repetitions 10
```


#### 6) Output format
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


#### 7) Notes
- The tool ignores aggregate rows from Google Benchmark JSON (e.g., `aggregate_name` like `mean` or `median`). It uses only per-run `real_time` values.
- Times are normalized to nanoseconds regardless of the benchmark's `time_unit`.
- For small sample sizes, the Student t critical value is used (table for df=1..30). For n > 30, z = 1.96 is used.
- Live one-line progress is enabled by default; disable with `--no-live`.
- By default, the runner passes to Google Benchmark: `--benchmark_counters_tabular=false` and `--benchmark_enable_random_interleaving=true`.


#### 8) Project layout
- `main.py`: compatibility wrapper delegating to the package in `src/`
- `src/meta_benchmark/`: Python package
  - `cli.py`: CLI and main loop
  - `runner.py`: process runner and `MetaConfig`
  - `stats.py`: stats computation and data structures
  - `filters.py`: benchmark filter helpers
  - `io_utils.py`: summary writer
  - `progress.py`: live progress helpers
  - `__main__.py`: allows `python -m meta_benchmark`
- `benchmarks/`: sample C++ benchmarks and CMake build
- `benchmarks/CMakeLists.txt`: top-level CMake file for samples (configure with `cmake -S benchmarks -B build`)


#### 9) Tips
- If your benchmarks are very fast, increase `--min-time-sec` to reduce noise.
- `--warmup-sec` can improve stability for cold caches/branch predictors at the cost of time.
- You can combine `--base-filter` to select your suite and let the meta-runner manage the stability.


#### 10) License
MIT License. See `LICENSE` for details.
