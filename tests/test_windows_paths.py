"""Check Windows source paths through CMake's generated install scripts."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import tempfile
import unittest

import sdk


@unittest.skipUnless(shutil.which("cmake"), "CMake is required")
class WindowsPathTest(unittest.TestCase):
    """Preserve Windows source paths across the configure/install boundary."""

    def test_relocation_replaces_cmake_normalized_pkgconfig_prefix(self) -> None:
        """Remove the forward-slash prefix emitted by CMake on Windows."""
        with tempfile.TemporaryDirectory(prefix="sdk-pkgconfig-path-") as temporary:
            prefix = Path(temporary)
            package = prefix / "fixture.pc"
            package.write_text(f"prefix={prefix.as_posix()}\n")
            sdk._relocate_metadata(prefix, [prefix])
            self.assertEqual(package.read_text(), "prefix=${pcfiledir}/../..\n")

    def test_relocation_rejects_normalized_windows_producer_paths(self) -> None:
        """Reject a generated package that retains a Windows producer path."""
        with tempfile.TemporaryDirectory(prefix="sdk-package-path-") as temporary:
            prefix = Path(temporary)
            prefix.joinpath("fixture.cmake").write_text('set(SOURCE "C:/agent/work/source")\n')
            with self.assertRaisesRegex(RuntimeError, "leaks a producer path"):
                sdk._relocate_metadata(prefix, [PureWindowsPath("C:/agent/work")])

    def test_generated_install_script_accepts_windows_source_path(self) -> None:
        """Parse an install script containing Windows drive and directory paths."""
        with tempfile.TemporaryDirectory(prefix="sdk-windows-path-") as temporary:
            root = Path(temporary)
            sdk._write_source_manifest(
                root / "sources.cmake", {"fixture": PureWindowsPath("C:/agent/work/sdk-path-fixture")}
            )
            root.joinpath("CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.25)\n"
                "project(WindowsInstallPath NONE)\n"
                "include(sources.cmake)\n"
                'install(DIRECTORY "${SDK_FIXTURE_SOURCE_DIR}/include/" DESTINATION include OPTIONAL)\n'
            )
            for command in (
                ["cmake", "-S", str(root), "-B", str(root / "build")],
                ["cmake", "--install", str(root / "build"), "--prefix", str(root / "install")],
            ):
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
