#include <benchmark/benchmark.h>
#include <string>

static void BM_StringConstruction(benchmark::State& state) {
  const std::size_t size = static_cast<std::size_t>(state.range(0));
  for (auto _ : state) {
    std::string s(size, 'x');
    benchmark::DoNotOptimize(s);
  }
  state.SetComplexityN(size);
}

static void BM_StringConcatenate(benchmark::State& state) {
  const std::size_t size = static_cast<std::size_t>(state.range(0));
  for (auto _ : state) {
    std::string s;
    for (std::size_t i = 0; i < size; ++i) {
      s += 'x';
    }
    benchmark::DoNotOptimize(s);
  }
  state.SetComplexityN(size);
}

BENCHMARK(BM_StringConstruction)->Arg(8)->Arg(64)->Arg(512)->Unit(benchmark::kNanosecond);
BENCHMARK(BM_StringConcatenate)->Arg(8)->Arg(64)->Arg(512)->Unit(benchmark::kNanosecond);
