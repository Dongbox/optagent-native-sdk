"""Check dependency replacement in a retained producer workspace."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import sdk


@unittest.skipUnless(shutil.which("cmake") and shutil.which("ninja"), "CMake and Ninja are required")
class PackageCacheTest(unittest.TestCase):
    """Resolve every package from the selected immutable dependency module."""

    def test_reconfiguration_replaces_cached_direct_and_transitive_packages(self) -> None:
        """Resolve the second dependency set in the same CMake build tree."""
        with tempfile.TemporaryDirectory(prefix="sdk-package-cache-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            source.joinpath("CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.25)\n"
                "project(PackageCache NONE)\n"
                'file(WRITE "${CMAKE_BINARY_DIR}/resolved.txt" "")\n'
                "foreach(package absl utf8_range protobuf OptAgentSupport)\n"
                "  find_package(${package} CONFIG REQUIRED)\n"
                "endforeach()\n"
            )
            args = Namespace(
                cmake=shutil.which("cmake"),
                linkage="SHARED",
                hipo=True,
                compiler_cache=None,
                deployment_target="26.0",
            )
            for variant in ("first", "second"):
                dependencies = {owner: root / variant / owner for owner in ("host", "common", "support")}
                expected = []
                for package in ("absl", "utf8_range", "protobuf", "OptAgentSupport"):
                    owner = "support" if package == "OptAgentSupport" else "common"
                    prefix = dependencies[owner]
                    directory = prefix / "lib/cmake" / package
                    directory.mkdir(parents=True)
                    value = f"{prefix}:{package}"
                    expected.append(value)
                    directory.joinpath(f"{package}Config.cmake").write_text(
                        f'file(APPEND "${{CMAKE_BINARY_DIR}}/resolved.txt" [==[{value}\n]==])\n'
                    )
                command = sdk._configure_command(
                    args,
                    "cpsat",
                    {},
                    dependencies,
                    root / "sources.cmake",
                    root / "build",
                    root / "install",
                    "Release",
                    "",
                )
                command[command.index("-S") + 1] = str(source)
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(root.joinpath("build/resolved.txt").read_text().splitlines(), expected)


if __name__ == "__main__":
    unittest.main()
