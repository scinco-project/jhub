# Changelog
All notable changes to this project will be documented in this file

## [26Q2.0] (June 23, 2026)
### 🚀 Added
- Tenant-specific behavior via `IS_TACC` and `IS_DESIGNSAFE` flags — controls allocation checks, uid/gid resolution, and feature availability per deployment
- DesignSafe only: project NFS mounts fetched at spawn time via the projects API (`get_ds_projects`)
- DesignSafe only: MATLAB and LSDYNA license injection into container environment (`get_licenses`)
- DesignSafe only: `MLM_LICENSE_FILE` env variable set at spawn
### 🔧 Modified
- Removed dead/commented-out code, converted all `.format()` calls to f-strings, removed stale TODO/NOTE comments

## [3.1.6] (May 8, 2026)
### 🚀 Added
- Updated metadata calls to be more robust
### 🔧 Modified
- Update to allocation checks

## [3.1.3] (2025)
### 🚀 Added
- Checks for training accounts
- Check for expired token, and refresh automatically
- Assign restricted settings to users on restricted allocation
- Block users that have no allocation
### 🔧 Modified
- Updated to JupyterHub v3
### 🔧 Deleted
- Removed agavepy and all references to it

## [2.0.0] (2021)
### 🚀 Added
- JupyterHub now uses v3 metadata!

## [1.5.0] (2021-11-02)
### 🚀 Added
- v3 authentication for JupyterHub
- Environment variables at startup
- Initial commit to repo


[3.1.3]: https://github.com/scinco-project/jhub/releases/tag/v3.1.3
[2.0.0]: https://github.com/scinco-project/jhub/releases/tag/v2.0.0
[1.5.0]: https://github.com/scinco-project/jhub/releases/tag/v1.5.0
