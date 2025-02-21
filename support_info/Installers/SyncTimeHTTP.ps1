wsl sudo htpdate -s www.google.com
$wslTime = wsl date +"%Y-%m-%d %H:%M:%S"
Set-Date -Date ([datetime]::ParseExact($wslTime, "yyyy-MM-dd HH:mm:ss", $null))