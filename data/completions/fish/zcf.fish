# fish completion for zcf

complete -c zcf -f

complete -c zcf -n "__fish_use_subcommand" -a "dashboard" -d "Display system dashboard"
complete -c zcf -n "__fish_use_subcommand" -a "run" -d "Execute application with optimal runtime and sandboxing"
complete -c zcf -n "__fish_use_subcommand" -a "inspect" -d "Inspect application binary"
complete -c zcf -n "__fish_use_subcommand" -a "env" -d "Inspect host environment"
complete -c zcf -n "__fish_use_subcommand" -a "plan" -d "Generate compatibility plan"
complete -c zcf -n "__fish_use_subcommand" -a "test" -d "Test application capability"
complete -c zcf -n "__fish_use_subcommand" -a "diag" -d "Analyze failure log and recommend fixes"
complete -c zcf -n "__fish_use_subcommand" -a "research" -d "Execute 11-step research workflow"
complete -c zcf -n "__fish_use_subcommand" -a "db" -d "Query compatibility database"

complete -c zcf -n "__fish_seen_subcommand_from run" -l sandbox -d "Enforce Bubblewrap sandboxing"
complete -c zcf -n "__fish_seen_subcommand_from run" -l no-sandbox -d "Disable sandboxing"
complete -c zcf -n "__fish_seen_subcommand_from run" -l headless -d "Force virtual Xvfb display"
complete -c zcf -n "__fish_seen_subcommand_from run" -l install-deps -d "Automatically install missing dependencies"

complete -c zcf-runner -w zcf
