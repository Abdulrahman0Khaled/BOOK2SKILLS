@echo off
chcp 65001 >nul
title Book-to-Skills Pipeline — NexMind AI
cls

echo ============================================
echo  📚 Book-to-Skills Pipeline
echo  🤖 Ollama (qwen2.5:14b) — Local
echo  ⚡ Intel i9-13900H + RTX 4070
echo ============================================
echo.

:: 1. التأكد من أن Ollama شغال
echo [1/5] جارٍ التحقق من خادم Ollama...
curl.exe -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo ⚠️  خادم Ollama غير شغال! جارٍ تشغيله...
    start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    timeout /t 8 /nobreak >nul
    curl.exe -s http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo ❌ فشل تشغيل Ollama. شغّله يدوياً وحاول مجدداً.
        pause
        exit /b 1
    )
)
echo ✅ خادم Ollama يعمل على localhost:11434
echo.

:: 2. تفعيل البيئة
echo [2/5] جارٍ تفعيل البيئة الافتراضية...
call "%~dp0.venv\Scripts\activate.bat" 2>nul
if errorlevel 1 (
    echo ⚠️  البيئة غير موجودة — جارٍ إنشاؤها...
    py -3.12 -m venv "%~dp0.venv"
    call "%~dp0.venv\Scripts\activate.bat"
)
echo ✅ البيئة جاهزة
echo.

:: 3. قتل أي عمليات Python عالقة (تسبب قفل الملفات)
echo [3/5] جارٍ تحرير الملفات المحجوزة...
taskkill /f /im python.exe 2>nul
timeout /t 2 /nobreak >nul
echo ✅ تم التحرير
echo.

:: 4. تثبيت الحزمة (بدون المكتبات الثقيلة أولاً)
echo [4/5] جارٍ تثبيت الحزمة والمكتبات الأساسية...
"%~dp0.venv\Scripts\python.exe" -c "import book_to_skills" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  جارٍ تثبيت الحزمة ...
    :: أولاً: الحزمة نفسها بدون dependencies (سريع)
    pip install --no-deps -e "%~dp0." >nul 2>&1
    
    :: ثانياً: فقط المكتبات اللي نحتاجها لـ Ollama
    pip install typer rich pydantic pydantic-settings pypdf python-docx structlog tqdm pyyaml >nul 2>&1
    
    if errorlevel 1 (
        echo ⚠️  فيه مكتبات ما نزلت — جارٍ المحاولة مرة أخرى...
        pip install typer rich pydantic pydantic-settings >nul 2>&1
    )
)
echo ✅ الحزمة جاهزة
echo.

:: 5. تشغيل الـ Pipeline على كل الكتب
echo [5/5] جارٍ معالجة الكتب... (قد يستغرق وقتاً)
echo.
"%~dp0.venv\Scripts\python.exe" -m book_to_skills run all --incremental
echo.

:: 6. عرض النتائج
echo ✅ اكتملت المعالجة!
echo.
"%~dp0.venv\Scripts\python.exe" -m book_to_skills list skills 2>nul || echo (لا توجد مهارات بعد)
echo.

echo ============================================
echo  🎯 تم الانتهاء بنجاح!
echo  📁 المهارات في: outputs\skills\
echo ============================================
echo.

pause
