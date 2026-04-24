@echo off
setlocal

set "ROOT=%~dp0"
set "MSYS2_UCRT64=C:\msys64\ucrt64"
set "UCRT_BIN=%MSYS2_UCRT64%\bin"
set "MAKE=%UCRT_BIN%\mingw32-make.exe"
set "GCC=%UCRT_BIN%\gcc.exe"
set "SUPERLU_INC=%MSYS2_UCRT64%\include\superlu"
set "SUPERLU_LIB=%MSYS2_UCRT64%\lib\libsuperlu.dll.a"
set "OPENBLAS_LIB=%MSYS2_UCRT64%\lib\libopenblas.dll.a"

cd /d "%ROOT%" || exit /b 1

if not exist "%GCC%" (
    echo [error] MSYS2 UCRT64 gcc not found: %GCC%
    echo Install MSYS2 UCRT64 gcc first.
    exit /b 1
)

if not exist "%MAKE%" (
    echo [error] MSYS2 UCRT64 make not found: %MAKE%
    echo Install mingw-w64-ucrt-x86_64-make first.
    exit /b 1
)

set "PATH=%UCRT_BIN%;%PATH%"

echo [info] Cleaning previous build...
"%MAKE%" clean
if errorlevel 1 exit /b %errorlevel%

if exist "%SUPERLU_INC%\slu_ddefs.h" if exist "%SUPERLU_LIB%" if exist "%OPENBLAS_LIB%" (
    echo [info] SuperLU and OpenBLAS found. Building with SUPERLU=1...
    "%MAKE%" SUPERLU=1 INCDIR=C:/msys64/ucrt64/include/superlu LIBDIR=C:/msys64/ucrt64/lib BLASLIB="-lopenblas" SUPERLULIB="-lsuperlu"
) else (
    echo [warn] SuperLU/OpenBLAS not fully found. Building without SuperLU.
    echo [warn] example5 requires SuperLU and will not run in this build.
    "%MAKE%"
)

if errorlevel 1 exit /b %errorlevel%

echo [info] Build complete.
echo [info] hotspot.exe and hotfloorplan.exe are ready.
exit /b 0
