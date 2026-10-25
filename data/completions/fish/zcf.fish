# fish completion for zcf

complete -c zcf -f

complete -c zcf -n "__fish_use_subcommand" -a "dashboard" -d "Display system dashboard"
complete -c zcf -n "__fish_use_subcommand" -a "console" -d "Launch local browser-based Web Console"
complete -c zcf -n "__fish_use_subcommand" -a "web" -d "Launch local browser-based Web Console"
complete -c zcf -n "__fish_use_subcommand" -a "gui" -d "Launch graphical Control Center"
complete -c zcf -n "__fish_use_subcommand" -a "run" -d "Execute application with optimal runtime and sandboxing"
complete -c zcf -n "__fish_use_subcommand" -a "integrate" -d "Manage desktop menu shortcuts"
complete -c zcf -n "__fish_use_subcommand" -a "service" -d "Manage background maintenance and binfmt"
complete -c zcf -n "__fish_use_subcommand" -a "inspect" -d "Inspect application binary"
complete -c zcf -n "__fish_use_subcommand" -a "env" -d "Inspect host environment"
complete -c zcf -n "__fish_use_subcommand" -a "plan" -d "Generate compatibility plan"
complete -c zcf -n "__fish_use_subcommand" -a "test" -d "Test application capability"
complete -c zcf -n "__fish_use_subcommand" -a "diag" -d "Analyze failure log and recommend fixes"
complete -c zcf -n "__fish_use_subcommand" -a "research" -d "Execute 11-step research workflow"
complete -c zcf -n "__fish_use_subcommand" -a "db" -d "Query compatibility database"

complete -c zcf -n "__fish_seen_subcommand_from run" -l sandbox -d "Enforce Bubblewrap sandboxing"
complete -c zcf -n "__fish_seen_subcommand_from run" -l no-sandbox -d "Disable sandboxing"
complete -c zcf -n "__fish_seen_subcommand_from run" -l allow-unconfined -d "Allow unconfined execution if sandbox unavailable"
complete -c zcf -n "__fish_seen_subcommand_from run" -l dry-run -d "Simulate execution without starting process"
complete -c zcf -n "__fish_seen_subcommand_from run" -l allow-network -d "Permit network access in sandbox"
complete -c zcf -n "__fish_seen_subcommand_from run" -l timeout -d "Execution timeout in seconds"
complete -c zcf -n "__fish_seen_subcommand_from run" -l headless -d "Force virtual Xvfb display"
complete -c zcf -n "__fish_seen_subcommand_from run" -l install-deps -d "Automatically install missing dependencies"

complete -c zcf -n "__fish_seen_subcommand_from test" -l dry-run -d "Validate orchestration path without process execution"
complete -c zcf -n "__fish_seen_subcommand_from test" -l record -d "Record test outcome to compatibility database"
complete -c zcf -n "__fish_seen_subcommand_from test" -l contributor -d "Contributor attribution name"

complete -c zcf -n "__fish_seen_subcommand_from console web" -l host -d "Host interface to bind"
complete -c zcf -n "__fish_seen_subcommand_from console web" -l port -d "Port to listen on"
complete -c zcf -n "__fish_seen_subcommand_from console web" -l allow-remote -d "Permit remote network access"
complete -c zcf -n "__fish_seen_subcommand_from console web" -l no-browser -d "Do not open browser automatically"

complete -c zcf-runner -w zcf
