# fish completion for zcf

complete -c zcf -f

complete -c zcf -n "__fish_use_subcommand" -a "dashboard" -d "Display system dashboard"
complete -c zcf -n "__fish_use_subcommand" -a "console" -d "Launch local browser-based Web Console"
complete -c zcf -n "__fish_use_subcommand" -a "web" -d "Launch local browser-based Web Console"
complete -c zcf -n "__fish_use_subcommand" -a "gui" -d "Launch graphical Control Center"
complete -c zcf -n "__fish_use_subcommand" -a "run" -d "Execute application with optimal runtime, sandboxing, and gaming tuning"
complete -c zcf -n "__fish_use_subcommand" -a "runners" -d "Discover, download, and manage Proton and Wine compatibility runners"
complete -c zcf -n "__fish_use_subcommand" -a "snapshot" -d "Time-Machine instant restore points and prefix rollbacks"
complete -c zcf -n "__fish_use_subcommand" -a "vault" -d "Universal Game Save Vault for discovery, backup, and prefix migration"
complete -c zcf -n "__fish_use_subcommand" -a "taskmgr" -d "Monitor active processes, kill wineserver, and launch Wine diagnostic tools"
complete -c zcf -n "__fish_use_subcommand" -a "prescribe" -d "Autonomous healing engine to analyze crashes and auto-repair prefixes"
complete -c zcf -n "__fish_use_subcommand" -a "components" -d "Manage Windows runtime components and DLL overrides"
complete -c zcf -n "__fish_use_subcommand" -a "completions" -d "Output shell completion script for Bash, Zsh, or Fish"
complete -c zcf -n "__fish_use_subcommand" -a "integrate" -d "Manage desktop menu shortcuts"
complete -c zcf -n "__fish_use_subcommand" -a "service" -d "Manage background maintenance and binfmt"
complete -c zcf -n "__fish_use_subcommand" -a "inspect" -d "Inspect application binary"
complete -c zcf -n "__fish_use_subcommand" -a "env" -d "Inspect host environment"
complete -c zcf -n "__fish_use_subcommand" -a "doctor" -d "Run pre-flight system readiness audit and gaming optimization check"
complete -c zcf -n "__fish_use_subcommand" -a "plan" -d "Generate compatibility plan"
complete -c zcf -n "__fish_use_subcommand" -a "test" -d "Test application capability"
complete -c zcf -n "__fish_use_subcommand" -a "diag" -d "Analyze failure log and recommend fixes"
complete -c zcf -n "__fish_use_subcommand" -a "research" -d "Execute 11-step research workflow"
complete -c zcf -n "__fish_use_subcommand" -a "db" -d "Query compatibility database"
complete -c zcf -n "__fish_use_subcommand" -a "history" -d "View and compare execution test history"

# history
complete -c zcf -n "__fish_seen_subcommand_from history" -l sha256 -d "Filter runs by artifact SHA-256"
complete -c zcf -n "__fish_seen_subcommand_from history" -l limit -d "Max number of runs to display"
complete -c zcf -n "__fish_seen_subcommand_from history" -l compare -d "Compare two run IDs side-by-side"
complete -c zcf -n "__fish_seen_subcommand_from history" -l clear -d "Clear all stored execution run logs"
complete -c zcf -n "__fish_seen_subcommand_from history" -l json -d "Output machine-readable JSON"
complete -c zcf -n "__fish_seen_subcommand_from doctor" -l json -d "Output machine-readable JSON"

# run
complete -c zcf -n "__fish_seen_subcommand_from run" -l no-sandbox -d "Disable Bubblewrap sandboxing"
complete -c zcf -n "__fish_seen_subcommand_from run" -l allow-unconfined -d "Allow unconfined execution if sandbox unavailable"
complete -c zcf -n "__fish_seen_subcommand_from run" -l dry-run -d "Simulate execution without starting process"
complete -c zcf -n "__fish_seen_subcommand_from run" -l allow-network -d "Permit network access in sandbox"
complete -c zcf -n "__fish_seen_subcommand_from run" -l timeout -d "Execution timeout in seconds"
complete -c zcf -n "__fish_seen_subcommand_from run" -l headless -d "Force virtual Xvfb display"
complete -c zcf -n "__fish_seen_subcommand_from run" -l install-deps -d "Automatically install missing dependencies"
complete -c zcf -n "__fish_seen_subcommand_from run" -l gamemode -d "Wrap execution with Feral GameMode (gamemoderun)"
complete -c zcf -n "__fish_seen_subcommand_from run" -l gamescope -d "Execute inside Gamescope nested compositor"
complete -c zcf -n "__fish_seen_subcommand_from run" -l upscale -a "fsr nis pixel linear" -d "Upscaling filter in Gamescope"
complete -c zcf -n "__fish_seen_subcommand_from run" -l fsr-sharpness -d "FSR sharpness (0-10)"
complete -c zcf -n "__fish_seen_subcommand_from run" -l fps-limit -d "Frame rate cap / refresh rate"
complete -c zcf -n "__fish_seen_subcommand_from run" -l mangohud -d "Enable MangoHud performance overlay"
complete -c zcf -n "__fish_seen_subcommand_from run" -l tuning-preset -a "esports 4k_fidelity power_saver minimal_overlay" -d "Use preconfigured performance profile"

# runners
complete -c zcf -n "__fish_seen_subcommand_from runners" -a "list available install"
complete -c zcf -n "__fish_seen_subcommand_from runners" -l limit -d "Max releases to query"
complete -c zcf -n "__fish_seen_subcommand_from runners" -l json -d "Output JSON"

# snapshot
complete -c zcf -n "__fish_seen_subcommand_from snapshot" -a "create list restore delete"
complete -c zcf -n "__fish_seen_subcommand_from snapshot" -l label -d "Snapshot description label"
complete -c zcf -n "__fish_seen_subcommand_from snapshot" -l json -d "Output JSON"

# vault
complete -c zcf -n "__fish_seen_subcommand_from vault" -a "discover backup list restore delete"
complete -c zcf -n "__fish_seen_subcommand_from vault" -l app -d "Application name filter"
complete -c zcf -n "__fish_seen_subcommand_from vault" -l notes -d "Notes for backup"
complete -c zcf -n "__fish_seen_subcommand_from vault" -l json -d "Output JSON"

# taskmgr
complete -c zcf -n "__fish_seen_subcommand_from taskmgr" -a "list kill reset-locks launch"
complete -c zcf -n "__fish_seen_subcommand_from taskmgr" -l prefix -d "Prefix filter"
complete -c zcf -n "__fish_seen_subcommand_from taskmgr" -l json -d "Output JSON"

# prescribe
complete -c zcf -n "__fish_seen_subcommand_from prescribe" -a "generate apply"
complete -c zcf -n "__fish_seen_subcommand_from prescribe" -l app -d "Application name"
complete -c zcf -n "__fish_seen_subcommand_from prescribe" -l prefix -d "Target prefix path"
complete -c zcf -n "__fish_seen_subcommand_from prescribe" -l dry-run -d "Simulate repair without modifying prefix"
complete -c zcf -n "__fish_seen_subcommand_from prescribe" -l json -d "Output JSON"

# components
complete -c zcf -n "__fish_seen_subcommand_from components" -a "list install overrides"
complete -c zcf -n "__fish_seen_subcommand_from components" -l prefix -d "Prefix path filter"
complete -c zcf -n "__fish_seen_subcommand_from components" -l timeout -d "Installation timeout in seconds"
complete -c zcf -n "__fish_seen_subcommand_from components" -l json -d "Output JSON"

# completions
complete -c zcf -n "__fish_seen_subcommand_from completions" -a "bash zsh fish"

# test
complete -c zcf -n "__fish_seen_subcommand_from test" -l dry-run -d "Validate orchestration path without process execution"
complete -c zcf -n "__fish_seen_subcommand_from test" -l execute -d "Perform real live execution test"
complete -c zcf -n "__fish_seen_subcommand_from test" -l record -d "Record test outcome to compatibility database"
complete -c zcf -n "__fish_seen_subcommand_from test" -l contributor -d "Contributor attribution name"

# console / web
complete -c zcf -n "__fish_seen_subcommand_from console web" -l host -d "Host interface to bind"
complete -c zcf -n "__fish_seen_subcommand_from console web" -l port -d "Port to listen on"
complete -c zcf -n "__fish_seen_subcommand_from console web" -l allow-remote -d "Permit remote network access"
complete -c zcf -n "__fish_seen_subcommand_from console web" -l no-browser -d "Do not open browser automatically"

complete -c zcf-runner -w zcf
