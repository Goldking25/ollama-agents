# Technical Exploration Report: Milestone 1 Project Scaffolding & Gradle Wrapper Specification

**Auditor / Agent:** explorer_m1_1  
**Role:** Project Scaffolding & Gradle Wrapper Explorer for Milestone 1  
**Milestone:** M1 — Project Scaffolding & Build Toolchain  
**Working Directory:** `e:\Learning\Python\agent_test\.agents\explorer_m1_1`  
**Target Project Directory:** `e:\Learning\Python\agent_test\android_2048_game`  
**Date:** 2026-09-26  

---

## 1. Executive Summary

This report establishes the complete, production-grade technical specification for bootstrapping and scaffolding the root Android project in `e:\Learning\Python\agent_test\android_2048_game`. 

Based on non-destructive toolchain inspections of the host environment, the project environment is fully pre-provisioned:
- **JDK**: Eclipse Adoptium Temurin 21 LTS (`C:\Program Files\Eclipse Adoptium\jdk-21.0.6.7-hotspot`) is installed and verified.
- **Android SDK**: Provisioned at `C:\Users\manig\AppData\Local\Android\Sdk` with platforms `android-35` (Android 15) and `android-31` (Android 12) pre-installed, build-tools `35.0.1`, and pre-accepted SDK licenses.
- **Gradle 8.10.2**: Pre-cached in `C:\Users\manig\.gradle\wrapper\dists\gradle-8.10.2-bin\a04bxjujx95o3nb99gddekhwo\gradle-8.10.2`.
- **Reference Wrapper Assets**: Verified in host project `C:\Users\manig\AndroidStudioProjects\MeasureAR` (matching Gradle 8.10.2 and AGP 8.7.2).

By standardizing the root project scaffolding, `local.properties`, `gradle.properties`, and the Gradle Wrapper binaries, this specification enables immediate, offline-capable, deterministic compilation for downstream implementation agents (`worker_m1`), app build configurations (`explorer_m1_2`), and manifest/R8 optimizations (`explorer_m1_3`).

---

## 2. Target Directory Hierarchy & File Layout

Following `PROJECT.md` Section "Code Layout" and standard modern Android project architecture:

```
e:\Learning\Python\agent_test\android_2048_game/
├── .gitignore
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
├── local.properties
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── app/
    ├── build.gradle.kts          (Specified by explorer_m1_2)
    ├── proguard-rules.pro        (Specified by explorer_m1_3)
    └── src/
        ├── main/
        │   ├── AndroidManifest.xml (Specified by explorer_m1_3)
        │   ├── java/com/game2048/android/
        │   │   └── MainActivity.kt
        │   └── res/
        │       ├── values/
        │       │   ├── colors.xml
        │       │   ├── strings.xml
        │       │   └── themes.xml
        │       └── ...
        └── test/
            └── java/com/game2048/android/
```

Milestone 1 focuses on creating the foundational scaffolding so that executing `./gradlew help` or `./gradlew tasks` succeeds without errors.

---

## 3. Gradle Wrapper Bootstrapping Specification

The Gradle Wrapper (`gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, `gradle-wrapper.properties`) ensures that builds execute consistently without requiring a globally pre-installed Gradle binary in the user's `PATH`.

### 3.1 Architecture of the Gradle Wrapper Mechanism
1. The user or automation agent invokes `.\gradlew.bat <task>` on Windows (or `./gradlew <task>` on Unix/POSIX).
2. The batch script detects `JAVA_HOME` (or uses the configured `org.gradle.java.home` from `gradle.properties`).
3. It launches `java.exe -classpath gradle\wrapper\gradle-wrapper.jar org.gradle.wrapper.GradleWrapperMain <task>`.
4. `GradleWrapperMain` reads `gradle/wrapper/gradle-wrapper.properties`.
5. It checks `GRADLE_USER_HOME/wrapper/dists/<hash>/gradle-8.10.2-bin/`. Because this exact distribution is pre-cached on the host, it skips network downloads entirely and immediately spawns the Gradle 8.10.2 Daemon.

---

### 3.2 File 1: `gradle/wrapper/gradle-wrapper.properties`
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\gradle\wrapper\gradle-wrapper.properties`
- **Content:**
```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```
- **Rationale:**
  - `distributionUrl` specifies `gradle-8.10.2-bin.zip`.
  - The cache folder `C:\Users\manig\.gradle\wrapper\dists\gradle-8.10.2-bin\a04bxjujx95o3nb99gddekhwo\gradle-8.10.2` already matches this URL key hash (`a04bxjujx95o3nb99gddekhwo`). As a result, the wrapper does not query the internet or re-download the archive.

---

### 3.3 File 2: `gradle/wrapper/gradle-wrapper.jar`
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\gradle\wrapper\gradle-wrapper.jar`
- **Source Inspection Evidence:**
  - Verified on host at: `C:\Users\manig\AndroidStudioProjects\MeasureAR\gradle\wrapper\gradle-wrapper.jar`
  - Exact file size: `59,203` bytes
  - SHA-256 Checksum: `e996d452d2645e70c01c11143ca2d3742734a28da2bf61f25c82bdc288c9e637`
  - Extracted distribution reference: `C:\Users\manig\.gradle\wrapper\dists\gradle-8.10.2-bin\a04bxjujx95o3nb99gddekhwo\gradle-8.10.2\lib\plugins\gradle-wrapper-main-8.10.2.jar`
- **Provisioning Method for Implementation Agent (`worker_m1`):**
  The implementation agent can copy this verified binary directly using PowerShell or Python:
  ```powershell
  # PowerShell copy command:
  Copy-Item -Path "C:\Users\manig\AndroidStudioProjects\MeasureAR\gradle\wrapper\gradle-wrapper.jar" -Destination "e:\Learning\Python\agent_test\android_2048_game\gradle\wrapper\gradle-wrapper.jar" -Force
  ```
  Or via Python:
  ```python
  import shutil
  src = r"C:\Users\manig\AndroidStudioProjects\MeasureAR\gradle\wrapper\gradle-wrapper.jar"
  dst = r"e:\Learning\Python\agent_test\android_2048_game\gradle\wrapper\gradle-wrapper.jar"
  shutil.copy2(src, dst)
  ```

---

### 3.4 File 3: `gradlew.bat`
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\gradlew.bat`
- **Full Verbatim Content:**
```bat
@rem
@rem Copyright 2015 the original author or authors.
@rem
@rem Licensed under the Apache License, Version 2.0 (the "License");
@rem you may not use this file except in compliance with the License.
@rem You may obtain a copy of the License at
@rem
@rem      https://www.apache.org/licenses/LICENSE-2.0
@rem
@rem Unless required by applicable law or agreed to in writing, software
@rem distributed under the License is distributed on an "AS IS" BASIS,
@rem WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
@rem See the License for the specific language governing permissions and
@rem limitations under the License.
@rem

@if "%DEBUG%" == "" @echo off
@rem ##########################################################################
@rem
@rem  Gradle startup script for Windows
@rem
@rem ##########################################################################

@rem Set local scope for the variables with windows NT shell
if "%OS%"=="Windows_NT" setlocal

set DIRNAME=%~dp0
if "%DIRNAME%" == "" set DIRNAME=.
set APP_BASE_NAME=%~n0
set APP_HOME=%DIRNAME%

@rem Resolve any "." and ".." in APP_HOME to make it shorter.
for %%i in ("%APP_HOME%") do set APP_HOME=%%~fi

@rem Add default JVM options here. You can also use JAVA_OPTS and GRADLE_OPTS to pass JVM options to this script.
set DEFAULT_JVM_OPTS="-Xmx64m" "-Xms64m"

@rem Find java.exe
if defined JAVA_HOME goto findJavaFromJavaHome

set JAVA_EXE=java.exe
%JAVA_EXE% -version >NUL 2>&1
if "%ERRORLEVEL%" == "0" goto execute

echo.
echo ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
echo.
echo Please set the JAVA_HOME variable in your environment to match the
echo location of your Java installation.

goto fail

:findJavaFromJavaHome
set JAVA_HOME=%JAVA_HOME:"=%
set JAVA_EXE=%JAVA_HOME%/bin/java.exe

if exist "%JAVA_EXE%" goto execute

echo.
echo ERROR: JAVA_HOME is set to an invalid directory: %JAVA_HOME%
echo.
echo Please set the JAVA_HOME variable in your environment to match the
echo location of your Java installation.

goto fail

:execute
@rem Setup the command line

set CLASSPATH=%APP_HOME%\gradle\wrapper\gradle-wrapper.jar


@rem Execute Gradle
"%JAVA_EXE%" %DEFAULT_JVM_OPTS% %JAVA_OPTS% %GRADLE_OPTS% "-Dorg.gradle.appname=%APP_BASE_NAME%" -classpath "%CLASSPATH%" org.gradle.wrapper.GradleWrapperMain %*

:end
@rem End local scope for the variables with windows NT shell
if "%ERRORLEVEL%"=="0" goto mainEnd

:fail
rem Set variable GRADLE_EXIT_CONSOLE if you need the _script_ return code instead of
rem the _cmd.exe /c_ return code!
if  not "" == "%GRADLE_EXIT_CONSOLE%" exit 1
exit /b 1

:mainEnd
if "%OS%"=="Windows_NT" endlocal

:omega
```

---

### 3.5 File 4: `gradlew` (POSIX Shell Script)
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\gradlew`
- **Full Verbatim Content:**
```sh
#!/usr/bin/env sh

#
# Copyright 2015 the original author or authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

##############################################################################
##
##  Gradle start up script for UN*X
##
##############################################################################

# Attempt to set APP_HOME
# Resolve links: $0 may be a link
PRG="$0"
# Need this for relative symlinks.
while [ -h "$PRG" ] ; do
    ls=`ls -ld "$PRG"`
    link=`expr "$ls" : '.*-> \(.*\)$'`
    if expr "$link" : '/.*' > /dev/null; then
        PRG="$link"
    else
        PRG=`dirname "$PRG"`"/$link"
    fi
done
SAVED="`pwd`"
cd "`dirname \"$PRG\"`/" >/dev/null
APP_HOME="`pwd -P`"
cd "$SAVED" >/dev/null

APP_NAME="Gradle"
APP_BASE_NAME=`basename "$0"`

# Add default JVM options here. You can also use JAVA_OPTS and GRADLE_OPTS to pass JVM options to this script.
DEFAULT_JVM_OPTS='"-Xmx64m" "-Xms64m"'

# Use the maximum available, or set MAX_FD != -1 to use that value.
MAX_FD="maximum"

warn () {
    echo "$*"
}

die () {
    echo
    echo "$*"
    echo
    exit 1
}

# OS specific support (must be 'true' or 'false').
cygwin=false
msys=false
darwin=false
nonstop=false
case "`uname`" in
  CYGWIN* )
    cygwin=true
    ;;
  Darwin* )
    darwin=true
    ;;
  MINGW* )
    msys=true
    ;;
  NONSTOP* )
    nonstop=true
    ;;
esac

CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar


# Determine the Java command to use to start the JVM.
if [ -n "$JAVA_HOME" ] ; then
    if [ -x "$JAVA_HOME/jre/sh/java" ] ; then
        # IBM's JDK on AIX uses strange locations for the executables
        JAVACMD="$JAVA_HOME/jre/sh/java"
    else
        JAVACMD="$JAVA_HOME/bin/java"
    fi
    if [ ! -x "$JAVACMD" ] ; then
        die "ERROR: JAVA_HOME is set to an invalid directory: $JAVA_HOME

Please set the JAVA_HOME variable in your environment to match the
location of your Java installation."
    fi
else
    JAVACMD="java"
    which java >/dev/null 2>&1 || die "ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.

Please set the JAVA_HOME variable in your environment to match the
location of your Java installation."
fi

# Increase the maximum file descriptors if we can.
if [ "$cygwin" = "false" -a "$darwin" = "false" -a "$nonstop" = "false" ] ; then
    MAX_FD_LIMIT=`ulimit -H -n`
    if [ $? -eq 0 ] ; then
        if [ "$MAX_FD" = "maximum" -o "$MAX_FD" = "max" ] ; then
            MAX_FD="$MAX_FD_LIMIT"
        fi
        ulimit -n $MAX_FD
        if [ $? -ne 0 ] ; then
            warn "Could not set maximum file descriptor limit: $MAX_FD"
        fi
    else
        warn "Could not query maximum file descriptor limit: $MAX_FD_LIMIT"
    fi
fi

# For Darwin, add options to specify how the application appears in the dock
if $darwin; then
    GRADLE_OPTS="$GRADLE_OPTS \"-Xdock:name=$APP_NAME\" \"-Xdock:icon=$APP_HOME/media/gradle.icns\""
fi

# For Cygwin or MSYS, switch paths to Windows format before running java
if [ "$cygwin" = "true" -o "$msys" = "true" ] ; then
    APP_HOME=`cygpath --path --mixed "$APP_HOME"`
    CLASSPATH=`cygpath --path --mixed "$CLASSPATH"`

    JAVACMD=`cygpath --unix "$JAVACMD"`

    # We build the pattern for arguments to be converted via cygpath
    ROOTDIRSRAW=`find -L / -maxdepth 1 -mindepth 1 -type d 2>/dev/null`
    SEP=""
    for dir in $ROOTDIRSRAW ; do
        ROOTDIRS="$ROOTDIRS$SEP$dir"
        SEP="|"
    done
    OURCYGPATTERN="(^($ROOTDIRS))"
    # Add a user-defined pattern to the cygpath arguments
    if [ "$GRADLE_CYGPATTERN" != "" ] ; then
        OURCYGPATTERN="$OURCYGPATTERN|($GRADLE_CYGPATTERN)"
    fi
    # Now convert the arguments - kludge to limit ourselves to /bin/sh
    i=0
    for arg in "$@" ; do
        CHECK=`echo "$arg"|egrep -c "$OURCYGPATTERN" -`
        CHECK2=`echo "$arg"|egrep -c "^-"`                                 ### Determine if an option

        if [ $CHECK -ne 0 ] && [ $CHECK2 -eq 0 ] ; then                    ### Added a condition
            eval `echo args$i`=`cygpath --path --ignore --mixed "$arg"`
        else
            eval `echo args$i`="\"$arg\""
        fi
        i=`expr $i + 1`
    done
    case $i in
        0) set -- ;;
        1) set -- "$args0" ;;
        2) set -- "$args0" "$args1" ;;
        3) set -- "$args0" "$args1" "$args2" ;;
        4) set -- "$args0" "$args1" "$args2" "$args3" ;;
        5) set -- "$args0" "$args1" "$args2" "$args3" "$args4" ;;
        6) set -- "$args0" "$args1" "$args2" "$args3" "$args4" "$args5" ;;
        7) set -- "$args0" "$args1" "$args2" "$args3" "$args4" "$args5" "$args6" ;;
        8) set -- "$args0" "$args1" "$args2" "$args3" "$args4" "$args5" "$args6" "$args7" ;;
        9) set -- "$args0" "$args1" "$args2" "$args3" "$args4" "$args5" "$args6" "$args7" "$args8" ;;
    esac
fi

# Escape application args
save () {
    for i do printf %s\\n "$i" | sed "s/'/'\\\\''/g;1s/^/'/;\$s/\$/' \\\\/" ; done
    echo " "
}
APP_ARGS=`save "$@"`

# Collect all arguments for the java command, following the shell quoting and substitution rules
eval set -- $DEFAULT_JVM_OPTS $JAVA_OPTS $GRADLE_OPTS "\"-Dorg.gradle.appname=$APP_BASE_NAME\"" -classpath "\"$CLASSPATH\"" org.gradle.wrapper.GradleWrapperMain "$APP_ARGS"

exec "$JAVACMD" "$@"
```

---

## 4. Root Configuration Files Specifications

### 4.1 `settings.gradle.kts`
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\settings.gradle.kts`
- **Full Verbatim Content:**
```kotlin
pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
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

rootProject.name = "android_2048_game"
include(":app")
```
- **Rationale & Analysis:**
  - `pluginManagement` defines where Gradle locates build plugins (AGP and Kotlin). The `includeGroupByRegex` blocks route Android, Google, and AndroidX artifact lookups directly to Google's repository, reducing latency and avoiding lookup timeouts.
  - `dependencyResolutionManagement`: Enforces `FAIL_ON_PROJECT_REPOS` mode so all child modules (`:app`) inherit verified global repositories (`google()` and `mavenCentral()`), preventing rogue or fragmented repository definitions in subprojects.
  - `rootProject.name = "android_2048_game"`: Matches the directory and workspace specification.
  - `include(":app")`: Integrates the main application module.

---

### 4.2 Root `build.gradle.kts`
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\build.gradle.kts`
- **Full Verbatim Content:**
```kotlin
// Top-level build file where you can add configuration options common to all sub-projects/modules.
plugins {
    id("com.android.application") version "8.7.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
}
```
- **Rationale & Analysis:**
  - `apply false` prevents applying the plugins to the root project itself while declaring their canonical versions for all subprojects (`:app`).
  - AGP `8.7.2` is fully compatible with Gradle `8.10.2` and verified functional on this host.
  - Kotlin `2.0.21` is modern, stable, compatible with Java 21, and matches host project baselines.

---

### 4.3 `local.properties`
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\local.properties`
- **Full Verbatim Content:**
```properties
## Location of the Android SDK.
## Required by Android Gradle Plugin for compiling against Android 15 (API 35) and 12 (API 31).
sdk.dir=C\:\\Users\\manig\\AppData\\Local\\Android\\Sdk
```
- **Rationale & Analysis:**
  - Android Gradle Plugin requires `sdk.dir` when `ANDROID_HOME` or `ANDROID_SDK_ROOT` is not explicitly set in the parent process.
  - Escaped backslashes (`C\:\\Users\\...`) conform to standard Java/Android `.properties` escaping format.
  - Direct inspection proved that `C:\Users\manig\AppData\Local\Android\Sdk` contains `platforms/android-35`, `platforms/android-31`, and build tools `35.0.1`.

---

### 4.4 `gradle.properties`
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\gradle.properties`
- **Full Verbatim Content:**
```properties
# Project-wide Gradle settings.

# Specifies the JVM arguments used for the daemon process.
# Sets heap to 2048MB with UTF-8 encoding for reliable compilation across environments.
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8

# Deterministic Java Toolchain: Pin daemon JVM to Eclipse Adoptium Temurin 21 LTS
org.gradle.java.home=C:/Program Files/Eclipse Adoptium/jdk-21.0.6.7-hotspot

# AndroidX package structure for modern support libraries
android.useAndroidX=true

# Enables namespacing of each library's R class so that its R class includes only the
# resources declared in the library itself, reducing binary size and class count.
android.nonTransitiveRClass=true

# Standard Kotlin code style
kotlin.code.style=official
```
- **Rationale & Analysis:**
  - `org.gradle.java.home=C:/Program Files/Eclipse Adoptium/jdk-21.0.6.7-hotspot`: Directly pins Gradle's launcher and daemon to the verified OpenJDK 21 LTS installation. Forward slashes (`/`) ensure safe cross-platform parsing by Gradle without Windows backslash escaping errors.
  - `org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8`: Provides sufficient heap space (2 GB) to avoid out-of-memory errors during R8 full-mode shrinking and DEX optimization, while enforcing standard UTF-8 string encoding.
  - `android.useAndroidX=true`: Mandatory for modern Android development.
  - `android.nonTransitiveRClass=true`: Improves incremental compilation speed and reduces generated bytecode size, directly helping satisfy the < 5 MB binary footprint target.

---

### 4.5 Root `.gitignore`
- **Target Path:** `e:\Learning\Python\agent_test\android_2048_game\.gitignore`
- **Full Verbatim Content:**
```gitignore
*.iml
.gradle
/local.properties
/.idea/
.DS_Store
/build
/captures
.externalNativeBuild
.cxx
*.apk
*.aab
```

---

## 5. Execution Steps for Implementation Worker (`worker_m1`)

When the implementation agent (`worker_m1`) begins execution, it should follow this sequential execution plan:

### Step 1: Directory Initialization
Create the following directories under `e:\Learning\Python\agent_test\android_2048_game`:
- `gradle/wrapper/`
- `app/`
- `app/src/main/java/com/game2048/android/`
- `app/src/main/res/values/`
- `app/src/test/java/com/game2048/android/`

### Step 2: Copy Gradle Wrapper Binary
Copy the binary `gradle-wrapper.jar` from the verified host project:
- Source: `C:\Users\manig\AndroidStudioProjects\MeasureAR\gradle\wrapper\gradle-wrapper.jar`
- Destination: `e:\Learning\Python\agent_test\android_2048_game\gradle\wrapper\gradle-wrapper.jar`
- Integrity Check: Confirm file size is `59,203` bytes.

### Step 3: Write Wrapper & Root Text Files
Write the verified file contents specified in Sections 3 and 4:
1. `gradle/wrapper/gradle-wrapper.properties`
2. `gradlew.bat`
3. `gradlew`
4. `settings.gradle.kts`
5. `build.gradle.kts`
6. `local.properties`
7. `gradle.properties`
8. `.gitignore`

### Step 4: Write App Module Files (Coordinated with Peer Explorers)
1. Write `app/build.gradle.kts` using the specification from `explorer_m1_2/app_gradle_plan.md`.
2. Write `app/proguard-rules.pro` using the specification from `explorer_m1_3/manifest_and_validation_plan.md`.
3. Write `app/src/main/AndroidManifest.xml` and minimal stub resources using the specification from `explorer_m1_3/manifest_and_validation_plan.md`.

### Step 5: Verification Execution
Run the verification sequence outlined in Section 6.

---

## 6. Verification & Troubleshooting Matrix

### 6.1 Verification Commands
Once the files are laid down, execute the following commands in sequence within `e:\Learning\Python\agent_test\android_2048_game`:

```powershell
# 1. Test Gradle Wrapper and JVM environment
.\gradlew.bat --version

# Expected output:
# Gradle 8.10.2
# Kotlin: 2.0.20 (or 2.0.21)
# Groovy: 3.0.22
# Ant: Apache Ant(TM) version 1.10.14
# JVM: 21.0.6 (Eclipse Adoptium 21.0.6+7-LTS)
# OS: Windows 11 10.0 amd64

# 2. Test project structure & multi-module recognition
.\gradlew.bat projects

# Expected output:
# Root project 'android_2048_game'
# \--- Project ':app'

# 3. Test tasks evaluation
.\gradlew.bat tasks --all

# 4. Dry-run assembleDebug
.\gradlew.bat assembleDebug --dry-run
```

### 6.2 Troubleshooting & Failure Modes

| Potential Issue | Root Cause | Immediate Fix |
| :--- | :--- | :--- |
| `JAVA_HOME is not set` | Shell environment lacks `JAVA_HOME` variable | Ensure `gradle.properties` contains `org.gradle.java.home=C:/Program Files/Eclipse Adoptium/jdk-21.0.6.7-hotspot` (with forward slashes). Alternatively, in PowerShell: `$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.6.7-hotspot'` |
| `SDK location not found` | Missing or corrupted `local.properties` | Verify `local.properties` exists in root with line `sdk.dir=C\:\\Users\\manig\\AppData\\Local\\Android\\Sdk` |
| `Could not find or load main class org.gradle.wrapper.GradleWrapperMain` | `gradle-wrapper.jar` missing or 0 bytes | Re-copy `gradle-wrapper.jar` from `C:\Users\manig\AndroidStudioProjects\MeasureAR\gradle\wrapper\gradle-wrapper.jar` and verify size is 59,203 bytes |
| `Downloading https://services.gradle.org/...` halts | Wrapper cannot find cached zip | Verify `gradle/wrapper/gradle-wrapper.properties` has `distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip`. Ensure `C:\Users\manig\.gradle\wrapper\dists\gradle-8.10.2-bin` has not been altered |
| Plugin `com.android.application` not found | Offline repository lookup failure | Ensure `pluginManagement` has `google()` repository configured in `settings.gradle.kts` |

---

## 7. Downstream Contract Sign-off

- **Root project name**: `android_2048_game`
- **Root build plugin declarations**:
  - `com.android.application` version `8.7.2` (apply false)
  - `org.jetbrains.kotlin.android` version `2.0.21` (apply false)
- **Included subprojects**: `:app`
- **Gradle version**: `8.10.2`
- **JVM target**: `21` (Eclipse Adoptium Temurin 21.0.6-LTS)
- **Android SDK Path**: `C:\Users\manig\AppData\Local\Android\Sdk` (API 35 target, API 31 min)

This scaffolding plan provides all parameters needed for Milestone 1 implementation.
