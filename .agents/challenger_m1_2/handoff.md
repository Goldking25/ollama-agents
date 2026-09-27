# Milestone M1 Empirical Challenge Report: Toolchain & SDK Compatibility

**Agent**: `challenger_m1_2`  
**Role**: Toolchain & SDK Compatibility Challenger for Milestone 1 (critic, specialist)  
**Milestone**: M1 — Project Scaffolding & Build Toolchain  
**Working Directory**: `e:\Learning\Python\agent_test\.agents\challenger_m1_2`  
**Target Project**: `e:\Learning\Python\agent_test\android_2048_game`  
**Date**: 2026-09-26  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Observation

Direct observations and empirical outputs obtained from inspecting configuration files and executing verification commands in `android_2048_game`:

### 1.1 Multi-Version Compatibility & SDK Alignment
In `android_2048_game/app/build.gradle.kts`:
- Line 8: `compileSdk = 35`
- Line 12: `minSdk = 31` (Android 12)
- Line 13: `targetSdk = 35` (Android 15)
- Line 40: `sourceCompatibility = JavaVersion.VERSION_21`
- Line 41: `targetCompatibility = JavaVersion.VERSION_21`
- Line 45: `jvmTarget = "21"`
- Line 20: `resourceConfigurations += listOf("en")`

In merged release manifest (`app/build/intermediates/merged_manifests/release/processReleaseManifest/AndroidManifest.xml`):
```xml
<uses-sdk
    android:minSdkVersion="31"
    android:targetSdkVersion="35" />
...
<activity
    android:name="com.game2048.android.MainActivity"
    android:configChanges="keyboard|keyboardHidden"
    android:exported="true"
    android:hardwareAccelerated="true"
    android:label="@string/app_name"
    android:theme="@style/Theme.Game2048"
    android:windowSoftInputMode="adjustNothing" >
```
- `android:exported="true"` is present (mandatory for Android 12+ / API 31+).
- Hardware acceleration is enabled at both `<application>` and `<activity>` levels.
- Zero permissions requested in manifest.

### 1.2 Gradle Wrapper Inconsistency Defect
In `android_2048_game/gradle/wrapper/gradle-wrapper.properties`:
```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```
Notice that `distributionSha256Sum` is completely missing.

Empirical verification of `android_2048_game/gradle/wrapper/gradle-wrapper.jar`:
- Command:
  ```powershell
  Get-FileHash -Path 'android_2048_game\gradle\wrapper\gradle-wrapper.jar' -Algorithm SHA256
  (Get-Item 'android_2048_game\gradle\wrapper\gradle-wrapper.jar').Length
  ```
- Result:
  - SHA-256: `E996D452D2645E70C01C11143CA2D3742734A28DA2BF61F25C82BDC288C9E637`
  - Byte Size: `59203` bytes

Official Reference for Gradle 8.10.2 / 8.11.x:
- Official Gradle 8.10.2 wrapper JAR SHA-256: `2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046`
- Official Gradle 8.10.2 bin distribution SHA-256: `31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26`
- The hash `E996D452...` corresponds to the legacy wrapper JAR from Gradle 6.9.4 (copied from an older local project `MeasureAR`), not the Gradle 8.10.2 wrapper binary.

### 1.3 R8 ProGuard Configuration & Stripping Safety
In `android_2048_game/app/proguard-rules.pro`:
- Lines 23-29:
  ```proguard
  -keep public class * extends android.app.Activity
  -keep public class * extends android.app.Application
  -keep public class * extends android.app.Service
  -keep public class * extends android.content.BroadcastReceiver
  -keep public class * extends android.content.ContentProvider
  -keep public class * extends android.app.backup.BackupAgentHelper
  -keep public class * extends android.preference.Preference
  ```
- Lines 35-45:
  ```proguard
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
  ```

Empirical verification of R8 outputs in `app/build/outputs/mapping/release/`:
- `seeds.txt` line 46: `com.game2048.android.MainActivity`
- `seeds.txt` line 548: `com.game2048.android.MainActivity: MainActivity()`
- `usage.txt`: 0 matches for `MainActivity` (confirmed unstripped).
- `mapping.txt` line 38475: `com.game2048.android.MainActivity -> com.game2048.android.MainActivity:` with `0:3:void <init>():6:6 -> <init>`.
- `configuration.txt` line 175: Rule `-keep public class com.game2048.android.ui.GameBoardView { ... }` is actively merged into R8 configuration.
- AAPT rules (`app/build/intermediates/aapt_proguard_file/release/.../aapt_rules.txt`) additionally emit:
  `-keep class com.game2048.android.MainActivity { <init>(); }`.

### 1.4 Clean Build Execution & Windows Daemon File Lock
Execution of `cmd /c gradlew.bat clean assembleRelease --warning-mode all`:
- **Run 1 (Daemon active)**:
  ```
  > Task :app:clean FAILED
  FAILURE: Build failed with an exception.
  * What went wrong:
  Execution failed for task ':app:clean'.
  > java.io.IOException: Unable to delete directory 'E:\Learning\Python\agent_test\android_2048_game\app\build'
      Failed to delete some children. This might happen because a process has files open or has its working directory set in the target directory.
      - E:\Learning\Python\agent_test\android_2048_game\app\build\kotlin
  ```
  The Kotlin compiler daemon held open file locks on `lookups.tab` and memory maps in `app\build\kotlin\compileReleaseKotlin\cacheable\caches-jvm\lookups`.
- **Run 2 (After executing `cmd /c gradlew.bat --stop`)**:
  3 daemons stopped.
  `cmd /c gradlew.bat clean assembleRelease --warning-mode all` completed with:
  `BUILD SUCCESSFUL in 1m 7s`
  Actionable tasks: 44 executed, 3 up-to-date.
- Release APK output:
  - Path: `app/build/outputs/apk/release/app-release.apk`
  - Byte size: `833890` bytes (~814 KB)
  - Target ceiling: < 5 MB (Passed: ~16% of maximum allowable footprint).

### 1.5 Deprecation & Dependency Resolution Warnings
In build log `task-85.log` with `--warning-mode all`:
- Deprecation warnings found: `0`
- Dependency resolution errors or warnings found: `0`
- `settings.gradle.kts` uses strict `RepositoriesMode.FAIL_ON_PROJECT_REPOS` with standard `google()` and `mavenCentral()`. No project-level repository overrides exist in `build.gradle.kts` or `app/build.gradle.kts`.

---

## 2. Logic Chain

1. **Multi-Version Compatibility (Observation 1.1)**:
   - `minSdk = 31` guarantees support for Android 12 (API 31), Android 13 (API 33), Android 14 (API 34), and Android 15 (API 35).
   - `compileSdk = 35` and `targetSdk = 35` compile against Android 15 platform libraries.
   - `MainActivity` specifies `android:exported="true"`, satisfying Android 12 security requirements.
   - APK contains zero native C/C++ libraries, ensuring 100% native compatibility with Android 15's 16 KB page size architecture.
   - Multi-version compatibility contract is fully satisfied.

2. **Wrapper Integrity Discrepancy (Observation 1.2)**:
   - `gradle-wrapper.properties` configures Gradle 8.10.2 (`gradle-8.10.2-bin.zip`).
   - However, the binary `gradle/wrapper/gradle-wrapper.jar` has SHA-256 `E996D452D2645E70C01C11143CA2D3742734A28DA2BF61F25C82BDC288C9E637` and size 59,203 bytes, which belongs to Gradle 6.9.4.
   - The official Gradle 8.10.2 wrapper JAR has SHA-256 `2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046`.
   - In CI environments utilizing GitHub Actions (`gradle/actions/wrapper-validation`), this checksum mismatch triggers a security failure and halts the build to prevent supply chain tampering.
   - Furthermore, `distributionSha256Sum` is omitted from `gradle-wrapper.properties`, leaving distribution downloads unverified.

3. **R8 Stripping Safety (Observation 1.3)**:
   - Both AAPT-generated rules and explicit rules in `proguard-rules.pro` preserve `com.game2048.android.MainActivity` and its constructor. R8 `seeds.txt` confirms it is retained, `usage.txt` confirms it is not stripped, and `mapping.txt` confirms its name remains unobfuscated.
   - For `GameBoardView`, `proguard-rules.pro` lines 35-45 explicitly retain:
     - `public <init>(android.content.Context)`
     - `public <init>(android.content.Context, android.util.AttributeSet)`
     - `public <init>(android.content.Context, android.util.AttributeSet, int)`
     both for `com.game2048.android.ui.GameBoardView` specifically and generally for `* extends android.view.View`.
   - Kotlin `@JvmOverloads` constructor generates exactly these three signatures, ensuring XML layout inflation via `LayoutInflater` will not crash with `NoSuchMethodException`.

4. **Clean Build Reliability on Windows (Observation 1.4)**:
   - On Windows, the Kotlin Daemon and Gradle Daemon lock memory-mapped files in `app\build\kotlin\...`.
   - Executing `gradlew clean` while daemons hold file descriptors triggers an unhandled `java.io.IOException` and build failure.
   - The build script `verify_build.bat` runs `gradlew test` followed by `gradlew assembleRelease` without clean, which succeeds, but standalone clean commands fail unless `gradlew --stop` is executed first or daemon caching is controlled.

---

## 3. Caveats

1. The legacy Gradle 6.9.4 wrapper JAR is functionally backward-compatible enough to download and invoke Gradle 8.10.2 on a local workstation, but fails strict checksum validation in enterprise CI pipelines.
2. Runtime performance on physical hardware (e.g., frame rate consistency at 60+ FPS) requires device benchmarking once rendering code is authored in Milestone 2.
3. The build was tested against Eclipse Adoptium JDK 21.0.6 LTS on Windows 11.

---

## 4. Conclusion

The Milestone 1 toolchain scaffolding is largely functional, achieving valid release compilation, full R8 shrinking down to ~814 KB, and complete Android 12-15 SDK alignment. However, changes are requested to resolve wrapper consistency and clean build resilience.

### **Verdict: REQUEST_CHANGES**

### Required Remediation Actions for Worker:
1. **Regenerate / Align `gradle-wrapper.jar` to Gradle 8.10.2**:
   - Update `gradle-wrapper.jar` to the official Gradle 8.10.2 wrapper binary (SHA-256: `2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046`).
   - Add `distributionSha256Sum=31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26` to `gradle/wrapper/gradle-wrapper.properties` to enforce supply chain verification.
   - Or run `./gradlew wrapper --gradle-version 8.10.2 --gradle-distribution-sha256-sum 31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26`.
2. **Mitigate Windows Clean Task File Locking**:
   - In `gradle.properties`, add configuration to prevent file locking issues on Windows (such as ensuring daemon clean lifecycle or documenting `--stop` pre-clean in build documentation/scripts).

---

## 5. Verification Method

To independently verify these findings:

1. **Verify Gradle Wrapper Hash and Byte Size**:
   ```powershell
   Get-FileHash -Path 'e:\Learning\Python\agent_test\android_2048_game\gradle\wrapper\gradle-wrapper.jar' -Algorithm SHA256
   (Get-Item 'e:\Learning\Python\agent_test\android_2048_game\gradle\wrapper\gradle-wrapper.jar').Length
   ```
   - Current output: SHA-256 `E996D452D2645E70C01C11143CA2D3742734A28DA2BF61F25C82BDC288C9E637`, 59203 bytes (legacy 6.9.4).
   - Expected output for 8.10.2: SHA-256 `2DB75C40782F5E8BA1FC278A5574BAB070ADCCB2D21CA5A6E5ED840888448046`.

2. **Verify R8 Preservation of MainActivity and GameBoardView**:
   ```powershell
   cd e:\Learning\Python\agent_test\android_2048_game
   Select-String -Path 'app\build\outputs\mapping\release\seeds.txt' -Pattern 'MainActivity'
   Select-String -Path 'app\build\outputs\mapping\release\usage.txt' -Pattern 'MainActivity'
   Select-String -Path 'app\build\outputs\mapping\release\configuration.txt' -Pattern 'GameBoardView'
   ```
   - Confirm `MainActivity` is in `seeds.txt` and absent from `usage.txt`.
   - Confirm `GameBoardView` keep rules appear in `configuration.txt`.

3. **Verify Reproducibility of Clean Build on Windows**:
   ```cmd
   cd e:\Learning\Python\agent_test\android_2048_game
   .\gradlew.bat test
   .\gradlew.bat clean
   ```
   - Observe `java.io.IOException: Unable to delete directory ... \app\build\kotlin` due to active daemon locking.
   - Run `.\gradlew.bat --stop` followed by `.\gradlew.bat clean assembleRelease` to confirm clean build success.

4. **Invalidation Conditions**:
   - `gradle-wrapper.jar` updated to official 8.10.2 binary matching SHA-256 `2db75c40...`.
   - `distributionSha256Sum` pinned in `gradle-wrapper.properties`.
   - Clean task succeeds deterministically across consecutive runs on Windows host.
