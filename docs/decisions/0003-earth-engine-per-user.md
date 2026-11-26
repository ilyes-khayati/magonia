# 0003. Earth Engine through each user's own project

Status: accepted; refined for version 1, which is single-user and local (see 0004): one Earth Engine project per installation, signed in on that computer, and no demo mode.

## Context
Earth Engine is free for noncommercial research, but a shared platform account
would fall under commercial terms and concentrate quota on one project.

## Decision
Each user signs in and connects their own Earth Engine project. The data layer is
an interface so other catalogues can replace or complement Earth Engine later.

## Consequences
No shared quota or licensing exposure. Onboarding needs a clear Earth Engine
connection step, and a demo mode with cached sample areas for first-time users.
