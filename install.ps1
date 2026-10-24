#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Installe uv, WaveStack et le modele Qwen par defaut sans droits administrateur,
    puis lance l'application. Idempotent : relancer ce script ne retelecharge ni le
    projet ni le modele s'ils sont deja presents.

.PARAMETER InstallDir
    Dossier du projet. Par defaut : le dossier du script s'il contient deja
    pyproject.toml (clone ou zip existant), sinon "<Documents>\WaveStack".

.PARAMETER DataDir
    Dossier de donnees (venv, caches, modeles). Par defaut WAVESTACK_DATA_DIR ou
    "%LOCALAPPDATA%\WaveStack". Reste toujours hors de $InstallDir et de Documents.

.PARAMETER UvInstallDir
    Dossier d'installation de uv (passe a son installeur via UV_INSTALL_DIR).

.PARAMETER NoLaunch
    N'ouvre pas l'application a la fin (utile pour les tests).

.PARAMETER Models
    Modeles locaux facultatifs a telecharger en plus de Qwen3.5-2B (qui reste le modele par
    defaut), identifiants separes par des virgules : qwen3.5-0.8b, minicpm5, granite-4.0-350m, granite-4.0-1b. `-Models list`
    affiche la table (identifiant, fichier, taille, licence) puis s'arrete. Equivalent :
    WAVESTACK_MODELS=id1,id2 (sous `irm | iex`, qui ne passe pas d'option). Chaque fichier
    est verifie par son empreinte SHA-256 apres telechargement.

.PARAMETER WithMiniCPM
    Alias de `-Models minicpm5` (publie en 1.2.0). Equivalent : WAVESTACK_WITH_MINICPM=1.

.PARAMETER DryRun
    Affiche les dossiers resolus sans rien installer, cloner, telecharger ni lancer.
#>
[CmdletBinding()]
param(
    [string]$InstallDir,
    [string]$DataDir,
    [string]$UvInstallDir,
    [switch]$NoLaunch,
    [string[]]$Models,
    [switch]$WithMiniCPM,
    [switch]$DryRun
)

# Corps dans un bloc enfant : sous `irm | iex`, ses variables et preferences ne restent
# pas dans la session de l'utilisateur.
& {
    $ErrorActionPreference = 'Stop'

    # Memes valeurs que README.md (une seule source de verite : voir tests/test_installers.py)
    $QwenUrl  = 'https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf'
    $QwenFile = 'Qwen3.5-2B-Q4_K_M.gguf'
    # Modeles locaux facultatifs : une seule table, lue par -Models (revision epinglee, taille,
    # licence et empreinte SHA-256 verifiee apres telechargement).
    $OptionalModels = @(
        @{ Id = 'qwen3.5-0.8b'; Size = '0,5 Go'; Bytes = 532517120; License = 'Apache-2.0'
           File = 'Qwen3.5-0.8B-Q4_K_M.gguf'
           Sha256 = 'bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517'
           Url = 'https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/6ab461498e2023f6e3c1baea90a8f0fe38ab64d0/Qwen3.5-0.8B-Q4_K_M.gguf' },
        @{ Id = 'minicpm5'; Size = '1,5 Go'; Bytes = 1561318368; License = 'Apache-2.0'
           File = 'MiniCPM5-2B-Q4_K_M.gguf'
           Sha256 = 'ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd'
           Url = 'https://huggingface.co/openbmb/MiniCPM5-2B-GGUF/resolve/2079a22f3beaa4e306449978533478fe0522f4b3/MiniCPM5-2B-Q4_K_M.gguf' },
        @{ Id = 'granite-4.0-350m'; Size = '0,3 Go'; Bytes = 236985760; License = 'Apache-2.0'
           File = 'granite-4.0-350m-Q4_K_M.gguf'
           Sha256 = '771c588a49607f274a2bba3185733607ebe6f74b996ab90e2d6bee0d98bcec52'
           Url = 'https://huggingface.co/ibm-granite/granite-4.0-350m-GGUF/resolve/b8208a86a58427e1739265318028eb5895b74bf2/granite-4.0-350m-Q4_K_M.gguf' },
        @{ Id = 'granite-4.0-1b'; Size = '1,0 Go'; Bytes = 1023645440; License = 'Apache-2.0'
           File = 'granite-4.0-1b-Q4_K_M.gguf'
           Sha256 = '22ec0f9cc99a90185312de3c882c84e7bd6789bdd050389844380a01a831d7f1'
           Url = 'https://huggingface.co/ibm-granite/granite-4.0-1b-GGUF/resolve/b27c2fe3f211b7f44e80fa620177aea371099aaa/granite-4.0-1b-Q4_K_M.gguf' }
    )
    $RepoUrl  = 'https://github.com/Aliquanto3/wavestack.git'
    $ZipUrl   = 'https://github.com/Aliquanto3/wavestack/archive/refs/heads/main.zip'
    $ZipRoot  = 'wavestack-main'

    # -- Modeles facultatifs demandes : valides avant toute action (rien n'est cree si un
    #    identifiant est inconnu). `list` affiche la table et s'arrete.
    $requested = @()
    # [string[]] : `-Models a,b` saisi dans une session PowerShell arrive en tableau, sous -File en
    # une chaine ; les deux formes sont rejointes puis coupees aux virgules.
    $modelsArg = if ($Models) { $Models -join ',' } else { $env:WAVESTACK_MODELS }
    if ($modelsArg) {
        $requested += @($modelsArg -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    }
    if ($WithMiniCPM -or ($env:WAVESTACK_WITH_MINICPM -eq '1')) { $requested += 'minicpm5' }
    if ($requested -contains 'list') {
        Write-Host 'Modeles facultatifs (Qwen3.5-2B est toujours telecharge) :'
        foreach ($m in $OptionalModels) {
            Write-Host ('  {0,-14} {1,-28} {2,-8} {3}' -f $m.Id, $m.File, $m.Size, $m.License)
        }
        return
    }
    $validIds = @($OptionalModels | ForEach-Object { $_.Id })
    foreach ($id in $requested) {
        if ($validIds -notcontains $id) {
            throw "Modele facultatif inconnu : '$id'. Identifiants valides : $($validIds -join ', ')."
        }
    }
    $selected = @($OptionalModels | Where-Object { $requested -contains $_.Id })

    # Verifie l'empreinte SHA-256 d'un fichier telecharge ; non conforme : fichier supprime et arret.
    # SHA256 de .NET plutot que Get-FileHash : Windows PowerShell 5.1 lance depuis PowerShell 7
    # (install.bat dans un terminal pwsh) herite de son PSModulePath et ne trouve plus Get-FileHash.
    function Test-ModelHash([string]$Path, [string]$Expected) {
        $stream = [IO.File]::OpenRead($Path)
        try {
            $sha = [Security.Cryptography.SHA256]::Create()
            $actual = -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') })
        } finally {
            $stream.Dispose()
        }
        if ($actual -ne $Expected.ToLowerInvariant()) {
            [IO.File]::Delete($Path)
            throw "Empreinte SHA-256 non conforme pour $(Split-Path -Leaf $Path) : fichier supprime. Attendue $Expected, obtenue $actual."
        }
    }

    # -- Dossier du projet : sur place si on est deja dans un clone ou un zip, sinon un
    #    dossier visible sous Documents (chemin reel, eventuellement redirige par OneDrive).
    if (-not $InstallDir) {
        if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'pyproject.toml'))) {
            $InstallDir = $PSScriptRoot
        } else {
            $documents = [Environment]::GetFolderPath('MyDocuments')
            $InstallDir = Join-Path $documents 'WaveStack'
        }
    }

    # -- Dossier de donnees : venv, caches et modeles, jamais sous Documents/OneDrive.
    if (-not $DataDir) {
        $DataDir = $env:WAVESTACK_DATA_DIR
        if (-not $DataDir) { $DataDir = Join-Path $env:LOCALAPPDATA 'WaveStack' }
    }
    $VenvDir   = Join-Path $DataDir 'venv'
    $CacheDir  = Join-Path $DataDir 'uv-cache'
    $ModelsDir = Join-Path $DataDir 'models'
    $ModelPath = Join-Path $ModelsDir $QwenFile

    Write-Host "Projet      : $InstallDir"
    Write-Host "Donnees     : $DataDir"
    Write-Host "Modele Qwen : $ModelPath"
    foreach ($m in $selected) { Write-Host "Modele $($m.Id) : $(Join-Path $ModelsDir $m.File)" }

    if ($DryRun) {
        Write-Host "(mode a blanc : aucune commande reseau ou d'installation executee)"
        return
    }

    # -- uv, dans le profil utilisateur, sans droits administrateur.
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host 'Installation de uv...'
        if ($UvInstallDir) { $env:UV_INSTALL_DIR = $UvInstallDir }
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        if ($LASTEXITCODE -ne 0) { throw "L'installation de uv a echoue (code $LASTEXITCODE)." }
        $uvBin = if ($UvInstallDir) { $UvInstallDir } else { Join-Path $env:USERPROFILE '.local\bin' }
        $env:PATH = "$uvBin;$env:PATH"
    }

    # -- Projet : clone si absent ; inchange s'il est deja la (idempotent).
    if (-not (Test-Path (Join-Path $InstallDir 'pyproject.toml'))) {
        Write-Host "Recuperation de WaveStack dans $InstallDir..."
        $parent = Split-Path -Parent $InstallDir
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        if (Get-Command git -ErrorAction SilentlyContinue) {
            git clone $RepoUrl $InstallDir
            if ($LASTEXITCODE -ne 0) { throw "git clone a echoue (code $LASTEXITCODE)." }
        } else {
            # Pas de git sur le poste : archive zip de la branche main, sans droits admin.
            $zip = Join-Path $env:TEMP 'wavestack-main.zip'
            Invoke-WebRequest -UseBasicParsing $ZipUrl -OutFile $zip
            Expand-Archive -LiteralPath $zip -DestinationPath $parent -Force
            Rename-Item -LiteralPath (Join-Path $parent $ZipRoot) (Split-Path -Leaf $InstallDir)
            [IO.File]::Delete($zip)  # Remove-Item refuse les chemins courts 8.3 de %TEMP%
        }
    } else {
        Write-Host "WaveStack deja present dans $InstallDir, pas de nouveau clone."
    }

    # -- Modele Qwen : telecharge si absent (idempotent).
    New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
    if (-not (Test-Path $ModelPath)) {
        Write-Host 'Telechargement du modele Qwen (1,3 Go)...'
        $ProgressPreference = 'SilentlyContinue'
        # Telechargement vers .part puis renommage : une coupure ne laisse pas un faux modele.
        Invoke-WebRequest -UseBasicParsing $QwenUrl -OutFile "$ModelPath.part"
        Move-Item -Force -LiteralPath "$ModelPath.part" $ModelPath
    } else {
        Write-Host 'Modele Qwen deja present, pas de nouveau telechargement.'
    }

    # -- Modeles facultatifs (-Models) : telecharges si absents, verifies par empreinte.
    foreach ($m in $selected) {
        $path = Join-Path $ModelsDir $m.File
        if (-not (Test-Path $path)) {
            Write-Host "Telechargement du modele $($m.Id) ($($m.Size))..."
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -UseBasicParsing $m.Url -OutFile "$path.part"
            Test-ModelHash "$path.part" $m.Sha256
            Move-Item -Force -LiteralPath "$path.part" $path
        } else {
            Write-Host "Modele $($m.Id) deja present, pas de nouveau telechargement."
        }
    }

    if (-not $NoLaunch) {
        # Venv et caches sous le dossier de donnees, jamais sous Documents ; l'appli lit ses
        # modeles dans le meme dossier. Variables retirees ensuite (session de `irm | iex`).
        $saved = @{}
        $vars = @{ UV_PROJECT_ENVIRONMENT = $VenvDir; UV_CACHE_DIR = $CacheDir; WAVESTACK_DATA_DIR = $DataDir }
        foreach ($k in $vars.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); Set-Item "env:$k" $vars[$k] }
        Push-Location $InstallDir
        try {
            Write-Host 'Lancement de WaveStack...'
            & uv run wavestack
        } finally {
            Pop-Location
            foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
        }
    }

    Write-Host ''
    Write-Host 'Pour relancer WaveStack plus tard : reexecutez install.bat (ou install.ps1) dans ce dossier.'
}
