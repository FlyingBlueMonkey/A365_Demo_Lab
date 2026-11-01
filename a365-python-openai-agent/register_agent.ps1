[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$RegistrationOnly
)

$ErrorActionPreference = 'Stop'
Get-Command a365 -ErrorAction Stop | Out-Null

Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath 'a365.config.json')) {
        throw 'Create a private a365.config.json from the example before registration.'
    }

    $arguments = @('setup', 'all', '--authmode', 's2s', '--aiteammate', 'false')
    if ($RegistrationOnly) {
        $arguments += '--agent-registration-only'
    }
    if (-not $Apply) {
        $arguments += '--dry-run'
    }
    & a365 @arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Agent 365 setup failed. Resolve the CLI errors and any administrator handoff before continuing.'
    }
    if (-not $Apply) {
        Write-Output 'Preview only. No registration is claimed. Review the plan before running with -Apply.'
        return
    }

    $generated = Get-Content -LiteralPath 'a365.generated.config.json' -Raw | ConvertFrom-Json
    foreach ($field in @('agentBlueprintId', 'agenticAppId', 'agentRegistrationId')) {
        $identifier = [guid]::Empty
        if (-not [guid]::TryParse([string]$generated.$field, [ref]$identifier) -or $identifier -eq [guid]::Empty) {
            throw "Setup did not produce a valid $field. Check registration status before running the agent."
        }
    }
    if ($generated.agentBlueprintId -eq $generated.agenticAppId) {
        throw 'Blueprint and agent instance IDs must differ.'
    }
    [pscustomobject]@{
        BlueprintId = $generated.agentBlueprintId
        AgentId = $generated.agenticAppId
        RegistrationId = $generated.agentRegistrationId
        NextStep = 'Verify this registered agent in the target tenant catalog; then run app.py --check-config.'
    }
}
finally {
    Pop-Location
}