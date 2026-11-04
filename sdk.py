"""Produce and verify relocatable native SDK modules from an exact source lock."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE_SOURCES = {
    "host": ("abseil", "protobuf"),
    "common": ("abseil", "protobuf"),
    "support": ("sodium", "zlib", "bzip2"),
    "openblas": ("openblas",),
    "highs": ("highs",),
    "cpsat": ("cpsat",),
    "test-tools": ("gtest",),
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _producer_snapshot() -> dict:
    paths = [ROOT / "CMakeLists.txt", ROOT / "sdk.lock.json", ROOT / "sdk.py", ROOT / "requirements-producer.lock"]
    paths += list((ROOT / "cmake").glob("*")) + list((ROOT / "patches").glob("*"))
    files = {str(p.relative_to(ROOT)): _sha(p) for p in sorted(paths) if p.is_file()}
    revision = _run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture=True)
    dirty = bool(_run(["git", "status", "--porcelain"], cwd=ROOT, capture=True))
    return {
        "repository": "https://github.com/Dongbox/optagent-native-sdk.git",
        "revision": revision,
        "dirty": dirty,
        "recipe_files": files,
    }


def _verify_snapshot(expected: dict) -> None:
    if _producer_snapshot() != expected:
        raise RuntimeError("Producer recipes changed during production; retry using the retained module cache")


def _run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _files(prefix: Path) -> dict[str, str]:
    result = {}
    for path in sorted(prefix.rglob("*")):
        if path.is_symlink() and path.is_dir():
            raise RuntimeError(f"SDK directory aliases are unsupported: {path}")
        if path.is_file() and path != prefix / "manifest.json":
            if not path.resolve().is_relative_to(prefix.resolve()):
                raise RuntimeError(f"SDK file escapes its install prefix: {path}")
            result[path.relative_to(prefix).as_posix()] = _sha(path)
    return result


def _verify_files(prefix: Path, expected: dict[str, str]) -> None:
    actual = _files(prefix)
    if set(actual) != set(expected):
        raise RuntimeError("SDK file inventory differs from its manifest")
    for relative, digest in expected.items():
        path = prefix / relative
        if not path.resolve().is_relative_to(prefix.resolve()):
            raise RuntimeError(f"Invalid manifest path: {relative}")
        if not path.is_file() or actual[relative] != digest:
            raise RuntimeError(f"SDK file missing or corrupt: {relative}")


def _prepare_source(name: str, spec: dict, cache: Path, seeds: list[Path]) -> Path:
    patch_id = {patch: _sha(ROOT / patch) for patch in spec.get("patches", [])}
    key = _identity({"source": spec, "patches": patch_id})
    destination = cache / "sources" / f"{name}-{key[:20]}"
    ready = destination / ".sdk-source.json"
    if ready.is_file():
        metadata = json.loads(ready.read_text())
        if metadata["identity"] != key:
            raise RuntimeError(f"Source identity differs: {destination}")
        if "repository" in spec:
            revision = _run(["git", "-C", str(destination), "rev-parse", "HEAD"], capture=True)
            if revision != spec["revision"]:
                raise RuntimeError(f"Source checkout revision differs: {destination}")
            # Pinned zlib's configure renames its bundled zconf.h. Accept only
            # that exact byte-preserving upstream operation.
            exclusions = []
            if name == "zlib" and not (destination / "zconf.h").exists():
                original = subprocess.check_output(["git", "-C", str(destination), "show", "HEAD:zconf.h"])
                if (destination / "zconf.h.included").read_bytes() != original:
                    raise RuntimeError("The generated zlib header backup differs")
                exclusions = [":!zconf.h"]
            diff = _run(["git", "-C", str(destination), "diff", "HEAD", "--", ".", *exclusions], capture=True)
            if hashlib.sha256(diff.encode()).hexdigest() != metadata["diff"]:
                raise RuntimeError(f"Prepared dependency sources were modified: {destination}")
        else:
            inventory = {key: value for key, value in _files(destination).items() if key != ".sdk-source.json"}
            if inventory != metadata["files"]:
                raise RuntimeError(f"Extracted dependency sources were modified: {destination}")
        return destination
    if destination.exists():
        raise RuntimeError(f"Incomplete source preparation; inspect {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if "repository" in spec:
        names = [spec["directory"], name, spec["directory"] + "-src", spec["directory"] + "-linux"]
        seed = next((root / item for root in seeds for item in names if (root / item / ".git").exists()), None)
        _run(["git", "clone", "--no-hardlinks", "--no-checkout", str(seed or spec["repository"]), str(destination)])
        _run(["git", "-C", str(destination), "remote", "set-url", "origin", spec["repository"]])
        exists = subprocess.run(
            ["git", "-C", str(destination), "cat-file", "-e", spec["revision"]], capture_output=True
        )
        if exists.returncode:
            _run(["git", "-C", str(destination), "fetch", "--no-tags", "origin", spec["revision"]])
        _run(["git", "-C", str(destination), "checkout", "--detach", spec["revision"]])
        if spec.get("submodules"):
            _run(["git", "-C", str(destination), "submodule", "update", "--init", "--recursive"])
        for patch in spec.get("patches", []):
            _run(["git", "-C", str(destination), "apply", str(ROOT / patch)])
        diff = _run(["git", "-C", str(destination), "diff", "HEAD", "--", "."], capture=True)
        metadata = {"identity": key, "diff": hashlib.sha256(diff.encode()).hexdigest()}
    else:
        archive = cache / "downloads" / spec["sha256"]
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            temporary = archive.with_suffix(".tmp")
            with urllib.request.urlopen(spec["url"], timeout=120) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            if _sha(temporary) != spec["sha256"]:
                raise RuntimeError("Dependency archive hash differs")
            temporary.replace(archive)
        if _sha(archive) != spec["sha256"]:
            raise RuntimeError("Cached dependency archive hash differs")
        with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
            with tarfile.open(archive) as source:
                source.extractall(temporary, filter="data")
            shutil.move(str(Path(temporary) / spec["directory"]), destination)
        metadata = {"identity": key, "files": _files(destination)}
    _write_json(ready, metadata)
    return destination


def _relocate_metadata(prefix: Path, producer_roots: list[Path]) -> None:
    for path in prefix.rglob("*.pc"):
        text = path.read_text()
        for spelling in {str(prefix), prefix.as_posix()}:
            text = text.replace(spelling, "${pcfiledir}/../..")
        path.write_text(text)
    for path in prefix.rglob("*.cmake"):
        text = path.read_text()
        for root in producer_roots:
            if any(spelling in text for spelling in {str(root), root.as_posix()}):
                raise RuntimeError(f"Install package leaks a producer path: {path}")


def _notices(prefix: Path, sources: dict[str, Path]) -> None:
    for name, source in sources.items():
        output = prefix / "share/optagent-native/licenses" / name
        output.mkdir(parents=True, exist_ok=True)
        for pattern in ("LICENSE*", "COPYING*", "NOTICE*", "THIRD_PARTY_NOTICES*"):
            for path in source.glob(pattern):
                if path.is_file():
                    shutil.copyfile(path, output / path.name)
        if name == "highs":
            for relative in ("extern/amd/License.txt", "extern/metis/LICENSE.txt", "extern/rcm/LICENSE"):
                path = source / relative
                shutil.copyfile(path, output / (path.parent.name + "-LICENSE.txt"))
        if name == "sodium":
            shutil.copyfile(source / "libsodium/LICENSE", output / "libsodium-LICENSE.txt")
        if name == "protobuf":
            shutil.copyfile(source / "third_party/utf8_range/LICENSE", output / "utf8-range-LICENSE.txt")


def _abi_header(abi: dict) -> str:
    header = """#ifndef OPTAGENT_NATIVE_ABI_H_
#define OPTAGENT_NATIVE_ABI_H_
#include <functional>
#include <string>
#include <string_view>
#include <vector>
#include "absl/base/options.h"
namespace optagent_native_abi {
#if defined(_LIBCPP_VERSION)
constexpr std::string_view library = "libc++";
constexpr int library_abi = _LIBCPP_ABI_VERSION;
#elif defined(__GLIBCXX__)
constexpr std::string_view library = "libstdc++";
constexpr int library_abi = _GLIBCXX_USE_CXX11_ABI;
#elif defined(_MSVC_STL_VERSION)
constexpr std::string_view library = "msvc";
constexpr int library_abi = _MSVC_STL_VERSION;
#else
#error Unsupported native SDK standard library
#endif
#if defined(_MSC_VER) && defined(_DLL)
constexpr int dynamic_crt = 1;
#else
constexpr int dynamic_crt = 0;
#endif
#ifdef _ITERATOR_DEBUG_LEVEL
constexpr int iterator_debug = _ITERATOR_DEBUG_LEVEL;
#else
constexpr int iterator_debug = 0;
#endif
#ifdef _GLIBCXX_DEBUG
constexpr int debug_containers = 1;
#else
constexpr int debug_containers = 0;
#endif
#if defined(_CPPUNWIND) || defined(__EXCEPTIONS)
constexpr int exceptions = 1;
#else
constexpr int exceptions = 0;
#endif
#if defined(_CPPRTTI) || defined(__GXX_RTTI)
constexpr int rtti = 1;
#else
constexpr int rtti = 0;
#endif
#if defined(__SANITIZE_ADDRESS__)
constexpr int address_sanitizer = 1;
#elif defined(__has_feature)
#if __has_feature(address_sanitizer)
constexpr int address_sanitizer = 1;
#else
constexpr int address_sanitizer = 0;
#endif
#else
constexpr int address_sanitizer = 0;
#endif
#if defined(__SANITIZE_THREAD__)
constexpr int thread_sanitizer = 1;
#elif defined(__has_feature)
#if __has_feature(thread_sanitizer)
constexpr int thread_sanitizer = 1;
#else
constexpr int thread_sanitizer = 0;
#endif
#else
constexpr int thread_sanitizer = 0;
#endif
"""
    checks = {
        "library_abi": "stdlib_abi",
        "iterator_debug": "iterator_debug",
        "debug_containers": "debug_containers",
        "exceptions": "exceptions",
        "rtti": "rtti",
        "dynamic_crt": "dynamic_crt",
        "address_sanitizer": "address_sanitizer",
        "thread_sanitizer": "thread_sanitizer",
        "sizeof(void*)": "pointer_size",
        "sizeof(std::string)": "string_size",
        "sizeof(std::vector<int>)": "vector_size",
        "sizeof(std::function<void()>)": "function_size",
    }
    header += f'static_assert(library == "{abi["stdlib"]}", "Native SDK standard library differs");\n'
    for expression, field in checks.items():
        header += f'static_assert({expression} == {abi[field]}, "Native SDK ABI differs: {field}");\n'
    header += (
        "#define OPTAGENT_NATIVE_STRINGIFY_INNER(x) #x\n"
        "#define OPTAGENT_NATIVE_STRINGIFY(x) OPTAGENT_NATIVE_STRINGIFY_INNER(x)\n"
    )
    header += (
        "static_assert(std::string_view(OPTAGENT_NATIVE_STRINGIFY(ABSL_OPTION_INLINE_NAMESPACE_NAME)) ==\n"
        f'  "{abi["absl_namespace"]}", "Native SDK Abseil namespace differs");\n'
    )
    return header + "#undef OPTAGENT_NATIVE_STRINGIFY\n#undef OPTAGENT_NATIVE_STRINGIFY_INNER\n}\n#endif\n"


def _module_linkage(name: str, requested: str) -> str:
    return "STATIC" if name in {"host", "support", "openblas", "test-tools"} else requested


def _configure_command(
    args,
    name: str,
    sources: dict,
    dependencies: dict,
    manifest: Path,
    build: Path,
    prefix: Path,
    configuration: str,
    sanitizer: str,
) -> list[str]:
    configure = [
        args.cmake,
        "-S",
        str(ROOT),
        "-B",
        str(build),
        "-G",
        "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={shutil.which('ninja')}",
        f"-DOPTAGENT_SDK_COMPONENT={name}",
        f"-DOPTAGENT_NATIVE_LINKAGE={_module_linkage(name, args.linkage)}",
        f"-DOPTAGENT_SDK_SOURCES={manifest}",
        f"-DCMAKE_BUILD_TYPE={configuration}",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        f"-DOPTAGENT_SDK_SANITIZER={sanitizer}",
        f"-DOPTAGENT_SDK_HIPO={'ON' if args.hipo else 'OFF'}",
        "-DCMAKE_PREFIX_PATH=" + ";".join(str(path) for path in dependencies.values()),
    ]
    # Reused workspaces retain *_DIR cache entries, which outrank a changed
    # CMAKE_PREFIX_PATH. Refresh transitive package locations as one unit.
    for owner, packages in {
        "common": ("absl", "utf8_range", "protobuf"),
        "support": ("OptAgentSupport",),
    }.items():
        if owner in dependencies:
            configure += [f"-D{package}_DIR={dependencies[owner] / 'lib' / 'cmake' / package}" for package in packages]
    if args.compiler_cache:
        configure += [
            f"-DCMAKE_C_COMPILER_LAUNCHER={args.compiler_cache}",
            f"-DCMAKE_CXX_COMPILER_LAUNCHER={args.compiler_cache}",
        ]
    if platform.system() == "Darwin":
        configure.append(f"-DCMAKE_OSX_DEPLOYMENT_TARGET={args.deployment_target}")
    if name == "cpsat":
        configure += [
            f"-DOPTAGENT_HOST_PROTOC={dependencies['host'] / 'bin' / ('protoc.exe' if os.name == 'nt' else 'protoc')}",
            "-DOPTAGENT_CPSAT_BUILD_TESTS=ON",
        ]
    if name == "highs" and "openblas" in dependencies:
        configure.append(f"-DOPTAGENT_OPENBLAS_ROOT={dependencies['openblas']}")
    if name == "openblas":
        configure = [
            args.cmake,
            "-S",
            str(sources["openblas"]),
            "-B",
            str(build),
            "-G",
            "Ninja",
            f"-DCMAKE_MAKE_PROGRAM={shutil.which('ninja')}",
            f"-DCMAKE_INSTALL_PREFIX={prefix}",
            f"-DCMAKE_BUILD_TYPE={configuration}",
        ]
        options = json.loads((ROOT / "cmake/openblas-options.json").read_text())
        configure += [f"-D{key}={value}" for key, value in options.items()]
        if os.name == "nt":
            compiler = shutil.which("clang-cl")
            if compiler is None:
                raise RuntimeError("OpenBLAS production requires clang-cl")
            configure += [
                f"-DCMAKE_C_COMPILER={compiler}",
                f"-DCMAKE_ASM_COMPILER={compiler}",
                "-DCMAKE_MSVC_RUNTIME_LIBRARY="
                + ("MultiThreadedDebugDLL" if configuration == "Debug" else "MultiThreadedDLL"),
            ]
    return configure


def _write_source_manifest(manifest: Path, sources: dict) -> None:
    # CMake bracket arguments preserve backslashes, but generated install()
    # scripts quote these paths again and interpret sequences such as \a.
    manifest.write_text(
        "".join(f"set(SDK_{source.upper()}_SOURCE_DIR [==[{path.as_posix()}]==])\n" for source, path in sources.items())
    )


def _module(args, lock: dict, name: str, dependencies: dict[str, Path]) -> Path:
    sources = {
        key: _prepare_source(key, lock["sources"][key], args.cache, args.seed_root) for key in MODULE_SOURCES[name]
    }
    recipe = [ROOT / "CMakeLists.txt"]
    if name != "openblas":
        recipe.append(ROOT / "cmake" / f"{name}.cmake")
    else:
        recipe.append(ROOT / "cmake/openblas-options.json")
    if name == "support":
        recipe.append(ROOT / "cmake/OptAgentSupportConfig.cmake")
    if name == "common":
        recipe.append(ROOT / "cmake/abi_probe.cc")
    if name in {"common", "highs", "cpsat"}:
        recipe.append(ROOT / "cmake/elf-symbols.cmake")
    configuration = "Release" if name == "host" else args.configuration
    sanitizer = "" if name == "host" else args.sanitizer
    identity = {
        "source": {key: lock["sources"][key] for key in sources},
        "patches": {p: _sha(ROOT / p) for key in sources for p in lock["sources"][key].get("patches", [])},
        "recipe": {str(p.relative_to(ROOT)): _sha(p) for p in recipe},
        "profile": "host" if name == "host" else args.profile,
        "linkage": _module_linkage(name, args.linkage),
        "configuration": configuration,
        "sanitizer": sanitizer,
        "deployment_target": args.deployment_target if platform.system() == "Darwin" else "",
        "hipo": args.hipo if name in {"highs", "openblas"} else None,
        "compiler": args.compiler_identity,
        "build_tools": args.build_tools,
        "driver_policy": args.configure_policy,
        "metadata_policy": args.metadata_policy,
        "dependencies": {
            key: json.loads((path.parent / "ready.json").read_text())["id"] for key, path in dependencies.items()
        },
    }
    key = _identity(identity)
    directory = args.cache / "modules" / name / key
    prefix = directory / "install"
    ready = directory / "ready.json"
    if ready.is_file():
        data = json.loads(ready.read_text())
        _verify_files(prefix, data["files"])
        print(f"[sdk] reuse {name} {key[:12]}", flush=True)
        return prefix
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "sources.cmake"
    _write_source_manifest(manifest, sources)
    # Install artifacts are immutable; the Ninja workspace is deliberately
    # stable across source/recipe revisions so CMake can rebuild actual deltas.
    workspace_id = _identity(
        {
            "producer_root": str(ROOT),
            "module": name,
            "compiler": args.compiler_identity,
            "configuration": configuration,
            "linkage": identity["linkage"],
            "sanitizer": sanitizer,
        }
    )
    workspace = args.cache / "work" / name / workspace_id
    workspace.mkdir(parents=True, exist_ok=True)
    index = workspace / "workspace.json"
    if index.is_file():
        build = Path(json.loads(index.read_text())["build"])
    else:
        build = workspace / "build"
        # Reuse an already validated bootstrap workspace without moving its
        # absolute CMake paths. This does not reuse outputs without Ninja checks.
        for previous in sorted((args.cache / "modules" / name).glob("*/ready.json")):
            old = json.loads(previous.read_text())
            candidate = previous.parent / "build"
            comparable = ("source", "patches", "compiler", "configuration", "linkage", "sanitizer")
            if candidate.is_dir() and all(old["identity"].get(field) == identity.get(field) for field in comparable):
                cache_file = candidate / "CMakeCache.txt"
                if cache_file.is_file() and f"CMAKE_HOME_DIRECTORY:INTERNAL={ROOT}" in cache_file.read_text():
                    build = candidate
                    break
        _write_json(index, {"build": str(build)})
    configure = _configure_command(args, name, sources, dependencies, manifest, build, prefix, configuration, sanitizer)
    print(f"[sdk] build {name} {key[:12]}", flush=True)
    _run(configure)
    _run([args.cmake, "--build", str(build), "--target", "install", "--parallel", str(args.jobs)])
    if name == "cpsat":
        _run([sys.executable, str(sources["cpsat"] / "cmake/optagent-sdk/update_closure.py"), str(sources["cpsat"])])
        _run([args.ctest, "--test-dir", str(build / "cpsat"), "--output-on-failure"])
    if name == "highs" and "openblas" in dependencies:
        shutil.copytree(dependencies["openblas"], prefix, dirs_exist_ok=True)
    abi = {}
    if name == "common":
        abi = json.loads(
            _run([str(build / ("sdk_abi_probe.exe" if os.name == "nt" else "sdk_abi_probe"))], capture=True)
        )
        header = prefix / "include/optagent_native/abi.h"
        header.parent.mkdir(parents=True, exist_ok=True)
        header.write_text(_abi_header(abi))
    for source, specification in ((key, lock["sources"][key]) for key in sources):
        _prepare_source(source, specification, args.cache, args.seed_root)
    if {str(path.relative_to(ROOT)): _sha(path) for path in recipe} != identity["recipe"]:
        raise RuntimeError("SDK recipe changed during production")
    _notices(prefix, sources)
    _relocate_metadata(prefix, list(sources.values()) + [build, prefix])
    toolchain = json.loads((build / "toolchain.json").read_text()) if (build / "toolchain.json").exists() else {}
    _write_json(ready, {"id": key, "identity": identity, "toolchain": toolchain, "abi": abi, "files": _files(prefix)})
    return prefix


def _compose(args, lock: dict, modules: dict[str, Path]) -> Path:
    destination = args.prefix.resolve()
    if destination.exists():
        metadata = json.loads((destination / "manifest.json").read_text())
        identities = {
            name: json.loads((prefix.parent / "ready.json").read_text())["id"] for name, prefix in modules.items()
        }
        if (
            metadata["source_lock"] != lock
            or metadata.get("producer") != args.producer_snapshot
            or {name: value["id"] for name, value in metadata["modules"].items()} != identities
        ):
            raise RuntimeError(f"SDK output differs; choose a new immutable prefix: {destination}")
        _verify_files(destination, metadata["files"])
        print(f"SDK_READY={destination}", flush=True)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdk-assemble-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "install"
        stage.mkdir()
        records = {}
        for name, prefix in modules.items():
            record = json.loads((prefix.parent / "ready.json").read_text())
            for relative, digest in record["files"].items():
                path = stage / relative
                if path.exists() and _sha(path) != digest:
                    raise RuntimeError(f"Module install collision: {name}: {relative}")
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(prefix / relative, path)
                shutil.copymode(prefix / relative, path)
            records[name] = {"id": record["id"], "toolchain": record["toolchain"], "abi": record.get("abi", {})}
        # This contract is derived from measured binary ABI data, not a reason
        # to recompile the common runtime when only validation policy changes.
        (stage / "include/optagent_native/abi.h").write_text(_abi_header(records["common"]["abi"]))
        config = stage / "lib/cmake/OptAgentNative"
        config.mkdir(parents=True)
        shutil.copyfile(ROOT / "cmake/OptAgentNativeConfig.cmake", config / "OptAgentNativeConfig.cmake")
        (config / "OptAgentNativeConfigVersion.cmake").write_text(
            f'set(PACKAGE_VERSION "{lock["version"]}")\n'
            "if(PACKAGE_FIND_VERSION VERSION_EQUAL PACKAGE_VERSION)\n"
            "  set(PACKAGE_VERSION_EXACT TRUE)\n  set(PACKAGE_VERSION_COMPATIBLE TRUE)\nendif()\n"
        )
        _write_json(
            stage / "manifest.json",
            {
                "schema": 1,
                "version": lock["version"],
                "abi_revision": lock["abi_revision"],
                "profile": args.profile,
                "configuration": args.configuration,
                "linkage": args.linkage,
                "sanitizer": args.sanitizer,
                "source_lock": lock,
                "producer": args.producer_snapshot,
                "build_tools": args.build_tools,
                "modules": records,
                "files": _files(stage),
                "deployment_target": args.deployment_target if platform.system() == "Darwin" else "",
                "features": {"hipo": args.hipo, "highs_int64": False, "cpsat_allocation_status": True},
            },
        )
        stage.rename(destination)
    print(f"SDK_READY={destination}", flush=True)
    return destination


@contextmanager
def _producer_lock(cache: Path):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "producer.lock"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise RuntimeError(f"SDK cache is in use; inspect its owner before recovering {path}") from error
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump({"pid": os.getpid(), "host": platform.node()}, output)
        yield
    finally:
        path.unlink()


def _compiler_identity(args) -> dict:
    compiler = os.environ.get("CXX") or ("cl" if os.name == "nt" else "c++")
    executable = shutil.which(compiler)
    if executable is None:
        raise RuntimeError(f"C++ compiler is unavailable: {compiler}")
    context = {
        "binary": _sha(Path(executable).resolve()),
        "system": platform.system(),
        "machine": platform.machine(),
        "cc": os.environ.get("CC"),
        "flags": {key: os.environ.get(key, "") for key in ("CFLAGS", "CXXFLAGS", "LDFLAGS")},
    }
    if platform.system() == "Darwin":
        context["sdk"] = _run(["xcrun", "--show-sdk-version"], capture=True)
    probe = args.cache / "toolchains" / _identity(context)
    command = [
        args.cmake,
        "-S",
        str(ROOT),
        "-B",
        str(probe),
        "-G",
        "Ninja",
        "-DOPTAGENT_SDK_COMPONENT=probe",
        # Module identity separately records its actual configuration, linkage
        # and sanitizer. Keep the compiler/standard-library identity neutral so
        # target variants do not recompile the always-Release host protoc.
        "-DOPTAGENT_NATIVE_LINKAGE=STATIC",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DOPTAGENT_SDK_SANITIZER=",
    ]
    if platform.system() == "Darwin":
        command.append(f"-DCMAKE_OSX_DEPLOYMENT_TARGET={args.deployment_target}")
    if os.name == "nt":
        blas = shutil.which("clang-cl")
        if blas:
            command.append(f"-DOPTAGENT_OPENBLAS_C_COMPILER={blas}")
    _run(command)
    return {
        "identity": (probe / "identity.txt").read_text().strip(),
        "toolchain": json.loads((probe / "toolchain.json").read_text()),
    }


def main(argv: list[str] | None = None) -> int:
    """Build, verify or archive a pinned SDK installation.

    Args:
        argv: Arguments to parse, or None to use process arguments.

    Returns:
        Zero on success, or two for invalid configuration or failed validation.
    """
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--cache", type=Path, required=True)
    build.add_argument("--prefix", type=Path, required=True)
    build.add_argument("--seed-root", action="append", default=[], type=Path)
    build.add_argument("--profile", required=True)
    build.add_argument("--linkage", choices=["STATIC", "SHARED"], default="STATIC")
    build.add_argument("--configuration", choices=["Release", "RelWithDebInfo", "Debug"], default="Release")
    build.add_argument("--sanitizer", choices=["", "address", "thread"], default="")
    build.add_argument("--hipo", action=argparse.BooleanOptionalAction, default=True)
    build.add_argument("--deployment-target", default="26.0")
    build.add_argument("--jobs", type=int, default=2)
    build.add_argument("--compiler-cache", default="")
    build.add_argument("--cmake", default="cmake")
    build.add_argument("--ctest", default="ctest")
    verify = subparsers.add_parser("verify")
    verify.add_argument("prefix", type=Path)
    pack = subparsers.add_parser("pack")
    pack.add_argument("prefix", type=Path)
    pack.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"verify", "pack"}:
            metadata = json.loads((args.prefix / "manifest.json").read_text())
            _verify_files(args.prefix, metadata["files"])
            if args.command == "pack":
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with tarfile.open(args.output, "w:gz", dereference=True) as archive:
                    archive.add(args.prefix, arcname="sdk")
                print(f"{_sha(args.output)}  {args.output.name}")
            else:
                print(f"SDK verified: {args.prefix}")
            return 0
        if args.jobs < 1:
            parser.error("--jobs must be positive")
        args.cache = args.cache.resolve()
        args.seed_root = [path.resolve() for path in args.seed_root]
        with _producer_lock(args.cache):
            policies = {
                node.name: node
                for node in ast.parse((ROOT / "sdk.py").read_text()).body
                if isinstance(node, ast.FunctionDef)
            }
            args.configure_policy = _identity(ast.dump(policies["_configure_command"], include_attributes=False))
            args.metadata_policy = _identity(
                [
                    ast.dump(policies[name], include_attributes=False)
                    for name in ("_write_source_manifest", "_relocate_metadata")
                ]
            )
            args.producer_snapshot = _producer_snapshot()
            args.build_tools = {
                "cmake": _run([args.cmake, "--version"], capture=True).splitlines()[0],
                "ninja": _run(["ninja", "--version"], capture=True),
            }
            args.compiler_identity = _compiler_identity(args)
            lock = json.loads((ROOT / "sdk.lock.json").read_text())
            host = _module(args, lock, "host", {})
            common = _module(args, lock, "common", {})
            support = _module(args, lock, "support", {})
            modules = {"host": host, "common": common, "support": support}
            if args.hipo and platform.system() != "Darwin":
                modules["openblas"] = _module(args, lock, "openblas", {})
            modules["highs"] = _module(
                args, lock, "highs", {"openblas": modules["openblas"]} if "openblas" in modules else {}
            )
            modules["cpsat"] = _module(args, lock, "cpsat", {"host": host, "common": common, "support": support})
            modules["test-tools"] = _module(args, lock, "test-tools", {})
            _verify_snapshot(args.producer_snapshot)
            _compose(args, lock, modules)
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"SDK error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
