param(
    [ValidateSet("1", "2", "3", "4", "5", "6", "all")]
    [string]$Example = "1"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Hotspot = Join-Path $RepoRoot "hotspot.exe"
$Hotfloorplan = Join-Path $RepoRoot "hotfloorplan.exe"
$Python = "python"
$Perl = "perl"

function Assert-File {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Required file not found: $Path"
    }
}

function Reset-Outputs {
    param([string]$ExampleDir, [string[]]$InitFiles = @("*.init"))

    Push-Location $ExampleDir
    try {
        foreach ($pattern in $InitFiles) {
            Remove-Item -Force -ErrorAction SilentlyContinue $pattern
        }
        New-Item -ItemType Directory -Force outputs | Out-Null
        Remove-Item -Force -ErrorAction SilentlyContinue outputs\*
    } finally {
        Pop-Location
    }
}

function Invoke-Checked {
    param([scriptblock]$Command)

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Run-Example1 {
    $dir = Join-Path $RepoRoot "examples\example1"
    Reset-Outputs $dir @("gcc.init")
    Push-Location $dir
    try {
        Invoke-Checked { & $Hotspot -c example.config -f ev6.flp -p gcc.ptrace -materials_file example.materials -model_type block -steady_file outputs\gcc.steady -o outputs\gcc.ttrace }
        Copy-Item outputs\gcc.steady gcc.init -Force
        Invoke-Checked { & $Hotspot -c example.config -init_file gcc.init -f ev6.flp -p gcc.ptrace -materials_file example.materials -model_type block -o outputs\gcc.ttrace }
    } finally {
        Pop-Location
    }
}

function Run-Example2 {
    $dir = Join-Path $RepoRoot "examples\example2"
    Reset-Outputs $dir @("gcc.init")
    Push-Location $dir
    try {
        Invoke-Checked { & $Hotspot -c example.config -f ev6.flp -p gcc.ptrace -materials_file example.materials -model_type grid -steady_file outputs\gcc.steady -grid_steady_file outputs\gcc.grid.steady }
        Copy-Item outputs\gcc.steady gcc.init -Force
        Invoke-Checked { & $Hotspot -c example.config -init_file gcc.init -f ev6.flp -p gcc.ptrace -materials_file example.materials -model_type grid -o outputs\gcc.ttrace -grid_transient_file outputs\gcc.grid.ttrace }
        Invoke-Checked { & $Python ..\..\scripts\split_grid_steady.py outputs\gcc.grid.steady 4 64 64 }
        Invoke-Checked { & $Python ..\..\scripts\grid_thermal_map.py ev6.flp outputs\gcc_layer0.grid.steady outputs\gcc.png }
        if (Get-Command $Perl -ErrorAction SilentlyContinue) {
            & $Perl ..\..\scripts\grid_thermal_map.pl ev6.flp outputs\gcc_layer0.grid.steady 64 64 > outputs\gcc.svg
            if ($LASTEXITCODE -ne 0) {
                throw "Perl heat map generation failed with exit code $LASTEXITCODE"
            }
        }
    } finally {
        Pop-Location
    }
}

function Run-Example3 {
    $dir = Join-Path $RepoRoot "examples\example3"
    Reset-Outputs $dir
    Push-Location $dir
    try {
        Invoke-Checked { & $Hotspot -c example.config -p example.ptrace -grid_layer_file example.lcf -materials_file example.materials -model_type grid -detailed_3D on -steady_file outputs\example.steady -grid_steady_file outputs\example.grid.steady }
        Copy-Item outputs\example.steady example.init -Force
        Invoke-Checked { & $Hotspot -c example.config -p example.ptrace -grid_layer_file example.lcf -materials_file example.materials -model_type grid -detailed_3D on -o outputs\example.ttrace -grid_transient_file outputs\example.grid.ttrace }
        Invoke-Checked { & $Python ..\..\scripts\split_grid_steady.py outputs\example.grid.steady 6 64 64 }
        Invoke-Checked { & $Python ..\..\scripts\grid_thermal_map.py floorplan2.flp outputs\example_layer2.grid.steady 64 64 outputs\layer2.png }
        if (Get-Command $Perl -ErrorAction SilentlyContinue) {
            & $Perl ..\..\scripts\grid_thermal_map.pl floorplan2.flp outputs\example_layer2.grid.steady 64 64 > outputs\layer2.svg
            if ($LASTEXITCODE -ne 0) {
                throw "Perl heat map generation failed with exit code $LASTEXITCODE"
            }
        }
    } finally {
        Pop-Location
    }
}

function Run-Example4 {
    $dir = Join-Path $RepoRoot "examples\example4"
    Reset-Outputs $dir
    Push-Location $dir
    try {
        Invoke-Checked { & $Hotspot -c example.config -p ev6_3D.ptrace -grid_layer_file ev6_3D.lcf -model_type grid -detailed_3D on -grid_steady_file outputs\example.grid.steady -steady_file outputs\example.steady }
        Copy-Item outputs\example.steady example.init -Force
        Invoke-Checked { & $Hotspot -c example.config -p ev6_3D.ptrace -grid_layer_file ev6_3D.lcf -init_file example.init -model_type grid -detailed_3D on -o outputs\example.transient -grid_transient_file outputs\example.grid.ttrace }
    } finally {
        Pop-Location
    }
}

function Run-Example5 {
    $dir = Join-Path $RepoRoot "examples\example5"
    Reset-Outputs $dir
    Push-Location $dir
    try {
        try {
            Invoke-Checked { & $Hotspot -c example.config -p example.ptrace -materials_file example.materials -grid_layer_file example.lcf -model_type grid -detailed_3D on -use_microchannels 1 -grid_steady_file outputs\example.grid.steady -steady_file outputs\example.steady }
            Copy-Item outputs\example.steady example.init -Force
            Invoke-Checked { & $Hotspot -c example.config -p example.ptrace -materials_file example.materials -grid_layer_file example.lcf -init_file example.init -model_type grid -detailed_3D on -use_microchannels 1 -o outputs\example.transient -grid_transient_file outputs\example.grid.ttrace }
        } catch {
            throw "Example5 requires HotSpot built with SuperLU support. Rebuild with `make SUPERLU=1` after installing SuperLU/BLAS for your compiler. Original error: $($_.Exception.Message)"
        }
    } finally {
        Pop-Location
    }
}

function Run-Example6 {
    $dir = Join-Path $RepoRoot "examples\example6"
    Push-Location $dir
    try {
        Remove-Item -Force -ErrorAction SilentlyContinue output.flp
        Invoke-Checked { & $Hotfloorplan -c example.config -f ev6.desc -p avg.p -o output.flp }
    } finally {
        Pop-Location
    }
}

Assert-File $Hotspot
Assert-File $Hotfloorplan

$examples = if ($Example -eq "all") { @("1", "2", "3", "4", "5", "6") } else { @($Example) }
foreach ($item in $examples) {
    Write-Host "Running example$item..."
    switch ($item) {
        "1" { Run-Example1 }
        "2" { Run-Example2 }
        "3" { Run-Example3 }
        "4" { Run-Example4 }
        "5" { Run-Example5 }
        "6" { Run-Example6 }
    }
}

Write-Host "Done."
