# Samba Discovery and Config Ownership Issues

These local issue files break the PRD into dependency-ordered AFK slices. They move
SimpleSaferServer's Samba ownership boundary to SSS-owned include files, add optional modern Windows
discovery through `wsdd2`, and update install, UI, uninstall, and docs behavior.

## Breakdown

1. **Establish SSS-owned Samba layout**
   - **Type**: AFK
   - **Blocked by**: None
   - **User stories covered**: 21, 22, 25, 26, 31, 32, 33, 34, 35
   - **File**: [01-establish-sss-owned-samba-layout.md](01-establish-sss-owned-samba-layout.md)

2. **Move managed shares to the SSS shares file**
   - **Type**: AFK
   - **Blocked by**: Issue 1
   - **User stories covered**: 17, 18, 19, 20, 23, 24, 36, 37
   - **File**: [02-move-managed-shares-to-sss-shares-file.md](02-move-managed-shares-to-sss-shares-file.md)

3. **Install and report discovery services**
   - **Type**: AFK
   - **Blocked by**: Issue 1
   - **User stories covered**: 1, 2, 3, 4, 5, 6, 7, 8
   - **File**: [03-install-and-report-discovery-services.md](03-install-and-report-discovery-services.md)

4. **Track three file-sharing services in the Web UI**
   - **Type**: AFK
   - **Blocked by**: Issues 2 and 3
   - **User stories covered**: 9, 10, 11, 12, 13, 14, 15, 16
   - **File**: [04-track-three-file-sharing-services-in-web-ui.md](04-track-three-file-sharing-services-in-web-ui.md)

5. **Clean up SSS-owned Samba config on uninstall**
   - **Type**: AFK
   - **Blocked by**: Issue 1
   - **User stories covered**: 27, 28, 29, 30
   - **File**: [05-clean-up-sss-owned-samba-config-on-uninstall.md](05-clean-up-sss-owned-samba-config-on-uninstall.md)

6. **Document Samba ownership and discovery**
   - **Type**: AFK
   - **Blocked by**: Issues 1, 2, 3, 4, and 5
   - **User stories covered**: 38, 39, 40
   - **File**: [06-document-samba-ownership-and-discovery.md](06-document-samba-ownership-and-discovery.md)
