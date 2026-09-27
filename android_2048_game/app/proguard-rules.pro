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
