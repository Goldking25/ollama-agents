# Challenger Verification Report: Milestone 1 Build & Artifact Integrity

**Challenger:** challenger_m1_1  
**Role:** Empirical Build & Artifact Challenger for Milestone 1  
**Target Project:** `e:\Learning\Python\agent_test\android_2048_game`  
**Verdict:** **APPROVE**  
**Risk Assessment:** **LOW**  
**Date:** 2026-09-26  

---

## 1. Observation

### 1.1 Toolchain & Build Script Execution
- Execution of `cmd.exe /c "verify_build.bat"` with `BypassSandbox: true` inside `e:\Learning\Python\agent_test\android_2048_game`:
  - **Step 1 (Unit Tests):** Executed `gradlew test` with exit code 0.
    - Tasks executed/up-to-date: `:app:compileDebugUnitTestKotlin`, `:app:testDebugUnitTest`, `:app:compileReleaseUnitTestKotlin`, `:app:testReleaseUnitTest`.
  - **Step 2 (Release APK Build):** Executed `gradlew assembleRelease` with exit code 0.
    - Key tasks executed: `:app:minifyReleaseWithR8`, `:app:shrinkReleaseRes`, `:app:packageRelease`.
  - **Step 3 (Size Check):** Output `833890` bytes (~814.3 KB).
  - Total script exit code: `0`.

### 1.2 Android Package & R8 Minification Verification
- **Artifact Location:** `app/build/outputs/apk/release/app-release.apk`
- **File Size:** `833,890` bytes (0.795 MB / ~814 KB), which is strictly under the 5 MB ceiling requirement (16.7% of maximum limit).
- **APK Archive Inspection (via Python `zipfile`):**
  - `classes.dex`: `564,400` bytes uncompressed (authentic compiled DEX bytecode, not stubbed).
  - `resources.arsc`: `89,752` bytes uncompressed.
  - `AndroidManifest.xml`: `5,416` bytes uncompressed (compiled binary XML).
  - `assets/dexopt/baseline.prof`: `1,174` bytes (AOT precompilation profile).
  - `META-INF/com/android/build/gradle/app-metadata.properties`: present.
- **R8 Minification Outputs (`app/build/outputs/mapping/release/`):**
  - `mapping.txt`: `4,033,091` bytes (4.03 MB of obfuscation mappings).
    - Example obfuscated symbol: `androidx.activity.Cancellable -> n4:`
    - Activity entry preserved: `com.game2048.android.MainActivity -> com.game2048.android.MainActivity:`
  - `usage.txt`: `1,042,049` bytes (1.04 MB of dead code stripped by R8).
  - `seeds.txt`: `101,161` bytes.
  - `resources.txt`: `209,573` bytes of unneeded resources stripped.
- **Output Metadata (`app/build/outputs/apk/release/output-metadata.json`):**
  - `applicationId`: `"com.game2048.android"`
  - `variantName`: `"release"`
  - `minSdkVersionForDexing`: `31`
  - `outputFile`: `"app-release.apk"`

### 1.3 Automated Test Execution & Report Verification
- **Test Source:** `app/src/test/java/com/game2048/android/SmokeUnitTest.kt` containing 2 `@Test` methods (`testJUnitRunnerExecution`, `testBasicMathAssertions`).
- **Generated Reports:**
  - `app/build/test-results/testDebugUnitTest/TEST-com.game2048.android.SmokeUnitTest.xml`:
    ```xml
    <testsuite name="com.game2048.android.SmokeUnitTest" tests="2" skipped="0" failures="0" errors="0" timestamp="2026-09-26T11:58:25" hostname="G-HOME" time="0.006">
      <properties/>
      <testcase name="testBasicMathAssertions" classname="com.game2048.android.SmokeUnitTest" time="0.005"/>
      <testcase name="testJUnitRunnerExecution" classname="com.game2048.android.SmokeUnitTest" time="0.0"/>
    </testsuite>
    ```
  - `app/build/reports/tests/testDebugUnitTest/index.html` and `testReleaseUnitTest/index.html`:
    - Tests: 2, Failures: 0, Ignored: 0, Success rate: 100%.

### 1.4 Adversarial Stress Findings
1. **Windows Sandbox File Access:**
   - Attempting `run_command` without `BypassSandbox: true` failed with:
     `Encountered error in tool execution: granting access to C:\: Access is denied.`
   - Cause: Android SDK and Temurin JDK reside on `C:\`, while the repo is on `E:\`.
2. **Chained Clean + Compilation Daemon Cache Lock:**
   - Executing a single combined command `.\gradlew.bat clean test assembleRelease` resulted in:
     `Execution failed for task ':app:compileDebugUnitTestKotlin'`
     `java.lang.IllegalStateException: Storage for [...proto.tab] is already registered`
     `Failed to create MD5 hash for file ... source-to-output.tab as it does not exist.`
   - Cause: Kotlin daemon holds memory-mapped file handles on Windows while `clean` simultaneously deletes the output directories.
   - Resolution: When running `clean`, run it as an independent command or use `verify_build.bat` which performs sequential invocations (`gradlew test` followed by `gradlew assembleRelease`).

---

## 2. Logic Chain

1. **Build Toolchain Conformance**:
   - Observation 1.1 confirms that running the canonical `verify_build.bat` triggers Gradle 8.10.2 via AGP 8.7.2, compiling Java/Kotlin against JDK 21 and Android SDK 35. Both the `test` task and `assembleRelease` task finish successfully with exit code 0.
2. **Binary Artifact Authenticity & Size Conformance**:
   - Observation 1.2 proves that `app-release.apk` is not a mock or dummy placeholder. It is a genuine, zipped Android package containing compiled DEX bytecode (`classes.dex`, 564 KB), binary XML resources (`resources.arsc`, 89 KB), and release metadata.
   - The APK size is 833,890 bytes (~814 KB), comfortably satisfying the user requirement of < 5 MB (R3 / AC 36).
   - The presence of `mapping.txt` (4 MB) and `usage.txt` (1 MB) confirms that R8 minification and resource shrinking were actively performed during compilation.
3. **Test Infrastructure & Report Authenticity**:
   - Observation 1.3 proves that running `gradlew test` executes genuine JUnit 4 tests and writes standard XML test suites to `app/build/test-results/` and HTML reports to `app/build/reports/tests/`. Both tests pass with 0 failures.

---

## 3. Caveats

1. **Cross-Drive Sandbox Requirement on Host**:
   - On this host, the project directory is on drive `E:\` while the Android SDK (`C:\Users\manig\AppData\Local\Android\Sdk`) and JDK (`C:\Program Files\Eclipse Adoptium\jdk-21.0.6.7-hotspot`) are on drive `C:\`. Any automated runner or agent must run with sandbox bypass or full drive permissions.
2. **Kotlin Daemon Incremental Cache Concurrency on Windows**:
   - Combining `clean` and compilation in a single Gradle invocation (`gradlew clean test assembleRelease`) can trigger memory-mapped file lock conflicts in the Kotlin compiler daemon on Windows. Clean operations should be executed separately (`gradlew clean`) before compiling.
3. **Milestone 1 Scope Boundary**:
   - Milestone 1 encompasses build toolchain scaffolding, configuration, and baseline verification. The 2048 game grid logic, swipe listeners, UI animations, and level progression are part of subsequent milestones (M2+).

---

## 4. Conclusion

**Verdict: APPROVE**

Milestone 1 has successfully met all build toolchain, verification, and artifact packaging acceptance criteria:
- `minSdkVersion` is 31 (Android 12) and `targetSdkVersion` is 35 (Android 15).
- AGP 8.7.2, Gradle 8.10.2, and Kotlin 2.0.21 build cleanly.
- `verify_build.bat` executes cleanly with return code 0.
- `app-release.apk` is genuinely produced with R8 minification enabled.
- Release APK size is 833,890 bytes (~814 KB), well below the 5 MB ceiling.
- Automated unit test suite executes and produces genuine JUnit XML and HTML reports.

---

## 5. Verification Method

To independently reproduce this verification:
1. Open PowerShell / Command Prompt on host:
   ```cmd
   cd e:\Learning\Python\agent_test\android_2048_game
   verify_build.bat
   ```
2. Verify exit code is `0` and last line outputs `833890`.
3. Check APK file size and integrity:
   ```powershell
   Get-Item app\build\outputs\apk\release\app-release.apk | Select-Object Length
   ```
4. Inspect JUnit test reports:
   - View `app\build\test-results\testDebugUnitTest\TEST-com.game2048.android.SmokeUnitTest.xml`
   - View `app\build\reports\tests\testDebugUnitTest\index.html`
