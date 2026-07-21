"""Build system detection and execution for Harhub's build-from-source
pipeline. Each BuildSystem knows how to detect itself from files present
in a project directory, what command to run, and where to look for the
resulting binary afterward.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BuildSystem:
    name: str
    marker_files: list[str]           # any of these present => detected
    default_command: list[str]        # command run inside the project dir
    output_globs: list[str]           # glob patterns (relative to project dir) to find built binaries
    setup: str = ""                   # human-readable note, shown in logs


BUILD_SYSTEMS: list[BuildSystem] = [
    BuildSystem(
        name="gradle",
        marker_files=["gradlew"],
        default_command=["./gradlew", "assembleRelease", "--no-daemon", "--console=plain"],
        output_globs=["**/build/outputs/apk/**/*.apk", "**/build/libs/*.jar"],
    ),
    BuildSystem(
        name="cmake",
        marker_files=["CMakeLists.txt"],
        default_command=None,  # handled specially: configure + build, see run_cmake_build
        output_globs=["build/**/*"],  # narrowed further after build by executable-bit filtering
    ),
    BuildSystem(
        name="make",
        marker_files=["Makefile", "makefile", "GNUmakefile"],
        default_command=["make", "-j$(nproc)"],
        output_globs=["*", "bin/*", "build/*", "out/*"],
    ),
    BuildSystem(
        name="cargo",
        marker_files=["Cargo.toml"],
        default_command=["cargo", "build", "--release"],
        output_globs=["target/release/*"],
    ),
    BuildSystem(
        name="npm",
        marker_files=["package.json"],
        default_command=["npm", "ci", "&&", "npm", "run", "build"],
        output_globs=["dist/**/*", "build/**/*", "out/**/*"],
    ),
]


def detect_build_system(project_dir: Path, forced: str = "auto") -> BuildSystem:
    if forced != "auto":
        matches = [b for b in BUILD_SYSTEMS if b.name == forced]
        if not matches:
            raise ValueError(f"Unknown build_system '{forced}' — must be one of: {[b.name for b in BUILD_SYSTEMS] + ['auto']}")
        return matches[0]

    for build_system in BUILD_SYSTEMS:
        for marker in build_system.marker_files:
            if (project_dir / marker).exists():
                return build_system

    raise RuntimeError(
        f"Could not detect a build system in '{project_dir}'. "
        f"Looked for: {[m for b in BUILD_SYSTEMS for m in b.marker_files]}. "
        f"Specify build_system explicitly if your project uses something else."
    )


def run_build(project_dir: Path, build_system: BuildSystem, override_command: str = "") -> None:
    if override_command:
        command = override_command
        shell = True
    elif build_system.name == "gradle":
        gradlew = project_dir / "gradlew"
        gradlew.chmod(gradlew.stat().st_mode | 0o111)
        command = " ".join(build_system.default_command)
        shell = True
    elif build_system.name == "cmake":
        _run_cmake_configure_and_build(project_dir)
        return
    else:
        command = " ".join(build_system.default_command)
        shell = True

    print(f"[{build_system.name}] running: {command}")
    result = subprocess.run(command, shell=shell, cwd=project_dir, capture_output=True, text=True)
    print(result.stdout[-4000:])
    if result.returncode != 0:
        print(result.stderr[-4000:])
        raise RuntimeError(f"{build_system.name} build failed with exit code {result.returncode}")


def _run_cmake_configure_and_build(project_dir: Path) -> None:
    build_dir = project_dir / "build"
    build_dir.mkdir(exist_ok=True)

    print("[cmake] configuring...")
    configure = subprocess.run(
        ["cmake", "-S", str(project_dir), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"],
        capture_output=True, text=True,
    )
    print(configure.stdout[-2000:])
    if configure.returncode != 0:
        print(configure.stderr[-2000:])
        raise RuntimeError(f"cmake configure failed with exit code {configure.returncode}")

    print("[cmake] building...")
    build = subprocess.run(
        ["cmake", "--build", str(build_dir), "--config", "Release", "--parallel"],
        capture_output=True, text=True,
    )
    print(build.stdout[-4000:])
    if build.returncode != 0:
        print(build.stderr[-4000:])
        raise RuntimeError(f"cmake build failed with exit code {build.returncode}")

def find_binary_by_override(project_dir: Path, output_path: str = "", output_glob: str = "") -> list[Path]:
    """Resolves the built binary using an explicit path or glob from a
    commands.toml override, bypassing the generic output_globs guesswork
    entirely — used when a project's build output doesn't land somewhere
    the auto-detector would find on its own.
    """
    if output_path:
        resolved = project_dir / output_path
        if not resolved.is_file():
            raise RuntimeError(
                f"commands.toml specifies output_path='{output_path}' but no file "
                f"was found at '{resolved}' after the build."
            )
        return [resolved]

    if output_glob:
        matches = sorted(p for p in project_dir.glob(output_glob) if p.is_file())
        if not matches:
            raise RuntimeError(
                f"commands.toml specifies output_glob='{output_glob}' but it matched "
                f"no files under '{project_dir}' after the build."
            )
        return matches

    raise ValueError("find_binary_by_override called without output_path or output_glob")

def find_built_binaries(project_dir: Path, build_system: BuildSystem) -> list[Path]:
    candidates: list[Path] = []
    for pattern in build_system.output_globs:
        candidates.extend(project_dir.glob(pattern))

    # Keep only actual files, and for generic patterns (make/cmake) filter
    # down to files that are either executable or have a known binary
    # extension — avoids picking up object files, logs, or source copies.
    known_binary_exts = {".apk", ".exe", ".jar", ".appimage", ".deb", ".rpm", ".zip", ".tar.gz", ".so", ".dll", ".dylib"}

    results = []
    for path in candidates:
        if not path.is_file():
            continue
        is_executable = bool(path.stat().st_mode & 0o111)
        has_known_ext = any(path.name.lower().endswith(ext) for ext in known_binary_exts)
        if is_executable or has_known_ext:
            results.append(path)

    # De-duplicate while preserving order
    seen = set()
    unique_results = []
    for path in results:
        if path not in seen:
            seen.add(path)
            unique_results.append(path)

    if not unique_results:
        raise RuntimeError(
            f"[{build_system.name}] build succeeded but no output binary was found "
            f"matching patterns {build_system.output_globs}. Check output_globs or "
            f"use build_command to build+place the binary explicitly."
        )

    return unique_results