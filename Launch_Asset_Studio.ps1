$studioRoot = $PSScriptRoot
$studioBlender = $env:ASSET_STUDIO_BLENDER
$studioLocalConfig = Join-Path $studioRoot 'runtime\development.json'
if (-not $studioBlender -and (Test-Path -LiteralPath $studioLocalConfig)) {
    $studioLocalSettings = Get-Content -LiteralPath $studioLocalConfig -Raw | ConvertFrom-Json
    $studioBlender = $studioLocalSettings.blender
}
if (-not $studioBlender) {
    $studioCommand = Get-Command blender -ErrorAction SilentlyContinue
    if ($studioCommand) { $studioBlender = $studioCommand.Source }
}
if (-not (Test-Path -LiteralPath $studioBlender)) {
    throw 'Set ASSET_STUDIO_BLENDER to Blender 4.2, or install the release ZIP through Blender Preferences.'
}
& $studioBlender --factory-startup --python (Join-Path $studioRoot 'launch_studio.py')
