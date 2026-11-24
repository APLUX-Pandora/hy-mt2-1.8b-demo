"""Install the paired prebuilt library; never compile the model engine at pip install."""
import hashlib
import json
import re
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.errors import SetupError
from wheel.bdist_wheel import bdist_wheel

ROOT = Path(__file__).resolve().parent


class BuildSDK(build_py):
    def run(self):
        try:
            pairing = json.loads((ROOT / "native-library.json").read_text())
            revision = pairing["source_revision"]
            if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
                raise ValueError("Invalid native source revision")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise SetupError(
                "Native SDK build information is missing or invalid. Use a fresh clone of the Demo to install the SDK."
            ) from error
        library = ROOT / "lib" / pairing["filename"]
        if not library.is_file():
            raise SetupError("The bundled native SDK library is missing. Use a fresh clone of the Demo to install the SDK.")
        payload = library.read_bytes()
        if payload[:4] != b"\x7fELF" or int.from_bytes(payload[18:20], "little") != 183:
            raise SetupError("The SDK payload must be a Linux AArch64 ELF")
        if hashlib.sha256(payload).hexdigest() != pairing["sha256"]:
            raise SetupError("Native SDK SHA256 does not match native-library.json")
        notices = ("LICENSE", "THIRD_PARTY_NOTICES.txt", "LICENSES")
        for name in notices:
            if not (ROOT / "lib" / name).exists():
                raise SetupError("Missing native SDK licensing: " + name)
        qnn_source = ROOT / "lib/qnn248"
        manifest_path = ROOT / "qnn-runtime-files.json"
        if not manifest_path.is_file() or hashlib.sha256(manifest_path.read_bytes()).hexdigest() != pairing.get("qnn_runtime_manifest_sha256"):
            raise SetupError("Missing or mismatched bundled QNN runtime inventory")
        qnn_rows = json.loads(manifest_path.read_text())["files"]
        expected = {row["path"] for row in qnn_rows}
        if qnn_source.is_symlink() or not qnn_source.is_dir():
            raise SetupError("Missing bundled QNN runtime")
        actual = {str(p.relative_to(qnn_source)) for p in qnn_source.rglob("*") if p.is_file() or p.is_symlink()}
        if actual != expected:
            raise SetupError("Bundled QNN runtime file closure differs")
        for row in qnn_rows:
            rel = Path(row["path"])
            file = qnn_source / rel
            if rel.is_absolute() or ".." in rel.parts or file.is_symlink() or file.stat().st_size != row["bytes"] or hashlib.sha256(file.read_bytes()).hexdigest() != row["sha256"]:
                raise SetupError("Bundled QNN runtime integrity mismatch: " + str(rel))
        super().run()
        target = Path(self.build_lib) / "pandora_hy_mt2_1_8b" / "_runtime"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(qnn_source, target / "qnn248", dirs_exist_ok=True)
        shutil.copy2(manifest_path, target / manifest_path.name)
        shutil.copy2(ROOT / "qnn-runtime-manifest.json", target / "qnn-runtime-manifest.json")
        shutil.copy2(library, target / library.name)
        shutil.copy2(ROOT / "native-library.json", target / "native-library.json")
        for name in notices:
            source = ROOT / "lib" / name
            if source.is_dir():
                shutil.copytree(source, target / name, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target / name)


class LinuxAArch64Wheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False
        self.plat_name = "linux_aarch64"

    def run(self):
        # Build and install into fresh directories even when this checkout has
        # been used for an older wheel with a different payload.
        with TemporaryDirectory(prefix="pandora-wheel-") as scratch:
            base = Path(scratch)
            build = self.reinitialize_command("build", reinit_subcommands=True)
            build.build_base = str(base / "build")
            self.bdist_dir = str(base / "wheel")
            self.skip_build = False
            super().run()

    def get_tag(self):
        return "py3", "none", "linux_aarch64"


setup(cmdclass={"build_py": BuildSDK, "bdist_wheel": LinuxAArch64Wheel})
