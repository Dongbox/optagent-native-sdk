"""Check that ABI probes use the consuming target's build configuration."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import sdk


@unittest.skipUnless(
    shutil.which("cmake") and shutil.which("ninja"), "CMake and Ninja are required"
)
class AbiConfigurationTest(unittest.TestCase):
    """Compile ABI checks using the real configuration-specific compiler flags."""

    def test_probe_matches_consumer_configuration(self) -> None:
        """Keep Release and Debug probes consistent with their target flags."""
        with tempfile.TemporaryDirectory(prefix="sdk-abi-configuration-") as temporary:
            root = Path(temporary)
            header = root / "sdk/include/optagent_native/abi.h"
            header.parent.mkdir(parents=True)
            for configuration in ("Release", "Debug"):
                with self.subTest(configuration=configuration):
                    condition = "ifndef" if configuration == "Release" else "ifdef"
                    header.write_text(
                        f"#{condition} NDEBUG\n#error Wrong ABI probe configuration\n#endif\n"
                    )
                    root.joinpath("CMakeLists.txt").write_text(
                        "cmake_minimum_required(VERSION 3.25)\n"
                        "project(AbiProbe LANGUAGES CXX)\n"
                        f'include("{sdk.ROOT.as_posix()}/cmake/OptAgentNativeAbi.cmake")\n'
                        f'optagent_native_check_abi("{root.as_posix()}/sdk" "{configuration}")\n'
                    )
                    result = subprocess.run(
                        [
                            "cmake",
                            "-S",
                            str(root),
                            "-B",
                            str(root / configuration),
                            "-G",
                            "Ninja",
                            f"-DCMAKE_BUILD_TYPE={configuration}",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )


if __name__ == "__main__":
    unittest.main()
