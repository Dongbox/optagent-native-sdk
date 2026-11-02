"""Check compiler cache identity with real CMake toolchain probes."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import sdk


@unittest.skipUnless(shutil.which("cmake") and shutil.which("ninja"), "CMake and Ninja are required")
class ToolchainCacheTest(unittest.TestCase):
    """Keep target variants separate from compiler and host-tool identity."""

    def test_target_variants_share_a_compiler_but_changed_flags_do_not(self) -> None:
        """Reuse host compiler identity while preserving real flag differences."""
        with tempfile.TemporaryDirectory(prefix="sdk-toolchain-test-") as temporary:
            args = Namespace(
                cmake=shutil.which("cmake"),
                cache=Path(temporary),
                linkage="STATIC",
                configuration="Release",
                sanitizer="",
                deployment_target="26.0",
            )
            original = sdk._compiler_identity(args)
            for linkage, configuration, sanitizer in [
                ("SHARED", "Release", ""),
                ("STATIC", "Debug", ""),
                ("SHARED", "Release", "address"),
                ("SHARED", "Release", "thread"),
            ]:
                with self.subTest(linkage=linkage, configuration=configuration, sanitizer=sanitizer):
                    args.linkage, args.configuration, args.sanitizer = linkage, configuration, sanitizer
                    self.assertEqual(original, sdk._compiler_identity(args))
            flag = "/DOPTAGENT_TOOLCHAIN_CACHE_PROBE=1" if os.name == "nt" else "-DOPTAGENT_TOOLCHAIN_CACHE_PROBE=1"
            with patch.dict(os.environ, {"CXXFLAGS": os.environ.get("CXXFLAGS", "") + " " + flag}):
                self.assertNotEqual(original["identity"], sdk._compiler_identity(args)["identity"])


if __name__ == "__main__":
    unittest.main()
