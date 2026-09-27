## 2026-09-26T03:53:43Z
You are survey_architecture.
Your role: Architecture & Technology Spec Miner.
Your working directory: e:\Learning\Python\agent_test\.agents\spec_miner_survey_2
Authoritative user request: e:\Learning\Python\agent_test\ORIGINAL_REQUEST.md

Task:
1. Thoroughly read e:\Learning\Python\agent_test\ORIGINAL_REQUEST.md.
2. Investigate and formalize the Android architecture and technical implementation strategy to fulfill all constraints:
   - Ultra-lean binary footprint (Target release APK < 5 MB): Evaluate View/CustomView with Canvas 2D vs Jetpack Compose vs SurfaceView. Weigh APK overhead of Compose dependencies (~10-20MB unoptimized or 3-5MB heavily stripped) vs pure Kotlin + Custom View (typically < 2MB APK).
   - Compatibility: minSdkVersion <= 31 (Android 12), targetSdkVersion >= 35 (Android 15), compileSdk 35.
   - UI & Animation: Custom View with ValueAnimator / ObjectAnimator / Choreographer or Kotlin coroutines for 60+ FPS rendering, vector drawables, adaptive UI layouts (portrait/landscape, densities hdpi/xhdpi/xxhdpi).
   - State & Persistence: Room vs DataStore vs lightweight SharedPreferences. Formulate lightweight JSON/key-value persistence schema for game state, high score, and level progression.
   - Build Toolchain & Proguard/R8: Code shrinking, resource shrinking, minifyReleaseEnabled = true, ProGuard optimization rules to ensure < 5 MB release APK.
   - Testing strategy: Pure JVM unit tests for game math and level progression state machine (fast, 100% deterministic), Robolectric or mock Android tests for ViewModel/Persistence, and build verification.
3. Write your detailed architecture specification to:
   e:\Learning\Python\agent_test\.agents\spec_miner_survey_2\spec_architecture.md
4. Deliver your handoff report to:
   e:\Learning\Python\agent_test\.agents\spec_miner_survey_2\handoff.md
   and notify the caller via send_message with a brief summary referencing your report path.
