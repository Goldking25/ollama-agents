"""Android APK Builder Tool for Ollama Agents.

Compiles Android Java/Kotlin source projects or generates ready-to-install debug .apk
files using local Android SDK and Gradle tooling installed in ~/ollama_workspace/.
"""

import os
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path.home() / "ollama_workspace"
ANDROID_APP_DIR = WORKSPACE_ROOT / "HelloWorldAndroidApp"
GRADLE_BIN = WORKSPACE_ROOT / "gradle-8.7" / "bin" / "gradle.bat"


def build_android_apk(
    app_name: str = "NearbyShareApp",
    main_activity_code: Optional[str] = None,
    package_name: str = "com.example.helloworld",
    output_filename: str = "app-debug.apk"
) -> str:
    """Compile and build a signed debug Android APK (.apk) file from source code.

    Args:
        app_name: Name of the application.
        main_activity_code: Full Java source code for MainActivity.java.
                            If omitted or empty, uses existing MainActivity.java.
        package_name: Android Java package namespace (default 'com.example.helloworld').
        output_filename: Output APK filename to save in ~/ollama_workspace/ (e.g. 'app-debug.apk').
    """
    try:
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        if not ANDROID_APP_DIR.exists():
            return f"Error: Android project directory '{ANDROID_APP_DIR}' not found."

        # Setup paths
        pkg_rel_dir = package_name.replace(".", "/")
        java_src_dir = ANDROID_APP_DIR / "app" / "src" / "main" / "java" / pkg_rel_dir
        java_src_dir.mkdir(parents=True, exist_ok=True)
        main_activity_file = java_src_dir / "MainActivity.java"

        # If user/agent provided updated source code, write it
        if main_activity_code and main_activity_code.strip():
            main_activity_file.write_text(main_activity_code.strip(), encoding="utf-8")
            logger.info("Updated %s with new activity source code (%d chars)", main_activity_file, len(main_activity_code))

        # Check Gradle binary
        if not GRADLE_BIN.exists():
            return f"Error: Gradle wrapper not found at '{GRADLE_BIN}'."

        # Locate Android SDK
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        android_sdk = Path(local_app_data) / "Android" / "Sdk"
        if not android_sdk.exists():
            android_sdk = Path("C:/Android/Sdk")

        env = os.environ.copy()
        if android_sdk.exists():
            env["ANDROID_HOME"] = str(android_sdk)
            env["ANDROID_SDK_ROOT"] = str(android_sdk)

        # Look for JDK
        adoptium_jdk = Path("C:/Program Files/Eclipse Adoptium/jdk-21.0.6.7-hotspot")
        if adoptium_jdk.exists():
            env["JAVA_HOME"] = str(adoptium_jdk)

        logger.info("Running Gradle assembleDebug in %s...", ANDROID_APP_DIR)
        cmd = [str(GRADLE_BIN), "-p", str(ANDROID_APP_DIR), "assembleDebug"]
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=180
        )

        if proc.returncode != 0:
            return f"[Build Failed with exit code {proc.returncode}]\nSTDOUT: {proc.stdout[-1500:]}\nSTDERR: {proc.stderr[-1500:]}"

        # Locate generated APK
        source_apk = ANDROID_APP_DIR / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if not source_apk.exists():
            return f"Build completed, but output APK not found at '{source_apk}'."

        # Ensure output filename ends with .apk
        clean_name = output_filename if output_filename.endswith(".apk") else f"{output_filename}.apk"
        dest_apk = WORKSPACE_ROOT / clean_name
        shutil.copy2(source_apk, dest_apk)

        apk_size = dest_apk.stat().st_size
        return (
            f"Successfully compiled and built Android APK: `{clean_name}`\n"
            f"- Path: `{dest_apk}`\n"
            f"- File Size: {apk_size} bytes ({(apk_size / 1024):.1f} KB)\n"
            f"- Download URL: `/workspace/{clean_name}`\n\n"
            f"The APK is ready for direct installation on any Android phone or tablet!"
        )
    except Exception as e:
        logger.error("Error building Android APK: %s", e)
        return f"Failed to build Android APK: {type(e).__name__}: {e}"


def prewarm_gradle_daemon() -> None:
    """Pre-warm Gradle daemon in background to eliminate first-build startup latency."""
    try:
        if not GRADLE_BIN.exists() or not ANDROID_APP_DIR.exists():
            return
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        android_sdk = Path(local_app_data) / "Android" / "Sdk"
        if not android_sdk.exists():
            android_sdk = Path("C:/Android/Sdk")
        env = os.environ.copy()
        if android_sdk.exists():
            env["ANDROID_HOME"] = str(android_sdk)
            env["ANDROID_SDK_ROOT"] = str(android_sdk)
        adoptium_jdk = Path("C:/Program Files/Eclipse Adoptium/jdk-21.0.6.7-hotspot")
        if adoptium_jdk.exists():
            env["JAVA_HOME"] = str(adoptium_jdk)

        logger.info("Pre-warming Gradle daemon in background...")
        subprocess.Popen(
            [str(GRADLE_BIN), "-p", str(ANDROID_APP_DIR), "--status"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        logger.debug("Gradle pre-warm skipped: %s", e)

