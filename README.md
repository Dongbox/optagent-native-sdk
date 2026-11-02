# OptAgent Native SDK

Produce immutable, relocatable C++20 solver SDKs independently of any Python or
OptAgent product build. This repository contains public third-party build
recipes and an owned CP-SAT session bridge. It contains no OptAgent product
sources, production license keys or private data.

The source lock pins HiGHS, CP-SAT, protobuf, Abseil, compression libraries,
libsodium, OpenBLAS and GoogleTest. Abseil and protobuf have one common build;
HiGHS owns its extras and BLAS; CP-SAT owns native Model registration, flags use,
observers and teardown. `bin/protoc` is a separately built host tool and is never
compiled by a product consumer. Test tools are installed for native owner tests
and are not runtime wheel dependencies.

## Local production

Use Python 3.12, CMake 3.25 or later, Ninja and a C++20 compiler. The initial
profiles are macOS arm64 (deployment target 26), manylinux2014 x86_64 (GCC 10),
and Windows amd64 (MSVC `/MD`; Debug uses its own `/MDd` SDK). Windows OpenBLAS
production additionally needs clang-cl in the MSVC developer environment.

```sh
python sdk.py build --cache build/cache --prefix build/install \
  --profile macos-arm64-release --linkage STATIC --configuration Release --jobs 4
cmake -S tests/consumer -B build/consumer -G Ninja \
  -DCMAKE_PREFIX_PATH="$PWD/build/install" -DCMAKE_BUILD_TYPE=Release
cmake --build build/consumer --parallel 4
ctest --test-dir build/consumer --output-on-failure --timeout 60
python sdk.py verify build/install
python sdk.py pack build/install --output dist/sdk.tar.gz
```

The install prefix is immutable. Choose a new prefix after changing the lock,
profile or module recipes. Keep the cache: completed modules are verified and
reused; interrupted builds retain their Ninja workspace. A producer lock rejects
concurrent mutation of the same cache. An explicit `--seed-root` can reuse local
Git objects; checkout revisions and patches are still verified. Never modify a
prepared source cache in place.

Retained workspaces explicitly refresh each dependency package directory when
module identities change. Updating `CMAKE_PREFIX_PATH` alone leaves cached
protobuf, Abseil or support package locations active. The package-cache contract
configures two dependency sets in one real CMake build tree.

The compiler identity is separate from target linkage, configuration and
instrumentation. Host protoc stays Release/static and has no target ABI-profile
key; support, OpenBLAS and test tools retain their actual static linkage. This
allows static/shared target SDKs to reuse matching host and support artifacts.
Run `python -m unittest discover -s tests -p 'test_*.py'` to verify compiler cache
identity with real CMake probes, including a changed-flags rejection case.

For Linux, build `toolchains/manylinux2014.Dockerfile` and run the same commands
inside it using profile `linux-x86_64-manylinux2014-release`. The image pins its
upstream digest and retains the GCC 10 / glibc 2.17 baseline. SDK module identity
includes sources, patches, recipes, compiler/standard-library context and direct
dependency identities. A Python version is not part of the SDK ABI profile.

## Consume an installation

```cmake
set(CMAKE_CXX_STANDARD 20)
find_package(OptAgentNative 0.1.0 EXACT CONFIG REQUIRED)
target_link_libraries(application PRIVATE
  OptAgentNative::highs OptAgentNative::cpsat protobuf::libprotobuf absl::int128)
```

Pass only the installed prefix via `CMAKE_PREFIX_PATH`. Import validates the
compiler, platform, architecture, standard library, exception/RTTI, container
layout, CRT/debug and sanitizer profile. `manifest.json` records every installed
file hash and source revision; verify it before evaluating package CMake code.
A consumer must never fall back to fetching or compiling solver sources.

Use `optagent_cpsat/session.h` for solve/validate operations. A `Session` owns its
native context, accepts one synchronous `Run`, borrows inputs until return and
borrows observer responses only during each callback. `RequestStop` is latched,
idempotent and nonblocking. Keep the session and any shared stop flag alive until
execution and stop callers finish. `RunStatus::kOutOfMemory` preserves allocation
failures separately from ordinary exceptions; `Solve` rethrows them as
`std::bad_alloc` after cleanup. Other reported failures use `std::runtime_error`.
`Solve` provides an ordinary one-call session.

## Release policy

Actions remain globally disabled during the initial local rollout. Every checked-in
workflow is manual (`workflow_dispatch`). Producing an SDK does not publish a
release. Review relocation, ABI rejection, solver contracts and platform runtime
isolation evidence before publishing immutable, platform-named Release assets.
Do not overwrite an asset referenced by an OptAgent lock; publish a new version.
On Linux/GCC, SDK shared libraries disable GNU unique data symbols and propagate
the matching C++ option to consumers of their public headers. Named ELF
symbol versions alone do not stop process-wide inline-data coalescing with a
foreign protobuf/OR-Tools runtime. The ELF contract test loads two real DSOs in
both orders and checks separate data addresses and mutations.

Static SDKs are the supported fallback until shared-library and installed-wheel
gates pass on each required platform. Configuration success alone is insufficient.
