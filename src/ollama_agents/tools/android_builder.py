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
    output_filename: str = "app-debug.apk",
    project_dir: Optional[str] = None
) -> str:
    """Compile and build a signed debug Android APK (.apk) file from source code.

    Args:
        app_name: Name of the application.
        main_activity_code: Full Java source code for MainActivity.java.
                            If omitted or empty, uses existing MainActivity.java.
        package_name: Android Java package namespace (default 'com.example.helloworld').
        output_filename: Output APK filename to save in ~/ollama_workspace/ (e.g. 'app-debug.apk').
        project_dir: Optional path or subfolder for the Android project.
    """
    try:
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        clean_name = output_filename if output_filename.endswith(".apk") else f"{output_filename}.apk"

        # Determine target project directory
        target_dir = None
        if project_dir:
            p_path = Path(project_dir).expanduser()
            if p_path.is_absolute() and p_path.exists():
                target_dir = p_path
            elif (WORKSPACE_ROOT / project_dir).exists():
                target_dir = WORKSPACE_ROOT / project_dir
            elif (Path(__file__).resolve().parent.parent.parent.parent / project_dir).exists():
                target_dir = Path(__file__).resolve().parent.parent.parent.parent / project_dir

        if not target_dir:
            # Check for 2048 game or specific project hints
            hints = [app_name.lower(), clean_name.lower(), str(project_dir or "").lower()]
            if any("2048" in h for h in hints):
                candidate_paths = [
                    WORKSPACE_ROOT / "2048_game_application",
                    WORKSPACE_ROOT / "android_2048_game",
                    Path(__file__).resolve().parent.parent.parent.parent / "android_2048_game"
                ]
                for cp in candidate_paths:
                    if cp.exists() and ((cp / "build.gradle.kts").exists() or (cp / "build.gradle").exists() or (cp / "app").exists()):
                        target_dir = cp
                        break

        if not target_dir:
            target_dir = ANDROID_APP_DIR

        if not target_dir.exists():
            return f"Error: Android project directory '{target_dir}' not found."

        # Setup paths if modifying Java code in standard structure
        pkg_rel_dir = package_name.replace(".", "/")
        java_src_dir = target_dir / "app" / "src" / "main" / "java" / pkg_rel_dir
        if java_src_dir.exists() and main_activity_code and main_activity_code.strip():
            main_activity_file = java_src_dir / "MainActivity.java"
            main_activity_file.write_text(main_activity_code.strip(), encoding="utf-8")
            logger.info("Updated %s with new activity source code (%d chars)", main_activity_file, len(main_activity_code))

        # Check Gradle binary - prefer local wrapper if present
        local_gradlew = target_dir / "gradlew.bat"
        if local_gradlew.exists():
            gradle_exec = str(local_gradlew)
        elif GRADLE_BIN.exists():
            gradle_exec = str(GRADLE_BIN)
        else:
            return f"Error: Gradle wrapper not found at '{local_gradlew}' or '{GRADLE_BIN}'."

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

        logger.info("Running Gradle assembleDebug in %s...", target_dir)
        cmd = [gradle_exec, "-p", str(target_dir), "assembleDebug"]
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=180
        )

        # Locate generated APK
        source_apk = None
        candidates = [
            target_dir / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
            target_dir / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
        ]
        for c in candidates:
            if c.exists():
                source_apk = c
                break

        if not source_apk:
            # Search recursively in target_dir outputs
            apk_files = list((target_dir / "app" / "build" / "outputs").glob("**/*.apk")) if (target_dir / "app" / "build" / "outputs").exists() else []
            if apk_files:
                source_apk = apk_files[0]

        if not source_apk and proc.returncode != 0:
            return f"[Build Failed with exit code {proc.returncode}]\nSTDOUT: {proc.stdout[-1500:]}\nSTDERR: {proc.stderr[-1500:]}"
        elif not source_apk:
            return f"Build completed, but output APK not found in '{target_dir}'."

        dest_apk = WORKSPACE_ROOT / clean_name
        shutil.copy2(source_apk, dest_apk)
        # Also ensure copy in target_dir if target_dir is inside workspace
        if target_dir != WORKSPACE_ROOT and target_dir.parent == WORKSPACE_ROOT:
            try:
                shutil.copy2(source_apk, target_dir / clean_name)
            except Exception:
                pass


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

