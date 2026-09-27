@echo off
echo ============================================================
echo Updating Gradle Wrapper to 8.10.2 with SHA256 Checksum
echo ============================================================
call .\gradlew.bat wrapper --gradle-version 8.10.2 --gradle-distribution-sha256-sum 31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Gradle wrapper update failed with error code %ERRORLEVEL%!
    exit /b %ERRORLEVEL%
)
echo [SUCCESS] Gradle wrapper updated successfully.
