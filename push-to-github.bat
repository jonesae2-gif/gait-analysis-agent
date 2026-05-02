@echo off
REM ==========================================================================
REM  push-to-github.bat
REM  ------------------
REM  One-shot script to publish this project to a brand-new GitHub repository.
REM
REM  Before running, you must:
REM    1. Have Git for Windows installed   (https://git-scm.com/download/win)
REM    2. Have a GitHub account
REM    3. Create an EMPTY repo on github.com (no README, no .gitignore)
REM       e.g. github.com/YOUR-USERNAME/gait-analysis-agent
REM
REM  Then double-click this file (or run it from a terminal) and follow the
REM  prompts. It will ask for your GitHub username and the repo name, then
REM  init / commit / push everything in one go.
REM ==========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ========================================================
echo   GaitMind  -  publish to GitHub
echo ========================================================
echo.

REM --- 0. Check git is installed -------------------------------------------
where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git is not installed or not on your PATH.
    echo         Install it from https://git-scm.com/download/win and try again.
    pause
    exit /b 1
)

REM --- 1. Remove any stale .git folder (left over from earlier attempts) ---
if exist ".git" (
    echo Found an existing .git folder. Removing it for a clean start...
    rmdir /s /q ".git"
)

REM --- 2. Ask for GitHub details -------------------------------------------
set /p GH_USER=GitHub username [jonesae2-gif]:
if "!GH_USER!"=="" set GH_USER=jonesae2-gif

set /p GH_REPO=Repository name [gait-analysis-agent]:
if "!GH_REPO!"=="" set GH_REPO=gait-analysis-agent

set /p GH_EMAIL=Your GitHub email [jonesae2@vcu.edu]:
if "!GH_EMAIL!"=="" set GH_EMAIL=jonesae2@vcu.edu

set /p GH_NAME=Your name for commits [Anastasia Jones]:
if "!GH_NAME!"=="" set GH_NAME=Anastasia Jones

echo.
echo About to push to: https://github.com/!GH_USER!/!GH_REPO!
set /p CONFIRM=Continue? (y/n):
if /i not "!CONFIRM!"=="y" (
    echo Cancelled.
    pause
    exit /b 0
)

REM --- 3. Init repo, configure user, stage, commit -------------------------
echo.
echo ---- Initializing local git repository ----
git init -b main
if errorlevel 1 goto fail

git config user.email "!GH_EMAIL!"
git config user.name "!GH_NAME!"

echo ---- Staging files ----
git add .

echo ---- Creating initial commit ----
git commit -m "Initial commit: GaitMind cognitive-learning gait-analysis agent"
if errorlevel 1 goto fail

REM --- 4. Add remote and push ---------------------------------------------
echo ---- Adding GitHub remote ----
git remote add origin https://github.com/!GH_USER!/!GH_REPO!.git

echo ---- Pushing to GitHub (force, safe for first push) ----
echo.
echo If this is the first time you've pushed from this machine, a browser
echo window may pop up asking you to sign in to GitHub. That's normal --
echo sign in to authorize Git Credential Manager.
echo.
REM --force is safe here because this is the first publish of this project.
REM It overwrites any auto-generated README/LICENSE on the empty GitHub repo.
git push -u --force origin main
if errorlevel 1 goto fail

echo.
echo ========================================================
echo   SUCCESS!
echo ========================================================
echo.
echo Your project is live at:
echo   https://github.com/!GH_USER!/!GH_REPO!
echo.
pause
exit /b 0

:fail
echo.
echo ========================================================
echo   Something went wrong. Common fixes:
echo ========================================================
echo   * Make sure the GitHub repo exists and is EMPTY
echo     (no README, .gitignore, or LICENSE selected at creation)
echo   * Make sure you typed the username and repo name correctly
echo   * If push was rejected, the repo may already have content --
echo     either delete it on GitHub and try again, or rename this one
echo.
pause
exit /b 1
