import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from snow_engine.media import _javascript_runtime_args, download_youtube


def downloader_settings(**overrides):
    values = {
        "ytdlp_format": "bv*+ba/b",
        "ytdlp_fallback_format": "b[height<=1080][ext=mp4]/b[height<=1080]/b/bv*+ba",
        "ytdlp_fallback_player_clients": "default,-web_safari",
        "ytdlp_js_runtime": "auto",
        "ytdlp_js_runtime_path": "",
        "ytdlp_remote_components": False,
        "ytdlp_cookies_file": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class DownloaderTests(unittest.TestCase):
    def test_first_attempt_matches_native_ytdlp_and_accepts_webm(self):
        logs = []
        debug_logs = []
        commands = []

        with tempfile.TemporaryDirectory() as temporary:
            job_dir = Path(temporary)

            def fake_run(command, **kwargs):
                commands.append(command)
                (job_dir / "source.webm").write_bytes(b"native yt-dlp output")
                return subprocess.CompletedProcess(command, 0, stdout="merged", stderr="")

            with patch("snow_engine.media.shutil.which") as runtime_lookup, patch(
                "snow_engine.media.subprocess.run", side_effect=fake_run
            ):
                downloaded = download_youtube(
                    "https://youtu.be/mBVpu4dg1_4",
                    job_dir,
                    downloader_settings(ytdlp_js_runtime_path="C:/tools/deno.exe"),
                    logs.append,
                    debug_logs.append,
                )

        self.assertEqual(downloaded.name, "source.webm")
        self.assertEqual(len(commands), 1)
        self.assertEqual(
            commands[0],
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--no-playlist",
                "--output",
                str(job_dir / "source.%(ext)s"),
                "https://youtu.be/mBVpu4dg1_4",
            ],
        )
        for forbidden in (
            "--format",
            "--merge-output-format",
            "--extractor-args",
            "--js-runtimes",
            "--force-overwrites",
        ):
            self.assertNotIn(forbidden, commands[0])
        runtime_lookup.assert_not_called()
        self.assertEqual(len(debug_logs), 1)
        self.assertIn("comando sanitizado", debug_logs[0])
        self.assertIn("mBVpu4dg1_4", debug_logs[0])

    def test_retries_with_progressive_format_and_alternate_client(self):
        logs = []
        debug_logs = []
        commands = []

        with tempfile.TemporaryDirectory() as temporary:
            job_dir = Path(temporary)

            def fake_run(command, **kwargs):
                commands.append(command)
                if len(commands) <= 2:
                    return subprocess.CompletedProcess(
                        command,
                        1,
                        stdout="",
                        stderr="ERROR: Unable to download video data: HTTP Error 403: Forbidden",
                    )
                (job_dir / "source.mp4").write_bytes(b"local merged video")
                return subprocess.CompletedProcess(command, 0, stdout="merged", stderr="")

            with patch("snow_engine.media.shutil.which", return_value=None), patch(
                "snow_engine.media.subprocess.run", side_effect=fake_run
            ):
                downloaded = download_youtube(
                    "https://youtu.be/acs6YL0fBug",
                    job_dir,
                    downloader_settings(),
                    logs.append,
                    debug_logs.append,
                )

        self.assertEqual(downloaded.name, "source.mp4")
        self.assertEqual(len(commands), 3)
        self.assertEqual(commands[0][:3], [sys.executable, "-m", "yt_dlp"])
        self.assertNotIn("--format", commands[0])
        self.assertNotIn("--merge-output-format", commands[0])
        self.assertNotIn("--extractor-args", commands[0])
        self.assertEqual(commands[1][commands[1].index("--format") + 1], "bv*+ba/b")
        self.assertNotIn("--extractor-args", commands[1])
        self.assertEqual(
            commands[2][commands[2].index("--format") + 1],
            "b[height<=1080][ext=mp4]/b[height<=1080]/b/bv*+ba",
        )
        self.assertIn("youtube:player_client=default,-web_safari", commands[2])
        self.assertEqual(len(debug_logs), 3)
        self.assertTrue(any("formato progressivo" in message for message in logs))

    def test_native_attempt_preserves_optional_cookies_but_sanitizes_debug_log(self):
        debug_logs = []
        commands = []

        with tempfile.TemporaryDirectory() as temporary:
            job_dir = Path(temporary)

            def fake_run(command, **kwargs):
                commands.append(command)
                (job_dir / "source.mkv").write_bytes(b"native output")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch("snow_engine.media.subprocess.run", side_effect=fake_run):
                download_youtube(
                    "https://youtu.be/mBVpu4dg1_4",
                    job_dir,
                    downloader_settings(ytdlp_cookies_file="C:/Users/Snow/secrets/cookies.txt"),
                    lambda message: None,
                    debug_logs.append,
                )

        self.assertIn("--cookies", commands[0])
        self.assertIn("C:/Users/Snow/secrets/cookies.txt", commands[0])
        self.assertIn("[COOKIES_FILE]", debug_logs[0])
        self.assertNotIn("C:/Users/Snow/secrets/cookies.txt", debug_logs[0])

    def test_configures_deno_and_optional_ejs_component(self):
        logs = []
        settings = downloader_settings(ytdlp_remote_components=True)
        with patch("snow_engine.media.shutil.which", return_value="/usr/local/bin/deno"):
            arguments, available = _javascript_runtime_args(settings, logs.append)

        self.assertTrue(available)
        self.assertEqual(
            arguments,
            ["--js-runtimes", "deno:/usr/local/bin/deno", "--remote-components", "ejs:github"],
        )
        self.assertTrue(any("Runtime JavaScript" in message for message in logs))

    def test_missing_deno_is_actionable_but_not_fatal(self):
        logs = []
        with patch("snow_engine.media.shutil.which", return_value=None):
            arguments, available = _javascript_runtime_args(downloader_settings(), logs.append)

        self.assertFalse(available)
        self.assertEqual(arguments, [])
        self.assertTrue(any("Deno não foi encontrado" in message for message in logs))


if __name__ == "__main__":
    unittest.main()
