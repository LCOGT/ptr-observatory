curl -O https://repo.anaconda.com/archive/Anaconda3-2023.03-1-Windows-x86_64.exe
Anaconda3-2023.03-1-Windows-x86_64.exe /AddToPath=1 /RegisterPython=1 /S /D=%UserProfile%\Anaconda3
timeout 300
del Anaconda3-2023.03-1-Windows-x86_64.exe