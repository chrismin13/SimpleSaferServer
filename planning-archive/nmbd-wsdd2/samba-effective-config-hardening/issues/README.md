# Samba Effective Config Hardening Issues

These local issue files break the PRD into dependency-ordered AFK slices. They harden the
Samba discovery/config redesign by making Unmanaged Samba Share detection use Samba's Effective
Samba Config, tightening required `smbd` failure handling, completing rollback behavior, and fixing
uninstall/manual-install edge cases before submission.

## Breakdown

1. **Detect Unmanaged Samba Shares From Effective Config**
   - **Type**: AFK
   - **Blocked by**: None
   - **User stories covered**: 1, 3, 4, 5, 6, 19, 20, 21
   - **File**: [01-detect-unmanaged-samba-shares-from-effective-config.md](01-detect-unmanaged-samba-shares-from-effective-config.md)

2. **Use Effective Unmanaged-Share Detection In SMB Writes**
   - **Type**: AFK
   - **Blocked by**: Issue 1
   - **User stories covered**: 2, 6, 7, 8, 19, 20
   - **File**: [02-use-effective-unmanaged-share-detection-in-smb-writes.md](02-use-effective-unmanaged-share-detection-in-smb-writes.md)

3. **Surface Unmanaged-Share Verification State In The UI**
   - **Type**: AFK
   - **Blocked by**: Issue 1
   - **User stories covered**: 3, 4, 11
   - **File**: [03-surface-unmanaged-share-verification-state-in-ui.md](03-surface-unmanaged-share-verification-state-in-ui.md)

4. **Complete SMB Share Publish Rollback**
   - **Type**: AFK
   - **Blocked by**: None
   - **User stories covered**: 9, 10, 11, 22
   - **File**: [04-complete-smb-share-publish-rollback.md](04-complete-smb-share-publish-rollback.md)

5. **Honor Required smbd Failure In Installer**
   - **Type**: AFK
   - **Blocked by**: None
   - **User stories covered**: 12, 13, 14, 23
   - **File**: [05-honor-required-smbd-failure-in-installer.md](05-honor-required-smbd-failure-in-installer.md)

6. **Clean Owned Samba Files On Uninstall Independently**
   - **Type**: AFK
   - **Blocked by**: None
   - **User stories covered**: 15, 16, 17, 24
   - **File**: [06-clean-owned-samba-files-on-uninstall-independently.md](06-clean-owned-samba-files-on-uninstall-independently.md)

7. **Repair Manual Install Documentation**
   - **Type**: AFK
   - **Blocked by**: None
   - **User stories covered**: 18, 25
   - **File**: [07-repair-manual-install-documentation.md](07-repair-manual-install-documentation.md)
