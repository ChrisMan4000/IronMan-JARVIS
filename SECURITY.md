# Security Policy

IronMan-JARVIS is a hobby project. It runs on your own PC and talks to a local LM Studio model. Nothing is sent to a cloud service by this project.

## Supported versions

Only the newest code on the `ironman` branch and the newest release get fixes.

| Version                    | Supported |
| -------------------------- | --------- |
| Latest `ironman` + release | :white_check_mark: |
| Older releases             | :x:       |

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Use GitHub's private reporting instead: open the **Security** tab of this repository, click **Report a vulnerability**, and describe what you found and how to reproduce it.

This is a one-person project, so replies can take a few days. If the report is valid, I will fix it as soon as I can and credit you if you want.

## Please note

- Jarvis can control smart-home devices and run local tools. Keep it on your home network and do not expose it to the internet.
- Never share your Tado token, Hue key, Sonos IP or other secrets in an issue or pull request.
- Problems in the upstream OpenJarvis code should also be reported to the [OpenJarvis project](https://github.com/open-jarvis/OpenJarvis).
