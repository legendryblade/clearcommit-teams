"""Entry point for the packaged Windows build (see build.ps1)."""

from clearcommit_teams.app import main

if __name__ == "__main__":
    raise SystemExit(main())
