# Technical Exploration & Implementation Plan: Manifest, ProGuard & Build Validation

**Auditor / Author:** explorer_m1_3 (Manifest, Proguard & Build Validation Explorer)  
**Milestone:** M1 — Project Scaffolding & Build Toolchain  
**Target Project:** `android_2048_game` (`e:\Learning\Python\agent_test\android_2048_game`)  
**Target Files:**  
- `app/src/main/AndroidManifest.xml`  
- `app/proguard-rules.pro`  
- Milestone 1 Verification Command Pipeline  
**Reference Documents:**  
- User Request: `e:\Learning\Python\agent_test\ORIGINAL_REQUEST.md`  
- Project Scope: `e:\Learning\Python\agent_test\PROJECT.md`  
- Environment Survey: `e:\Learning\Python\agent_test\.agents\explorer_survey_1\environment_report.md`  
- Architecture Specification: `e:\Learning\Python\agent_test\.agents\spec_miner_survey_2\spec_architecture.md`  
- Peer Explorer Plan: `e:\Learning\Python\agent_test\.agents\explorer_m1_2\app_gradle_plan.md`  

---

## 1. Executive Summary & Architecture Context

Milestone 1 establishes the foundational scaffolding, build toolchain, and validation harness for the Android 2048 Game App. This document specifies the exact, production-ready implementation for three core infrastructure elements:

1. **`app/src/main/AndroidManifest.xml`**:
   - Modern AGP 8.7.2 compliance with decoupled namespace (`com.game2048.android`).
   - Zero-permission architecture ensuring user privacy, security, and instantaneous install.
   - Application-wide hardware acceleration (`android:hardwareAccelerated="true"`) to guarantee 60+ FPS zero-allocation Canvas 2D rendering.
   - Mandatory Android 12+ (API 31–35) `android:exported="true"` on `MainActivity`.
   - Edge-to-edge AppCompat theme reference and adaptive orientation support across phone form factors.
   - Resource prerequisites required for AAPT2 compilation.

2. **`app/proguard-rules.pro`**:
   - Full-mode R8 code shrinking and optimization rules to achieve an ultra-lean binary footprint (< 1.8 MB release APK vs. the 5 MB ceiling).
   - Component preservation for Android framework classes (`Activity`, `View`, `ViewModel`).
   - Explicit retention of custom view constructors (`GameBoardView`) required for layout XML inflation.
   - Field and method preservation for pure Kotlin domain models and JSON persistence records to prevent serialization failure.
   - Complete stripping of non-fatal logging calls (`Log.v`, `Log.d`, `Log.i`, `Log.w`) in release builds.

3. **Milestone 1 Verification Command Pipeline**:
   - Deterministic, multi-stage CLI verification sequence tailored for Windows PowerShell and Command Prompt.
   - Pipeline covering Gradle wrapper sanity, task graph evaluation, dry-run dependency checks, debug compilation, test runner execution, release minification, and automated APK size enforcement.

---

## 2. Specification: `app/src/main/AndroidManifest.xml`

### 2.1 Complete Production-Ready File Content

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">

    <!-- Zero runtime or install permissions required (Ultra-lean, private, self-contained) -->

    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/Theme.Game2048"
        android:hardwareAccelerated="true"
        tools:targetApi="31">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:theme="@style/Theme.Game2048"
            android:hardwareAccelerated="true"
            android:windowSoftInputMode="adjustNothing"
            android:configChanges="keyboard|keyboardHidden"
            android:label="@string/app_name">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

    </application>

</manifest>
```

### 2.2 Deep Architectural Breakdown & Rationale

#### A. Package & Namespace Decoupling
- **Standard AGP 8.x Practice:** Under AGP 8.0+, specifying `package="..."` inside `<manifest>` is deprecated. The build system derives the R class package and BuildConfig namespace exclusively from `namespace = "com.game2048.android"` in `app/build.gradle.kts`.
- **Class Reference Resolution:** The relative activity name `.MainActivity` cleanly resolves to `com.game2048.android.MainActivity`.
- **Namespaces:** Standard `xmlns:android` and `xmlns:tools` are declared at the root element to support build tool annotations (`tools:targetApi`).

#### B. Zero-Permission Policy
- In accordance with `spec_architecture.md` (Section 8.1, line 371), the 2048 game is completely self-contained. It operates locally with no network calls, camera access, external storage requests, or telemetry.
- No `<uses-permission>` tags are declared. This ensures immediate installation without runtime permission dialogues, minimizes APK size overhead, and provides maximum user trust.

#### C. Application Tag Attributes
- **`android:allowBackup="true"`**: Enables Android standard backup for persistent game data (high score, unlocked levels) stored in private SharedPreferences.
- **`android:icon` & `android:roundIcon`**: References standard launcher icons (`@mipmap/ic_launcher` and `@mipmap/ic_launcher_round`).
- **`android:label="@string/app_name"`**: Resolves to the application display string (`"2048"`).
- **`android:supportsRtl="true"`**: Guarantees layout compatibility with Right-to-Left system locales.
- **`android:theme="@style/Theme.Game2048"`**: References the application edge-to-edge AppCompat theme.
- **`android:hardwareAccelerated="true"`**:
  - *Critical Performance Requirement:* Mandated by `PROJECT.md` §F13 and `spec_architecture.md` §2.2.
  - Ensures the Android framework executes Canvas 2D operations (`drawRoundRect`, `drawText`, `drawColor`) directly on the GPU via the RenderThread.
  - Eliminates software rasterization bottlenecks, providing steady 60+ FPS touch responsiveness within the 16.6 ms (and 120 Hz 8.3 ms) frame budget.
- **`tools:targetApi="31"`**: Guides AAPT2 and lint analyzer for minimum supported API level 31 (Android 12).

#### D. MainActivity Declaration
- **`android:name=".MainActivity"`**: Points to `com.game2048.android.MainActivity`.
- **`android:exported="true"`**:
  - *MANDATORY FOR ANDROID 12+ (API 31–35):* Android 12 enforces that any activity defining an `<intent-filter>` must explicitly specify `android:exported`. Failure to specify this attribute results in an immediate AAPT2 manifest merge compilation error:
    `Apps targeting Android 12 and higher are required to specify an explicit value for android:exported when the corresponding component has an intent filter defined.`
  - Setting `android:exported="true"` allows Android's home screen launcher (`Launcher3`, Pixel Launcher, Samsung One UI) to start `MainActivity`.
- **`android:theme="@style/Theme.Game2048"`**: Applied explicitly to ensure no default action bar or incompatible window styling is inherited.
- **`android:windowSoftInputMode="adjustNothing"`**: Prevents the soft keyboard from unexpectedly resizing the layout viewport during non-text interactions.

#### E. Orientation & Responsive Layout Adaptation Strategy
In `ORIGINAL_REQUEST.md` (Acceptance Criteria, line 37) and `PROJECT.md` (§F16, line 30), the app must adapt across phone screen densities and orientations. Two architectural strategies were evaluated:

| Strategy | Implementation in Manifest | Behavior | Evaluated Verdict |
|---|---|---|---|
| **Strategy A: Resource Qualification (Dual XML)** | *Default:* Do not intercept `orientation\|screenSize` | Activity recreates on rotate; Android automatically swaps between `res/layout/activity_main.xml` (portrait) and `res/layout-land/activity_main.xml` (landscape). Game state is retained in `GameViewModel`. | **RECOMMENDED & ADOPTED** (Aligns with `PROJECT.md` line 144 and `spec_architecture.md` Section 8.3) |
| **Strategy B: Manual In-Place Configuration** | `android:configChanges="orientation\|screenSize\|screenLayout\|smallestScreenSize"` | Activity is not recreated; `onConfigurationChanged()` must manually rebind or adjust layout constraints. | Valid alternative if single dynamic ConstraintLayout is used. |

To support Strategy A cleanly while avoiding spurious recreations from external hardware dock/keyboard events, the manifest specifies:
```xml
android:configChanges="keyboard|keyboardHidden"
```
Screen orientation is intentionally **unconstrained** (no `android:screenOrientation="portrait"` locking), allowing free rotation between portrait and landscape modes.

#### F. Edge-to-Edge System Bars & Cutouts
In Android 15 (targetSdk 35), edge-to-edge layout is enforced by default. To ensure uniform behavior from Android 12 through Android 15:
- The theme sets transparent system bars:
  ```xml
  <item name="android:statusBarColor">@android:color/transparent</item>
  <item name="android:navigationBarColor">@android:color/transparent</item>
  ```
- MainActivity coordinates with `WindowInsetsCompat` to pad HUD elements safely away from system bars and camera cutouts without clipping game controls.

---

### 2.3 Supporting Resource Prerequisites for Manifest Validation

During Milestone 1 compilation, AAPT2 parses `AndroidManifest.xml` and validates all resource references. If referenced resources are missing, AAPT2 will halt compilation with fatal errors. Therefore, the implementation worker must ensure the following minimal resource files are co-located in `app/src/main/res/`:

#### 1. String Resource: `app/src/main/res/values/strings.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">2048</string>
</resources>
```

#### 2. Theme Resource: `app/src/main/res/values/themes.xml`
Because `explorer_m1_2` selected `androidx.appcompat:appcompat:1.7.0` (and rejected heavy Material components to keep APK < 1.8 MB), the base theme inherits from `Theme.AppCompat.DayNight.NoActionBar`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.Game2048" parent="Theme.AppCompat.DayNight.NoActionBar">
        <!-- Edge-to-edge transparent system bars -->
        <item name="android:statusBarColor">@android:color/transparent</item>
        <item name="android:navigationBarColor">@android:color/transparent</item>
        <item name="android:windowLightStatusBar">true</item>
        <item name="android:windowLightNavigationBar">true</item>
    </style>
</resources>
```

#### 3. Color Resource: `app/src/main/res/values/colors.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="board_background">#BBADA0</color>
    <color name="cell_empty">#CDC1B4</color>
    <color name="text_dark">#776E65</color>
    <color name="text_light">#F9F6F2</color>
</resources>
```

#### 4. Launcher Icon Vector Drawables: `app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/board_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
```
With `app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/board_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
```
And vector drawable `app/src/main/res/drawable/ic_launcher_foreground.xml`:
```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#F9F6F2"
        android:pathData="M30,30h48v48h-48z" />
</vector>
```

#### 5. Minimal Stub Activity: `app/src/main/java/com/game2048/android/MainActivity.kt`
```kotlin
package com.game2048.android

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
    }
}
```

---

## 3. Specification: `app/proguard-rules.pro`

### 3.1 Complete Production-Ready File Content

```proguard
# ==============================================================================
# Android 2048 Game App — ProGuard & R8 Shrinking Rules
# Optimized for R8 Full Mode with aggressive minification (< 1.8 MB release APK)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. General R8 Optimization & Code Shrinking
# ------------------------------------------------------------------------------
-allowaccessmodification
-repackageclasses ''
-dontusemixedcaseclassnames

# Preserve line numbers for stack trace debugging while stripping source filenames
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# Preserve standard annotations and generic signatures
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod

# ------------------------------------------------------------------------------
# 2. Android Core Framework Preservation
# ------------------------------------------------------------------------------
-keep public class * extends android.app.Activity
-keep public class * extends android.app.Application
-keep public class * extends android.app.Service
-keep public class * extends android.content.BroadcastReceiver
-keep public class * extends android.content.ContentProvider
-keep public class * extends android.app.backup.BackupAgentHelper
-keep public class * extends android.preference.Preference

# ------------------------------------------------------------------------------
# 3. Custom View & XML Layout Inflation
# Preserve GameBoardView and all View constructors required by LayoutInflater
# ------------------------------------------------------------------------------
-keep public class com.game2048.android.ui.GameBoardView {
    public <init>(android.content.Context);
    public <init>(android.content.Context, android.util.AttributeSet);
    public <init>(android.content.Context, android.util.AttributeSet, int);
}

-keepclasseswithmembers class * extends android.view.View {
    public <init>(android.content.Context);
    public <init>(android.content.Context, android.util.AttributeSet);
    public <init>(android.content.Context, android.util.AttributeSet, int);
}

# Preserve methods referenced by android:onClick in XML layouts
-keepclassmembers class * extends android.app.Activity {
    public void *(android.view.View);
}

# ------------------------------------------------------------------------------
# 4. AndroidX ViewModel & Lifecycle
# ------------------------------------------------------------------------------
-keepclassmembers class * extends androidx.lifecycle.ViewModel {
    public <init>(...);
}

# ------------------------------------------------------------------------------
# 5. Kotlin Metadata & Domain Model Preservation
# Prevent R8 full-mode from stripping fields/methods used in JSON serialization
# ------------------------------------------------------------------------------
-keepclassmembers class * extends kotlin.jvm.internal.Lambda {
    <fields>;
}

-keepclassmembers class com.game2048.android.core.model.** {
    <fields>;
    <methods>;
}

-keepclassmembers class com.game2048.android.level.model.** {
    <fields>;
    <methods>;
}

-keepclassmembers class com.game2048.android.persistence.** {
    <fields>;
    <methods>;
}

# ------------------------------------------------------------------------------
# 6. Logging Stripping (Release Build Optimization)
# Completely eliminate non-fatal Log calls in release to save space and CPU cycles.
# Note: Log.e and Log.wtf are deliberately retained for unhandled error diagnostics.
# ------------------------------------------------------------------------------
-assumenosideeffects class android.util.Log {
    public static boolean isLoggable(java.lang.String, int);
    public static int v(...);
    public static int d(...);
    public static int i(...);
    public static int w(...);
}
```

### 3.2 Detailed ProGuard & R8 Optimization Rationale

1. **`-allowaccessmodification` & `-repackageclasses ''`**:
   - Allows R8 to broaden visibility modifiers (e.g. `private` to `public`) to enable aggressive method inlining and dead code elimination.
   - Flattens all package structures into the root package (`''`), reducing string pool size in `classes.dex` and saving ~40–80 KB.
2. **Preserving Custom View Constructors**:
   - `LayoutInflater` uses reflection to instantiate views declared in XML layouts. Without keeping `(Context, AttributeSet)` and `(Context, AttributeSet, int)` constructors, layout inflation throws a fatal `NoSuchMethodException` or `InflateException` at runtime in release builds.
3. **Preserving Pure Kotlin Domain & Persistence Models**:
   - The game persistence engine maps state to JSON (`org.json.JSONObject`). If R8 renames or removes data class properties or getters, serialization fails or produces corrupted state.
   - The rules explicitly protect classes under `com.game2048.android.core.model.**`, `com.game2048.android.level.model.**`, and `com.game2048.android.persistence.**`.
4. **Release Logging Elimination (`-assumenosideeffects`)**:
   - Android apps often execute verbose logging in inner loops. In a high-frequency gesture game, string formatting inside `Log.v` or `Log.d` allocates memory and burns CPU time.
   - Stripping `Log.v`, `Log.d`, `Log.i`, and `Log.w` instructs R8 to remove both the method calls and their argument evaluation bytecode entirely.
   - `Log.e` and `Log.wtf` are kept so fatal errors are not silenced.

---

## 4. Milestone 1 Verification Command Pipeline

This pipeline specifies the exact command sequence that Worker (`worker_m1`) and Reviewers must execute from the project root (`e:\Learning\Python\agent_test\android_2048_game`).

### 4.1 Pipeline Overview Matrix

| Step | Command (PowerShell / CMD) | Objective | Target Exit Code | Key Success Signal |
|:---:|---|---|:---:|---|
| **S1** | `.\gradlew.bat --version` | Verify Gradle wrapper binary & JDK 21 daemon | `0` | Gradle 8.10.2, JVM: 21.0.6 |
| **S2** | `.\gradlew.bat help` | Test Gradle project evaluation & settings script | `0` | `BUILD SUCCESSFUL` |
| **S3** | `.\gradlew.bat projects` | Verify root and `:app` module hierarchy | `0` | `+--- Project ':app'` |
| **S4** | `.\gradlew.bat :app:tasks` | Verify AGP 8.7.2 task registration | `0` | `assembleDebug`, `assembleRelease` present |
| **S5** | `.\gradlew.bat :app:dependencies --configuration implementation` | Verify dependency tree resolution | `0` | `androidx.core:core-ktx:1.15.0`, `appcompat:1.7.0` |
| **S6** | `.\gradlew.bat assembleDebug --dry-run` | Validate complete task execution DAG | `0` | All tasks marked `:app:... SKIPPED` |
| **S7** | `.\gradlew.bat assembleDebug` | Compile Kotlin sources, link AAPT2 resources, generate debug APK | `0` | `app-debug.apk` generated |
| **S8** | `.\gradlew.bat test` | Execute pure JVM unit test suite | `0` | `BUILD SUCCESSFUL` (0 failures) |
| **S9** | `.\gradlew.bat assembleRelease` | Compile with R8 full-mode minification & resource shrinking | `0` | `app-release.apk` generated |
| **S10** | *Size Gate Script (PowerShell)* | Measure release APK size against 5 MB ceiling | `0` | APK < 5,242,880 bytes (Target ~1.5 MB) |

---

### 4.2 Exact Step-by-Step Command Line Specifications

#### Step 1: Toolchain & Wrapper Integrity Verification
Verifies that `gradle-wrapper.jar`, `gradlew.bat`, and `gradle-wrapper.properties` execute cleanly with the local JDK 21:
```powershell
.\gradlew.bat --version
```
*Expected Output:*
```
------------------------------------------------------------
Gradle 8.10.2
------------------------------------------------------------
Build time:    2024-09-23 21:28:39 UTC
Kotlin:        1.9.24
Groovy:        3.0.22
Launcher JVM:  21.0.6 (Eclipse Adoptium 21.0.6+7-LTS)
Daemon JVM:    C:\Program Files\Eclipse Adoptium\jdk-21.0.6.7-hotspot
OS:            Windows 11 10.0 amd64
```

#### Step 2: Project Evaluation & Help Verification
Ensures `settings.gradle.kts`, root `build.gradle.kts`, and `gradle.properties` evaluate without syntax or configuration errors:
```powershell
.\gradlew.bat help
```
*Expected Output:* `BUILD SUCCESSFUL`

#### Step 3: Project Tree Structure Check
Confirms that `:app` is properly included in the project graph:
```powershell
.\gradlew.bat projects
```
*Expected Output:*
```
Root project 'android_2048_game'
\--- Project ':app'
```

#### Step 4: AGP Task Graph Registration Check
Confirms Android Gradle Plugin (AGP 8.7.2) loaded successfully and registered all build, assemble, and test tasks:
```powershell
.\gradlew.bat :app:tasks --group="build"
```
*Expected Output:* Lists `assemble`, `assembleDebug`, `assembleRelease`, `build`, etc.

#### Step 5: Dependency Graph Resolution
Validates that Gradle can resolve all AndroidX libraries from Google Maven and Maven Central:
```powershell
.\gradlew.bat :app:dependencies --configuration implementation
```
*Expected Output:*
```
implementation - Implementation dependencies for compilation and runtime.
+--- androidx.core:core-ktx:1.15.0
|    +--- androidx.core:core:1.15.0
|    \--- org.jetbrains.kotlin:kotlin-stdlib:2.0.21
\--- androidx.appcompat:appcompat:1.7.0
```

#### Step 6: Task Plan Dry-Run Execution
Validates task dependencies and ordering across compilation, manifest merging, and packaging without executing long-running compilation:
```powershell
.\gradlew.bat assembleDebug --dry-run
```
*Expected Output:*
All tasks reported with `:task SKIPPED` and `BUILD SUCCESSFUL`.

#### Step 7: Debug Assembly & DEX Compilation
Compiles the application, links resources through AAPT2, merges the manifest, and packages `app-debug.apk`:
```powershell
.\gradlew.bat assembleDebug
```
*Expected Output:*
- `BUILD SUCCESSFUL`
- Output artifact created at: `app\build\outputs\apk\debug\app-debug.apk`

#### Step 8: Pure JVM Unit Test Suite Execution
Runs all domain math and logic unit tests:
```powershell
.\gradlew.bat :app:testDebugUnitTest
```
*Expected Output:*
- `BUILD SUCCESSFUL`
- HTML test report generated at: `app\build\reports\tests\testDebugUnitTest\index.html`

#### Step 9: Release Compilation with R8 Full-Mode Shrinking
Executes the R8 code optimizer, dead code eliminator, and resource shrinker using `app/proguard-rules.pro`:
```powershell
.\gradlew.bat assembleRelease
```
*Expected Output:*
- `BUILD SUCCESSFUL`
- Output artifact created at: `app\build\outputs\apk\release\app-release.apk` (or `app-release-unsigned.apk` if signingConfig is omitted)

#### Step 10: Automated APK Size Gate Check
PowerShell one-liner to strictly verify that release APK size is well under the 5 MB (5,242,880 bytes) ceiling:
```powershell
powershell -Command "
    $apk = Get-ChildItem -Path 'app\build\outputs\apk\release' -Filter '*.apk' | Select-Object -First 1;
    if (-not $apk) { Write-Error 'Release APK not found!'; exit 1 }
    $sizeBytes = $apk.Length;
    $sizeMB = [math]::Round($sizeBytes / 1MB, 2);
    Write-Host ('[APK SIZE GATE] File: ' + $apk.Name + ' | Size: ' + $sizeBytes + ' bytes (' + $sizeMB + ' MB)');
    if ($sizeBytes -gt 5242880) {
        Write-Error ('FAILURE: APK size ' + $sizeMB + ' MB exceeds 5 MB limit!');
        exit 1;
    } else {
        Write-Host ('SUCCESS: Release APK is ' + $sizeMB + ' MB (within 5 MB ceiling).');
        exit 0;
    }
"
```

---

## 5. Diagnostic Guide: Common Failure Modes & Mitigations

| Error Scenario | Root Cause | Exact Error Message | Verified Mitigation |
|---|---|---|---|
| **Missing Android 12 `android:exported`** | An activity with `<intent-filter>` does not specify `android:exported`. | `Apps targeting Android 12 and higher are required to specify an explicit value for android:exported` | Add `android:exported="true"` to `<activity android:name=".MainActivity">` in `AndroidManifest.xml`. |
| **AAPT2 Missing String/Theme Resource** | `AndroidManifest.xml` references `@string/app_name` or `@style/Theme.Game2048` before `strings.xml` or `themes.xml` exist. | `AAPT: error: resource string/app_name not found.` | Create stub resource files in `app/src/main/res/values/` before running assemble. |
| **Incompatible Base Theme with AppCompat** | Theme inherits from `Theme.MaterialComponents` but Material library is rejected. | `java.lang.IllegalArgumentException: You need to use a Theme.AppCompat theme (or descendant) with this activity.` | Ensure theme inherits from `Theme.AppCompat.DayNight.NoActionBar`. |
| **R8 NoSuchMethodException on View Inflation** | Custom View constructors stripped by R8 during release shrinking. | `android.view.InflateException: Binary XML file line #... Error inflating class com.game2048.android.ui.GameBoardView` | Add `-keep public class com.game2048.android.ui.GameBoardView { public <init>(...); }` to `proguard-rules.pro`. |
| **R8 Missing Classes Warning** | R8 reports missing optional references from third-party libraries. | `R8: Missing class ...` | Add `-dontwarn <package>.**` for unneeded library references in `proguard-rules.pro`. |
| **JDK 21 Mismatch on CLI** | System `JAVA_HOME` points to Java 8 or Java 11 instead of JDK 21. | `Unsupported class file major version` or Gradle JVM crash. | `gradle.properties` sets `org.gradle.java.home=C:/Program Files/Eclipse Adoptium/jdk-21.0.6.7-hotspot`. |

---

## 6. Implementation Checklist for Worker Agent (`worker_m1`)

When executing Milestone 1 scaffolding, `worker_m1` must create:

1. [ ] `android_2048_game/app/src/main/AndroidManifest.xml` with content from Section 2.1.
2. [ ] `android_2048_game/app/proguard-rules.pro` with content from Section 3.1.
3. [ ] Minimal resource stubs in `android_2048_game/app/src/main/res/`:
   - `values/strings.xml` (`app_name = "2048"`)
   - `values/themes.xml` (`Theme.Game2048` inheriting from `Theme.AppCompat.DayNight.NoActionBar`)
   - `values/colors.xml`
   - `mipmap-anydpi-v26/ic_launcher.xml` and `ic_launcher_round.xml`
   - `drawable/ic_launcher_foreground.xml`
4. [ ] Minimal Activity stub: `android_2048_game/app/src/main/java/com/game2048/android/MainActivity.kt`
5. [ ] Execute Verification Steps S1 through S10 from Section 4 to validate the clean project build.
