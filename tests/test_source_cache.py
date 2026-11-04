"""Check source-cache integrity across upstream configure operations."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import sdk


@unittest.skipUnless(shutil.which("git"), "Git is required")
class SourceCacheTest(unittest.TestCase):
    """Accept only unchanged dependency sources with the active Git filters."""

    def test_zlib_backup_preserves_checkout_line_endings(self) -> None:
        """Accept the upstream rename with CRLF, while rejecting changed bytes."""
        with tempfile.TemporaryDirectory(prefix="sdk-source-cache-") as temporary:
            root = Path(temporary)
            upstream = root / "upstream"
            subprocess.run(["git", "init", "-q", str(upstream)], check=True)
            upstream.joinpath("zconf.h").write_bytes(
                b"/* zlib header fixture */\n#define ZLIB_CONST 1\n"
            )
            subprocess.run(["git", "-C", str(upstream), "add", "zconf.h"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(upstream),
                    "-c",
                    "user.name=SDK Test",
                    "-c",
                    "user.email=sdk@example.invalid",
                    "commit",
                    "-qm",
                    "Fixture",
                ],
                check=True,
            )
            revision = subprocess.check_output(
                ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
            ).strip()
            spec = {
                "repository": str(upstream),
                "revision": revision,
                "directory": "zlib",
            }
            source = sdk._prepare_source("zlib", spec, root / "cache", [])
            subprocess.run(
                ["git", "-C", str(source), "config", "core.autocrlf", "true"],
                check=True,
            )
            (source / "zconf.h").unlink()
            subprocess.run(
                ["git", "-C", str(source), "checkout-index", "--force", "--all"],
                check=True,
            )
            header = source / "zconf.h"
            self.assertIn(b"\r\n", header.read_bytes())
            backup = source / "zconf.h.included"
            header.rename(backup)
            self.assertEqual(
                sdk._prepare_source("zlib", spec, root / "cache", []), source
            )
            backup.write_bytes(backup.read_bytes() + b"/* unexpected change */\r\n")
            with self.assertRaisesRegex(RuntimeError, "header backup differs"):
                sdk._prepare_source("zlib", spec, root / "cache", [])


if __name__ == "__main__":
    unittest.main()
