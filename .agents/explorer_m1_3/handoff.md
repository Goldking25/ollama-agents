# Handoff Report: Manifest, ProGuard & Build Validation Specification

**Author:** explorer_m1_3 (Manifest, Proguard & Build Validation Explorer)  
**Milestone:** M1 — Project Scaffolding & Build Toolchain  
**Target:** `android_2048_game`  
**Recipient:** parent / `worker_m1`  
**Date:** 2026-09-26  

---

## 1. Observation

1. **Gradle and JDK Toolchain Verification**:
   - Executed `cd "C:\Users\manig\AndroidStudioProjects\MeasureAR"; .\gradlew.bat -v`
   - Tool result:
     ```
     Gradle 8.10.2
     Build time: 2024-09-23 21:28:39 UTC
     Launcher JVM: 21.0.6 (Eclipse Adoptium 21.0.6+7-LTS)
     Daemon JVM: C:\Program Files\Eclipse Adoptium\jdk-21.0.6.7-hotspot
     OS: Windows 11 10.0 amd64
     Exit Code: 0
     ```
   - Executed `.\gradlew.bat help`: Exited with code 0 in 51s, successfully starting and warming the Gradle 8.10.2 daemon.

2. **Target Android Versions & Hardware Acceleration Requirements**:
   - `ORIGINAL_REQUEST.md` (lines 5, 19, 34): Compatibility span is Android 15 down to Android 12 (`minSdkVersion` 31, `targetSdkVersion` 35, `compileSdk` 35). Release APK must be strictly under 5 MB.
   - `PROJECT.md` (line 7): "Single Activity (`MainActivity`) + High-performance 2D Canvas Custom View (`GameBoardView`) with hardware acceleration and zero allocation in `onDraw()`."
   - `PROJECT.md` (line 124–126): Standard layout specifies `app/src/main/AndroidManifest.xml` and package `com.game2048.android`.

3. **Peer Explorer Decision Alignment**:
   - `explorer_m1_2` (`.agents/explorer_m1_2/app_gradle_plan.md`, lines 36, 91–101): Configured `namespace = "com.game2048.android"`, `minSdk = 31`, `targetSdk = 35`, dependencies limited to `androidx.core:core-ktx:1.15.0` and `androidx.appcompat:appcompat:1.7.0`. Explicitly rejected Jetpack Compose and Google Material Components to prevent 3.5–7 MB APK bloat.
   - Host reference manifest `C:\Users\manig\AndroidStudioProjects\MeasureAR\app\src\main\AndroidManifest.xml` confirms AGP 8+ practice: `<manifest>` root omits deprecated `package="..."` attribute and defers entirely to Gradle `namespace`.

4. **Host Environment Survey Findings**:
   - `explorer_survey_1/environment_report.md` (lines 83–88, 122): Android SDK at `C:\Users\manig\AppData\Local\Android\Sdk` has `android-35`, `android-34`, `android-33`, and `android-31` installed. Debug keystore initialized at `C:\Users\manig\.android\debug.keystore`.

---

## 2. Logic Chain

1. **Namespace & Manifest Root**:
   - From Observation 2 and 3, `namespace = "com.game2048.android"` is defined in `app/build.gradle.kts`. Under AGP 8.0+, specifying `package` in `AndroidManifest.xml` produces a deprecation warning or merge conflict.
   - *Inference*: `AndroidManifest.xml` must declare `<manifest xmlns:android="http://schemas.android.com/apk/res/android" xmlns:tools="http://schemas.android.com/tools">` without a `package` attribute, using relative path `.MainActivity` which cleanly expands to `com.game2048.android.MainActivity`.

2. **Mandatory Android 12 `exported` Attribute**:
   - From Observation 2, `minSdkVersion` is 31 (Android 12).
   - In Android 12+, any component with an `<intent-filter>` must explicitly specify `android:exported="true"` or `android:exported="false"`.
   - *Inference*: Because `MainActivity` contains `MAIN` and `LAUNCHER` intent filters, setting `android:exported="true"` is mandatory. Omitting it causes an immediate AAPT2 manifest merger compilation failure.

3. **Hardware Acceleration Requirement**:
   - From Observation 2, smooth 60+ FPS touch responsiveness and zero-allocation Canvas 2D rendering are core acceptance criteria.
   - *Inference*: Declaring `android:hardwareAccelerated="true"` on both `<application>` and `<activity>` guarantees that Android's RenderThread handles all Canvas operations on the GPU, avoiding software rasterization.

4. **Orientation and Window Configuration**:
   - From Observation 2 (`ORIGINAL_REQUEST.md` line 37), the UI must adapt properly across screen orientations.
   - *Inference*: The manifest must not lock `screenOrientation="portrait"`. By keeping orientation unconstrained and setting `android:configChanges="keyboard|keyboardHidden"`, Android can seamlessly switch between `res/layout` (portrait) and `res/layout-land` (landscape) while `GameViewModel` preserves the active board state.

5. **Theme Selection & AppCompat Compatibility**:
   - From Observation 3, `explorer_m1_2` included `androidx.appcompat:appcompat:1.7.0` and excluded Google Material Components.
   - *Inference*: The application theme declared in the manifest (`@style/Theme.Game2048`) must inherit from `Theme.AppCompat.DayNight.NoActionBar`. Referencing a Material theme would throw a fatal `ClassNotFoundException` / `Theme.AppCompat` inflation error at runtime.

6. **R8 Optimization & Shrinking Invariants**:
   - From Observation 2 and 3, release builds enable R8 minification and resource shrinking to keep the APK under 5 MB (target ~1.5 MB).
   - *Inference*: In R8 full mode:
     - Custom view constructors (`GameBoardView`) must be protected with `-keep public class com.game2048.android.ui.GameBoardView { public <init>(...); }` to prevent `InflateException` during layout inflation.
     - Kotlin domain models (`com.game2048.android.core.model.**`) and persistence classes must retain fields and methods to prevent JSON serialization breakdown.
     - Logging statements (`Log.v`, `Log.d`, `Log.i`, `Log.w`) must be stripped via `-assumenosideeffects` to reduce binary size and avoid runtime allocations, while keeping `Log.e` and `Log.wtf` for critical error diagnostics.

7. **Verification Pipeline Determinism**:
   - From Observation 1, the local environment has pre-cached Gradle 8.10.2, JDK 21, and Android SDK platforms 31 and 35.
   - *Inference*: A 10-step verification command pipeline (`--version` -> `help` -> `projects` -> `tasks` -> `dependencies` -> `--dry-run` -> `assembleDebug` -> `test` -> `assembleRelease` -> APK size gate) provides a reproducible validation standard for Worker and Reviewer agents.

---

## 3. Caveats

1. **AAPT2 Missing Resource Dependency**:
   - `AndroidManifest.xml` references `@string/app_name`, `@style/Theme.Game2048`, and `@mipmap/ic_launcher`.
   - If `worker_m1` attempts to run `assembleDebug` without creating minimal stub resources (`strings.xml`, `themes.xml`, `colors.xml`, launcher vector icons, and `MainActivity.kt`), AAPT2 will halt with missing resource linking errors.
   - Section 2.3 of `manifest_and_validation_plan.md` provides all necessary stub resources to prevent this.

2. **On-Device Instrumentation Testing Scope**:
   - Verification Step S8 verifies pure JVM unit tests (`:app:testDebugUnitTest`). Connected on-device tests (`:app:connectedDebugAndroidTest`) are intentionally deferred to Milestones M4 and M5 when UI and animations are implemented.

3. **No Platform Caveats**:
   - No assumptions or caveats regarding toolchain or platform dependencies: Java 21, Android SDK 31/35, and Gradle 8.10.2 are verified present and functional.

---

## 4. Conclusion

1. **`app/src/main/AndroidManifest.xml`** is fully specified:
   - Modern AGP 8.7.2 namespace decoupling (`com.game2048.android`).
   - Zero permissions requested.
   - Application-wide and activity-level `hardwareAccelerated="true"`.
   - `android:exported="true"` for API 31–35 compliance.
   - Edge-to-edge AppCompat theme reference and unconstrained adaptive orientation.

2. **`app/proguard-rules.pro`** is fully specified:
   - R8 full-mode aggressive shrinking and class repackaging.
   - Custom view (`GameBoardView`) layout inflation protection.
   - Domain model and persistence JSON serialization safety.
   - Complete removal of non-fatal logging calls in release builds.

3. **Milestone 1 Verification Command Pipeline** is established:
   - 10-step deterministic execution suite from wrapper sanity to automated PowerShell release APK size gating (< 5 MB).
   - Detailed troubleshooting guide for AAPT2, exported attribute, and JVM errors.

4. The complete technical exploration report is recorded at:
   `e:\Learning\Python\agent_test\.agents\explorer_m1_3\manifest_and_validation_plan.md`.

---

## 5. Verification Method

### Files to Inspect
- Technical report: `e:\Learning\Python\agent_test\.agents\explorer_m1_3\manifest_and_validation_plan.md`
- Handoff report: `e:\Learning\Python\agent_test\.agents\explorer_m1_3\handoff.md`

### Verification Commands (Run in `android_2048_game/` once scaffolded)
```powershell
# 1. Verify Gradle wrapper & JDK 21 daemon
.\gradlew.bat --version

# 2. Verify project structure & module inclusion
.\gradlew.bat help
.\gradlew.bat projects

# 3. Dry-run debug assembly
.\gradlew.bat assembleDebug --dry-run

# 4. Compile debug APK & merge manifest
.\gradlew.bat assembleDebug

# 5. Execute JVM unit tests
.\gradlew.bat test

# 6. Compile release APK with R8 minification & ProGuard shrinking
.\gradlew.bat assembleRelease

# 7. Check release APK size against 5 MB limit
powershell -Command "
    $apk = Get-ChildItem -Path 'app\build\outputs\apk\release' -Filter '*.apk' | Select-Object -First 1;
    if ($apk.Length -gt 5242880) { throw 'APK Exceeded 5MB!' };
    Write-Host ('APK Size: ' + [math]::Round($apk.Length / 1MB, 2) + ' MB (PASS)');
"
```

### Invalidation Conditions
- Changing target or minimum SDK below 31, which alters `android:exported` requirements.
- Introducing Jetpack Compose or Google Material Components, which causes theme inheritance failures and blows the < 5 MB binary size limit.
- Re-adding the deprecated `package="..."` attribute to `<manifest>`, which triggers AGP 8.x deprecation warnings.
- Stripping custom view constructors in R8 rules, which triggers release-mode layout inflation crashes.
