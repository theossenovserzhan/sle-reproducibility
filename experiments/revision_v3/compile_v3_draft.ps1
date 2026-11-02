param([string]$RenderSubfolder = 'draft_qa')
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = 'C:\Users\ossen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskNode = 'C:\Users\ossen\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$taskMarker = 'C:\Users\ossen\.codex\plugins\cache\openai-primary-runtime\pdf\26.1020.11618\skills\pdf\container_tools\mark_artifact_operation_started.mjs'
$taskTectonic = 'C:\Users\ossen\OneDrive\Documents\SmartCity\tools_bin\tectonic\tectonic.exe'
$taskPoppler = 'C:\Users\ossen\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin'
Set-Location -LiteralPath $taskRoot
& $taskPython (Join-Path $taskRoot 'build_v3_final_tables.py')
if ($LASTEXITCODE -ne 0) { throw 'Table audit/generation failed' }
& $taskPython (Join-Path $taskRoot 'update_response_v3.py')
if ($LASTEXITCODE -ne 0) { throw 'Response generation failed' }
$taskTmp = Join-Path $taskRoot 'tmp'
$taskOut = Join-Path $taskRoot 'output\pdf'
if ($RenderSubfolder -notin @('draft_qa','final_qa')) { throw 'Unknown task render folder' }
$taskRender = Join-Path $taskRoot ('tmp\pdfs\' + $RenderSubfolder)
New-Item -ItemType Directory -Path $taskTmp,$taskOut,$taskRender -Force | Out-Null
$taskCacheSource = Join-Path (Split-Path -Parent $taskRoot) 'revision_v2\tmp\tectonic-cache'
$taskCache = Join-Path $taskTmp 'tectonic-cache'
if (-not (Test-Path -LiteralPath $taskCache)) {
    Copy-Item -LiteralPath $taskCacheSource -Destination $taskTmp -Recurse
}
$env:TECTONIC_CACHE_DIR = $taskCache
$taskMarkerState = Join-Path $taskTmp 'pdf_artifact_operation_started.json'
if (-not (Test-Path -LiteralPath $taskMarkerState)) {
    & $taskNode $taskMarker --operation-kind create --expected-output-count 3 --output-format pdf
    if ($LASTEXITCODE -ne 0) { throw 'PDF operation marker failed' }
    @{started_utc=[DateTime]::UtcNow.ToString('o');outputs=3;operation='create'} | ConvertTo-Json | Set-Content -LiteralPath $taskMarkerState -Encoding utf8
}
Set-Location -LiteralPath (Join-Path $taskRoot 'manuscript_v3')
foreach ($taskName in @('main','supplement','response_to_reviewers')) {
    $taskLog = Join-Path $taskTmp ($taskName + '_compile.txt')
    & $taskTectonic --only-cached --keep-logs --outdir $taskOut ($taskName + '.tex') *> $taskLog
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $taskLog -Tail 45
        throw ('TeX compilation failed: ' + $taskName)
    }
    $taskPdf = Join-Path $taskOut ($taskName + '.pdf')
    & (Join-Path $taskPoppler 'pdfinfo.exe') $taskPdf | Set-Content -LiteralPath (Join-Path $taskTmp ($taskName + '_pdfinfo.txt')) -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw ('pdfinfo failed: ' + $taskName) }
    & (Join-Path $taskPoppler 'pdftoppm.exe') -r 110 -png $taskPdf (Join-Path $taskRender $taskName) *> (Join-Path $taskTmp ($taskName + '_render.txt'))
    if ($LASTEXITCODE -ne 0) { throw ('PDF rendering failed: ' + $taskName) }
    Write-Output ('DRAFT_PDF_RENDERED ' + $taskName)
}
Write-Output 'ALL_DRAFT_PDFS_RENDERED; visual review and final network integration remain'
