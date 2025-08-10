#include <benchmark/benchmark.h>
#include <vector>
#include <algorithm>
#include <numeric>

static void BM_VectorPushBack(benchmark::State& state) {
  const std::size_t n = static_cast<std::size_t>(state.range(0));
  for (auto _ : state) {
    std::vector<int> v;
    v.reserve(n);
    for (std::size_t i = 0; i < n; ++i) v.push_back(static_cast<int>(i));
    benchmark::DoNotOptimize(v);
  }
  state.SetComplexityN(n);
}

static void BM_VectorSort(benchmark::State& state) {
  const std::size_t n = static_cast<std::size_t>(state.range(0));
  std::vector<int> base(n);
  std::iota(base.begin(), base.end(), 0);
  for (auto _ : state) {
    auto v = base;
    std::reverse(v.begin(), v.end());
    std::sort(v.begin(), v.end());
    benchmark::DoNotOptimize(v);
  }
  state.SetComplexityN(n);
}

BENCHMARK(BM_VectorPushBack)->Arg(128)->Arg(1024)->Arg(8192)->Unit(benchmark::kNanosecond);
BENCHMARK(BM_VectorSort)->Arg(128)->Arg(1024)->Arg(8192)->Unit(benchmark::kNanosecond);
