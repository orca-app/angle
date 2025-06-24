import argparse
import os
import sys
import platform
import shutil
import subprocess
from contextlib import contextmanager

def onerror(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=onerror)``
    """
    import stat
    # Is the error an access error?
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise

def yeetdir(path):
    os.makedirs(path, exist_ok=True)
    shutil.rmtree(path, onerror=onerror)

@contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(previous_dir)

##### main:

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="release", help="compile in debug config (default is release)")
argv = sys.argv[1:]
args = parser.parse_args(argv)

ANGLE_COMMIT = ""
with open("commit.txt", "r") as f:
    ANGLE_COMMIT = f.read().strip()

if ANGLE_COMMIT == "":
	print("Failed to find commit.txt")
	exit(1)

input_config = args.config
config = input_config.lower()
if config != "release" and config != "debug":
	print("Invalid configuration " + config + ", only 'release' or 'debug' allowed")
	exit(1)

print("Building angle at sha " + ANGLE_COMMIT + " in config: " + config)

os.makedirs("build", exist_ok=True)

with pushd("build"):
    # get depot tools repo
    print("  * checking depot tools")
    if not os.path.exists("depot_tools"):
        subprocess.run([
            "git", "clone", "--depth=1", "--no-tags", "--single-branch",
            "https://chromium.googlesource.com/chromium/tools/depot_tools.git"
        ], check=True)
    os.environ["PATH"] = os.path.join(os.getcwd(), "depot_tools") + os.pathsep + os.environ["PATH"]
    os.environ["DEPOT_TOOLS_WIN_TOOLCHAIN"] = "0"

    # get angle repo
    print("  * checking angle")
    if not os.path.exists("angle"):
        subprocess.run([
            "git", "clone", "--no-tags", "--single-branch",
            "https://chromium.googlesource.com/angle/angle"
        ], check=True)

    with pushd("angle"):
        subprocess.run([
            "git", "fetch", "--no-tags"
        ], check=True)

        subprocess.run([
            "git", "reset", "--hard", ANGLE_COMMIT
        ], check=True)

        subprocess.run([
            sys.executable, "scripts/bootstrap.py"
        ], check=True)

        shell = True if platform.system() == "Windows" else False
        subprocess.run(["gclient", "sync"], shell=shell, check=True)

        print("  * preparing build")

        is_debug = "false" if config == "release" else "true"

        gnargs = [
            "angle_build_all=false",
            "angle_build_tests=false",
            f"is_debug={is_debug}",
            "is_component_build=false",
        ]

        if platform.system() == "Windows":
            gnargs += [
                "angle_enable_d3d9=false",
                "angle_enable_gl=false",
                "angle_enable_vulkan=false",
                "angle_enable_null=false",
                "angle_has_frame_capture=false"
            ]
        else:
            gnargs += [
                #NOTE(martin): oddly enough, this is needed to avoid deprecation errors when _not_ using OpenGL,
                #              because angle uses some CGL APIs to detect GPUs.
                "treat_warnings_as_errors=false",
                "angle_enable_metal=true",
                "angle_enable_gl=false",
                "angle_enable_vulkan=false",
                "angle_enable_null=false"
            ]

        gnargString = ' '.join(gnargs)

        subprocess.run(["gn", "gen", f"out/{config}", f"--args={gnargString}"], shell=shell, check=True)

        print("  * building")
        subprocess.run(["autoninja", "-C", f"out/{config}", "libEGL", "libGLESv2"], shell=shell, check=True)

    # package result
    print("  * copying build artifacts...")

    yeetdir("angle.out")
    os.makedirs("angle.out/include", exist_ok=True)
    os.makedirs("angle.out/lib", exist_ok=True)

    # - includes
    shutil.copytree("angle/include/KHR", "angle.out/include/KHR", dirs_exist_ok=True)
    shutil.copytree("angle/include/EGL", "angle.out/include/EGL", dirs_exist_ok=True)
    shutil.copytree("angle/include/GLES", "angle.out/include/GLES", dirs_exist_ok=True)
    shutil.copytree("angle/include/GLES2", "angle.out/include/GLES2", dirs_exist_ok=True)
    shutil.copytree("angle/include/GLES3", "angle.out/include/GLES3", dirs_exist_ok=True)

    # - libs
    if platform.system() == "Windows":
        shutil.copy(f"angle/out/{config}/libEGL.dll", "angle.out/lib/")
        shutil.copy(f"angle/out/{config}/libGLESv2.dll", "angle.out/lib/")

        shutil.copy(f"angle/out/{config}/libEGL.dll.lib", "angle.out/lib/")
        shutil.copy(f"angle/out/{config}/libGLESv2.dll.lib", "angle.out/lib/")

        subprocess.run(["copy", "/y",
                        "%ProgramFiles(x86)%\\Windows Kits\\10\\Redist\\D3D\\x64\\d3dcompiler_47.dll",
                        "angle.out\\lib\\"], shell=True, check=True)
    else:
        shutil.copy(f"angle/out/{config}/libEGL.dylib", "angle.out/lib")
        shutil.copy(f"angle/out/{config}/libGLESv2.dylib", "angle.out/lib")
