@echo off
echo ============================================================
echo [STEP 0] Mitigating Windows Daemon Locking: gradlew --stop
echo ============================================================
call .\gradlew.bat --stop

echo ============================================================
echo [STEP 1] Running Clean: gradlew clean
echo ============================================================
call .\gradlew.bat clean
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Clean failed with error code %ERRORLEVEL%!
    exit /b %ERRORLEVEL%
)

echo ============================================================
echo [STEP 2] Running Unit Tests: gradlew test
echo ============================================================
call .\gradlew.bat test
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Unit tests failed with error code %ERRORLEVEL%!
    exit /b %ERRORLEVEL%
)

echo ============================================================
echo [STEP 3] Building Release APK: gradlew assembleRelease
echo ============================================================
call .\gradlew.bat assembleRelease
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Assemble release failed with error code %ERRORLEVEL%!
    exit /b %ERRORLEVEL%
)

echo ============================================================
echo [STEP 4] Verifying Release APK Size strictly under 5 MB
echo ============================================================
if not exist "app\build\outputs\apk\release\app-release.apk" (
    echo [ERROR] Release APK not found at app\build\outputs\apk\release\app-release.apk!
    exit /b 1
)
powershell -Command "$apk = Get-Item 'app\build\outputs\apk\release\app-release.apk'; Write-Host ('[INFO] Release APK Size: ' + $apk.Length + ' bytes (' + [math]::Round($apk.Length / 1MB, 3) + ' MB)'); if ($apk.Length -gt 5242880) { Write-Host '[ERROR] APK size exceeds 5 MB limit!' -ForegroundColor Red; exit 1; } else { Write-Host '[SUCCESS] APK size is strictly under 5 MB ceiling.' -ForegroundColor Green; }"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Size verification failed!
    exit /b %ERRORLEVEL%
)
