import os
import subprocess
import sys
import zipfile
import urllib.request
from pathlib import Path

# Paths
SDK_DIR = Path(r"C:\Users\manig\AppData\Local\Android\Sdk")
JAVA_HOME = Path(r"C:\Program Files\Android\Android Studio\jbr")
WORKSPACE_DIR = Path(r"C:\Users\manig\ollama_workspace")
PROJECT_DIR = WORKSPACE_DIR / "HelloWorldAndroidApp"
GRADLE_DIR = WORKSPACE_DIR / "gradle-8.7"
GRADLE_BIN = GRADLE_DIR / "bin" / "gradle.bat"

print(f"[1/5] Setting up environment...")
os.environ["JAVA_HOME"] = str(JAVA_HOME)
os.environ["ANDROID_HOME"] = str(SDK_DIR)
os.environ["PATH"] = f"{JAVA_HOME / 'bin'};{GRADLE_DIR / 'bin'};" + os.environ["PATH"]

PROJECT_DIR.mkdir(parents=True, exist_ok=True)

# 1. gradle.properties
(PROJECT_DIR / "gradle.properties").write_text("""
android.useAndroidX=true
android.nonTransitiveRClass=true
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
""", encoding="utf-8")

# 2. settings.gradle
(PROJECT_DIR / "settings.gradle").write_text("""
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "HelloWorldAndroidApp"
include ':app'
""", encoding="utf-8")

# 3. Top-level build.gradle
(PROJECT_DIR / "build.gradle").write_text("""
plugins {
    id 'com.android.application' version '8.2.2' apply false
}
""", encoding="utf-8")

# 4. app/build.gradle - Pure Java without external dependencies
APP_DIR = PROJECT_DIR / "app"
APP_DIR.mkdir(parents=True, exist_ok=True)

(APP_DIR / "build.gradle").write_text("""
plugins {
    id 'com.android.application'
}

android {
    namespace 'com.example.helloworld'
    compileSdk 34

    defaultConfig {
        applicationId "com.example.helloworld"
        minSdk 24
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }

    buildTypes {
        release {
            minifyEnabled false
        }
    }
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}
""", encoding="utf-8")

# 5. AndroidManifest.xml
MAIN_DIR = APP_DIR / "src" / "main"
MAIN_DIR.mkdir(parents=True, exist_ok=True)

(MAIN_DIR / "AndroidManifest.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:allowBackup="true"
        android:label="Hello World"
        android:supportsRtl="true">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
""", encoding="utf-8")

# 6. MainActivity.java
JAVA_SRC_DIR = MAIN_DIR / "java" / "com" / "example" / "helloworld"
JAVA_SRC_DIR.mkdir(parents=True, exist_ok=True)

(JAVA_SRC_DIR / "MainActivity.java").write_text("""package com.example.helloworld;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;
import android.view.Gravity;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        TextView textView = new TextView(this);
        textView.setText("Hello World from Autonomous Agent!");
        textView.setTextSize(26);
        textView.setGravity(Gravity.CENTER);
        setContentView(textView);
    }
}
""", encoding="utf-8")

print(f"[4/5] Building Android APK using Gradle...")
cmd = f'"{GRADLE_BIN}" assembleDebug'
result = subprocess.run(cmd, shell=True, cwd=str(PROJECT_DIR), capture_output=True, text=True)

print("STDOUT:", result.stdout[-2500:] if result.stdout else "")
print("STDERR:", result.stderr[-2500:] if result.stderr else "")

APK_PATH = APP_DIR / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
DEST_APK = WORKSPACE_DIR / "HelloWorld-debug.apk"

if APK_PATH.exists():
    import shutil
    shutil.copy(APK_PATH, DEST_APK)
    print(f"\n[SUCCESS 5/5] APK generated successfully!")
    print(f"APK Location: {DEST_APK}")
    print(f"Size: {DEST_APK.stat().st_size / (1024*1024):.2f} MB")
else:
    print("\n[!] APK build failed. Check log above.")
