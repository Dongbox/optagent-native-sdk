"""Check process-local ownership of versioned ELF runtime data."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    platform.system() == "Linux" and all(shutil.which(tool) for tool in ("g++", "cmake", "ninja")),
    "The ELF isolation contract requires Linux, GCC, CMake and Ninja",
)
class ElfIsolationTest(unittest.TestCase):
    """Keep SDK inline data distinct from a foreign RTLD_LOCAL library."""

    def test_versioned_runtime_data_remains_local_in_both_load_orders(self) -> None:
        """Preserve separate addresses and mutations for identically named data."""
        recipe = Path(__file__).resolve().parents[1] / "cmake/elf-symbols.cmake"
        with tempfile.TemporaryDirectory(prefix="sdk-elf-isolation-") as temporary:
            root = Path(temporary)
            root.joinpath("marker.cc").write_text(
                "inline int sdk_runtime_marker = 17;\n"
                'extern "C" int* marker_address() { return &sdk_runtime_marker; }\n'
            )
            root.joinpath("CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.25)\n"
                "project(ElfIsolation LANGUAGES CXX)\n"
                "set(CMAKE_CXX_STANDARD 20)\n"
                "set(BUILD_SHARED_LIBS ON)\n"
                f'include("{recipe}")\n'
                "add_library(foreign SHARED marker.cc)\n"
                "add_library(owned SHARED marker.cc)\n"
                "sdk_elf_symbols(owned OPTAGENT_NATIVE_1)\n"
            )
            for command in (
                [
                    "cmake",
                    "-S",
                    str(root),
                    "-B",
                    str(root / "build"),
                    "-G",
                    "Ninja",
                    f"-DCMAKE_CXX_COMPILER={shutil.which('g++')}",
                ],
                ["cmake", "--build", str(root / "build"), "--parallel", "2"],
            ):
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            program = """
import ctypes
import sys
libraries = [ctypes.CDLL(path, mode=ctypes.RTLD_LOCAL) for path in sys.argv[1:]]
for library in libraries:
    library.marker_address.restype = ctypes.POINTER(ctypes.c_int)
first, second = [library.marker_address().contents for library in libraries]
assert ctypes.addressof(first) != ctypes.addressof(second), "runtime data coalesced"
first.value = 31
assert second.value == 17, "foreign runtime state changed"
"""
            for order in (("foreign", "owned"), ("owned", "foreign")):
                with self.subTest(order=order):
                    result = subprocess.run(
                        [sys.executable, "-I", "-c", program]
                        + [str(root / "build" / f"lib{name}.so") for name in order],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
