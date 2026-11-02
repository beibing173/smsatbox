# SMSATBOX · Android 端构建配置
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**

# 数据模型（JSON 反射友好）
-keep class com.smsatbox.app.data.** { *; }
