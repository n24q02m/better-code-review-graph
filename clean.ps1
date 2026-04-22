$reposNode = @("better-notion-mcp", "better-email-mcp", "better-godot-mcp")
$reposPython = @("mcp-core", "better-telegram-mcp", "wet-mcp", "mnemo-mcp", "better-code-review-graph")

foreach ($r in $reposNode) {
  cd C:\Users\n24q02m-wlap\projects\$r
  Write-Host "Cleaning $r..."
  Remove-Item -Recurse -Force node_modules, package-lock.json -ErrorAction SilentlyContinue
  npm install
  npm run build
}

foreach ($r in $reposPython) {
  cd C:\Users\n24q02m-wlap\projects\$r
  Write-Host "Cleaning $r..."
  Remove-Item -Recurse -Force .venv, uv.lock -ErrorAction SilentlyContinue
  uv sync
}
