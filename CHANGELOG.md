# Changelog
All notable changes to this project will be documented in this file

## [26Q3.4] (Oct 28, 2026)
### 🔧 Modified
- Convert spawner.cpu_limit to int string for environment variables

## [26Q3.3] (Oct 27, 2026)
### 🐛 Bug fix
- Fix spawner.configs check to use hasattr

## [26Q3.2] (Oct 22, 2026)
### 🐛 Bug fix
- Check is spawner.configs exists and attempt to refetch

## [26Q3.1] (Oct 21, 2026)
### 🔧 Modified
- Set default deployment target

## [26Q3.0] (Oct 20, 2026)
### 🚀 Added
- Improved modularization of JupyterHub by implementing deployment hooks
- Added symlink enabling capabilities
- Converted from TAS to LDAP for user accounts, projects, and access
  - User account (uid, gid, home directory) now read from the LDAP `People` entry (`retrieve_full_ldap_account`, `get_ldap_data`), replacing the TAS users API
  - Allocation/project membership now read from LDAP `Groups`, replacing the TAS projects API; users with no groups are rejected with a 403
  - Supplemental GIDs set on the spawner from the user's LDAP group DNs
  - Restricted project detection now uses the LDAP group DN; default `RESTRICTED_ID` changed from `66657` to `G-827652`
  - Restricted users are blocked from DesignSafe JupyterHub 
  - Requires `LDAP_PASS`; `TAS_ROLE_ACCT`/`TAS_ROLE_PASS` are no longer used
- Retries on metadata calls (`get_tenant_configs`, `get_user_configs`) via `tenacity`, configurable with `RETRY_ATTEMPTS` and `RETRY_WAIT`
- Per-deployment defaults for `TAPIS_BASE_URL`, `PORTALS_BASE_URL`, and Jupyter home directory
- `Dockerfile.uv` for building with uv
- Type hints on function signatures
- Updated JupyterHub from 3.0.0 to 6.0.1
### 🔧 Modified
- More refactoring, moving to pure functions
- Better error handling and debugging
- `INSTANCE`, `TENANT`, and `TAPIS_SERVICE_TOKEN` are now required at startup
- Spawn page template updated for the new JupyterHub version; template path moved to `/srv/jupyterhub/custom_templates`
- Converted remaining `.format()`/`%` strings to f-strings and removed commented-out logging
### 🔧 Deleted
- Removed `IS_TACC`/`IS_DESIGNSAFE` flags in favor of `DEPLOYMENT_TARGET`
- Removed TAS API calls

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
