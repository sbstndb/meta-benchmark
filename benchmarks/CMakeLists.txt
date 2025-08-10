cmake_minimum_required(VERSION 3.20)
project(meta_benchmark_samples LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Disable Google Benchmark tests to avoid requiring GoogleTest
set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
set(BENCHMARK_ENABLE_GTEST_TESTS OFF CACHE BOOL "" FORCE)

include(FetchContent)

# Fetch Google Benchmark
FetchContent_Declare(
  googlebenchmark
  GIT_REPOSITORY https://github.com/google/benchmark.git
  GIT_TAG v1.8.4
)
FetchContent_MakeAvailable(googlebenchmark)

# Ensure pthread on Linux
set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

# Samples target
add_executable(sample_benchmarks
  sample_strings.cpp
  sample_vectors.cpp
)

target_link_libraries(sample_benchmarks PRIVATE benchmark::benchmark benchmark::benchmark_main Threads::Threads)

target_compile_options(sample_benchmarks PRIVATE -O3 -DNDEBUG)
set_target_properties(sample_benchmarks PROPERTIES OUTPUT_NAME sample_benchmarks)
