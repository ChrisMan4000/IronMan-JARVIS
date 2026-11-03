# PSScriptAnalyzer settings for the IronMan J.A.R.V.I.S. scripts (used by Invoke-ScriptAnalyzer and desloppify).
@{
    ExcludeRules = @(
        # These scripts are interactive installers and launchers: coloured console text for the user is the point.
        # Write-Output would mix the messages into function return values (for example Chk, Status, Wait-For).
        'PSAvoidUsingWriteHost'
    )
}
