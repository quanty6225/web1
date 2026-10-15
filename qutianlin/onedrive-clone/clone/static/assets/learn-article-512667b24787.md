---
layout: Conceptual
title: OneDrive Sync release notes - SharePoint in Microsoft 365 | Microsoft Learn
canonicalUrl: https://learn.microsoft.com/en-us/sharepoint/sync-release-notes
breadcrumb_path: /sharepoint/breadcrumb/toc.json
uhfHeaderId: MSDocsHeader-SharePoint
feedback_system: Standard
feedback_product_url: https://feedbackportal.microsoft.com/feedback/forum/06735c62-321c-ec11-b6e7-0022481f8472
recommendations: true
description: Release notes for OneDrive sync client
author: kaylangan
ms.author: kangan
manager: gacarini
ms.service: onedrive
ms.topic: release-notes
ms.date: 2026-10-09T00:00:00.0000000Z
locale: en-us
document_id: dfd91433-e4bc-7aa9-a32e-edca3183815c
document_version_independent_id: 9865c764-d912-b7db-cf91-299ad8e2a71f
updated_at: 2026-10-12T17:41:00.0000000Z
original_content_git_url: https://github.com/MicrosoftDocs/OfficeDocs-SharePoint-pr/blob/live/SharePoint/SharePointOnline/sync-release-notes.md
gitcommit: https://github.com/MicrosoftDocs/OfficeDocs-SharePoint-pr/blob/0e050893597f472dae89d3a67d35e84a7d2eff7b/SharePoint/SharePointOnline/sync-release-notes.md
git_commit_id: 0e050893597f472dae89d3a67d35e84a7d2eff7b
site_name: Docs
depot_name: office.OfficeDocs-SharePoint
page_type: conceptual
toc_rel: toc.json
pdf_url_template: https://learn.microsoft.com/pdfstore/en-us/office.OfficeDocs-SharePoint/{branchName}{pdfName}
feedback_help_link_type: ''
feedback_help_link_url: ''
word_count: 6314
asset_id: sync-release-notes
moniker_range_name: 
monikers: []
item_type: Content
source_path: SharePoint/SharePointOnline/sync-release-notes.md
cmProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/7428317a-e6c2-4461-ad3e-8a8ad3608734
spProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/e4f59707-f107-48f2-8d75-0afd91868cd7
platformId: c9aab9d3-1f55-877a-c078-2dc2cc9565a6
---

# OneDrive Sync release notes - SharePoint in Microsoft 365 | Microsoft Learn

Note

New versions roll out gradually, so if your version number is higher than the versions listed here, your device is running a newer build that this page doesn't yet reflect.

Important

If you're not getting the latest updates automatically, check that you don't have any Family Safety settings, browser extensions, or firewall rules that are blocking access to OneDrive's "oneclient.sfx.ms" and "g.live.com" domains.

Important

The OneDrive sync app requires Windows 10 22H2 or Windows 11 to receive updates. After August 15, 2026, devices running earlier versions of Windows 10 will remain on their currently installed version and will not receive new releases listed on this page. For details, see [OneDrive system requirements](https://support.microsoft.com/onedrive/onedrive-system-requirements).

# [Windows](#tab/windows)
## Current Version

| Ring | Released | Rolling Out |
| --- | --- | --- |
| Production | 26.178.0913.0007 ([amd64](https://go.microsoft.com/fwlink/?linkid=844652) | [arm64](https://go.microsoft.com/fwlink/?linkid=2359340)) | 26.183.0920.0005 ([amd64](https://go.microsoft.com/fwlink/?linkid=860984) | [arm64](https://go.microsoft.com/fwlink/?linkid=2359137)) |
| Deferred | 26.123.0628.0001 ([amd64](https://go.microsoft.com/fwlink/?linkid=860987) | [arm64](https://go.microsoft.com/fwlink/?linkid=2359341)) | 26.189.0928.0005 *Target Date: Nov 12, 2026* |

**What's New**

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Copy links from Activity Center:** Users can now copy a link to a file directly from the per-item menu for recently synced files in the OneDrive Activity Center. (Version 26.150.0804.0010)
- **Browse your photos in OneDrive:** OneDrive now brings the photos experience from OneDrive on the web and mobile to your desktop, so you can browse, search, and organize photos from your OneDrive and your PC in one place. Available for personal Microsoft accounts. Select **View photos** in the OneDrive activity center to open it. [Learn more](https://support.microsoft.com/onedrive/windows/browse-your-photos-on-windows) (Version 26.123.0628.0001)
- **Improved max path handling for OneDrive shortcuts:** OneDrive now uses the correct root path when checking Folder Shortcuts against the maximum path length, so fewer files are incorrectly flagged as exceeding the limit. (Version 26.119.0622.0003)
- **Clearer sync status messages:** OneDrive sync status messages in File Explorer, the Windows notification area, and the OneDrive Activity Center are now clearer and more consistent. We removed outdated status strings and refreshed key states, so "Your files are synced" and "Up to date" now read "Backed up and synced." (Version 26.074.0420.0001)
- **Move folders to OneDrive from File Explorer:** Right-click any folder in File Explorer to move it directly to OneDrive, making it easier to back up and sync local folders. (Version 26.045.0308.0003)

## Windows Production Ring

#### 26.183.0920.0005 (October 9, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.178.0913.0007 (October 9, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.178.0913.0006 (October 2, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.173.0906.0008 (September 25, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.168.0830.0006 (September 18, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.163.0823.0004 (September 11, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.158.0816.0002 (September 4, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.153.0809.0004 (August 28, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.150.0804.0011 (August 21, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Copy links from Activity Center:** Users can now copy a link to a file directly from the per-item menu for recently synced files in the OneDrive Activity Center.
    - **Check in and check out synced files:** Users with work or school accounts can now check files in and out of SharePoint document libraries that require check-out. When you check out a file, its synced copy becomes editable locally instead of read-only, and Check In and Check Out commands are available from the right-click menu in File Explorer. Checking a file back in restores the read-only state.

#### 26.145.0728.0011 (August 14, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.139.0720.0007 (August 7, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Self-service file exclusions:** Users with work or school accounts can now exclude specific files from syncing to OneDrive or SharePoint. Administrators can hide these controls with the DisableChangesToODIgnoreList policy to keep exclusions organization-managed.
    - **Control the default exclusion list:** The new DisableDefaultODIgnoreList policy lets administrators opt out of Microsoft's built-in default exclusion list, which is expanding to include more file types over time.

#### 26.134.0713.0007 (July 31, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Exclude specific folders from syncing:** Administrators can use a new Group Policy setting to keep folders with specific names on the device rather than uploading them to OneDrive or SharePoint. Existing synced content is not affected.

#### 26.129.0706.0004 (July 24, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.123.0628.0001 (July 17, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Browse your photos in OneDrive:** OneDrive now brings the photos experience from OneDrive on the web and mobile to your desktop, so you can browse, search, and organize photos from your OneDrive and your PC in one place. Available for personal Microsoft accounts. Select **View photos** in the OneDrive activity center to open it. [Learn more](https://support.microsoft.com/onedrive/windows/browse-your-photos-on-windows)

#### 26.119.0622.0003 (July 10, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Improved max path handling for OneDrive shortcuts:** OneDrive now uses the correct root path when checking Folder Shortcuts against the maximum path length, so fewer files are incorrectly flagged as exceeding the limit.

#### 26.113.0614.0004 (July 3, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.108.0607.0002 (June 26, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.106.0603.0003 (June 19, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.098.0524.0004 (June 12, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.095.0519.0003 (June 5, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.088.0510.0004 (May 29, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.084.0504.0007 (May 26, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.078.0426.0002 (May 15, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Clearer sync status messages:** OneDrive sync status messages in File Explorer, the Windows notification area, and the OneDrive Activity Center are now clearer and more consistent. We removed outdated status strings and refreshed key states, so "Your files are synced" and "Up to date" now read "Backed up and synced."

#### 26.070.0414.0001 (May 1, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.063.0405.0002 (April 24, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.062.0402.0002 (April 17, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.055.0323.0004 (April 10, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.051.0316.0004 (April 4, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.045.0308.0003 (March 27, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Move folders to OneDrive from File Explorer:** Right-click any folder in File Explorer to move it directly to OneDrive, making it easier to back up and sync local folders.

#### 26.040.0301.0001 (March 20, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.035.0222.0002 (March 13, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.032.0217.0003 (March 6, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Improved First Run Experience:** The OneDrive first-run setup experience has been rebuilt with a modern, streamlined interface for faster and simpler account configuration.
    - **Custom OneDrive folder name:** Administrators can now set a custom name for the local OneDrive sync folder on users' computers, replacing the default "OneDrive - {organization name}" convention. Shortening the folder name increases available path length for nested files and folders. [Learn more](use-group-policy#set-a-custom-name-for-the-onedrive-folder)

#### 26.026.0209.0004 (February 27, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.022.0203.0006 (February 20, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- Folders that contain only content excluded from sync now remain on disk as local-only when deleted from the cloud.

#### 26.017.0126.0002 (February 13, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.012.0119.0002 (February 6, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.007.0112.0002 (January 30, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.002.0105.0001 (January 23, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Mark of the Web for Outlook attachments:** Email attachments saved to OneDrive from Outlook now include the Mark of the Web (MOTW) security tag, ensuring Windows security features like Protected View apply when these files are opened.

#### 25.243.1211.0001 (January 19, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.238.1204.0001 (January 12, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.224.1116.0003 (January 5, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

2025 releases

#### 25.222.1112.0002 (December 9, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.216.1104.0002 (December 3, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.209.1026.0002 (November 17, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.206.1021.0003 (November 10, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.199.1012.0002 (November 3, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **OneDrive Sync Health Dashboard for Government Clouds:** The OneDrive Sync health dashboard now supports GCC, GCC High, and DoD environments, enabling administrators to proactively monitor sync health, identify issues, and streamline support operations.

#### 25.194.1005.0003 (October 27, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Copilot Actions in File Explorer and OneDrive Activity Center:** Users with a work or school account and a Microsoft 365 Copilot license can now use Copilot in File Explorer and OneDrive Activity Center to summarize documents, generate FAQs, compare files, or get answers about their files saved in OneDrive.

#### 25.189.0928.0002 (October 20, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **SharePoint Server Subscription Edition Version 23H2 Support with OIDC Authentication:** OneDrive Sync now supports SharePoint Server Subscription Edition Version 23H2 with OIDC authentication using Entra ID, enabling modern authentication for on-premises SharePoint environments.

#### 25.184.0921.0004 (October 13, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.179.0914.0003 (October 6, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.174.0907.0003 (September 29, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Refreshed OneDrive Icon**: The updated OneDrive icon introduces a cleaner, more modern look across all devices and apps.

#### 25.170.0901.0003 (September 19, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Improved Folder Backup Opt-Out Experience:** The PC Folder Backup (Known Folder Move) opt-out process is now more intuitive, letting users choose whether to keep files in OneDrive or move them back to their PC for greater clarity and control.

#### 25.164.0824.0003 (September 12, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **LocalNetworkAccess Support:** Chromium v142+ requires browsers to prompt users or admins for access to OneDrive and SharePoint URLs to enable offline mode. For per-machine installations, OneDrive Sync automatically applies the required permissions and policies for existing users in Chrome and Edge. For per-user installations, OneDrive Sync prompts users via a notification to enable these permissions. Available for work or school accounts.

#### 25.159.0817.0003 (September 5, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.155.0811.0002 (August 29, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.149.0803.0003 (August 22, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **OneDrive offline mode process update:** On Windows, the process for offline mode is now called Microsoft OneDrive Sync Service (OneDrive.Sync.Service.exe), replacing Microsoft SharePoint (Microsoft.SharePoint.exe). The icon changed from SharePoint to OneDrive for improved clarity.

#### 25.140.0720.0001 (August 8, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.137.0715.0001 (July 31, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.130.0706.0004 (July 25, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Copilot Actions in File Explorer:** Users with Microsoft 365 Personal, Family, or Premium accounts can now use Copilot in File Explorer to summarize documents, generate FAQs, compare files, or get answers about their files saved in OneDrive.

#### 25.127.0701.0005 (July 18, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.122.0624.0003 (July 11, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.115.0615.0002 (July 7, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.110.0608.0001 (June 30, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.105.0601.0002 (June 23, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.095.0518.0002 (June 9, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.091.0512.0001 (June 3, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.085.0504.0002 (May 26, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.080.0427.0003 (May 19, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.075.0420.0002 (May 12, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.070.0413.0001 (May 5, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.065.0406.0002 (April 25, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.060.0330.0003 (April 18, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.056.0324.0003 (April 14, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.051.0317.0003 (March 29, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.046.0310.0005 (March 21, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.041.0303.0002 (March 17, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.035.0223.0003 (March 7, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.031.0217.0003 (February 28, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.025.0209.0001 (February 20, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.020.0202.0001 (February 14, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Unlicensed OneDrive accounts:** OneDrive Sync now shows a warning when a user does not have a license assigned. Accounts start in read-only mode and then they will be archived. [Learn more](unlicensed-onedrive-accounts)

## Windows Deferred Ring

#### 26.189.0928.0005 (Target Date: Nov 12, 2026)

- This build is planned for the Deferred ring.

#### 26.123.0628.0001 (October 6, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Improved max path handling for OneDrive shortcuts:** OneDrive now uses the correct root path when checking Folder Shortcuts against the maximum path length, so fewer files are incorrectly flagged as exceeding the limit.

#### 26.078.0426.0002 (August 5, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Clearer sync status messages:** OneDrive sync status messages in File Explorer, the Windows notification area, and the OneDrive Activity Center are now clearer and more consistent. We removed outdated status strings and refreshed key states, so "Your files are synced" and "Up to date" now read "Backed up and synced."
- **Move folders to OneDrive from File Explorer:** Right-click any folder in File Explorer to move it directly to OneDrive, making it easier to back up and sync local folders.

#### 26.040.0301.0001 (June 1, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Improved First Run Experience:** The OneDrive first-run setup experience has been rebuilt with a modern, streamlined interface for faster and simpler account configuration.
- **Custom OneDrive folder name:** Administrators can now set a custom name for the local OneDrive sync folder on users' computers, replacing the default "OneDrive - {organization name}" convention. Shortening the folder name increases available path length for nested files and folders. [Learn more](use-group-policy#set-a-custom-name-for-the-onedrive-folder)
- **Mark of the Web for Outlook attachments:** Email attachments saved to OneDrive from Outlook now include the Mark of the Web (MOTW) security tag, ensuring Windows security features like Protected View apply when these files are opened.

#### 25.224.1116.0003 (March 24, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **OneDrive Sync Health Dashboard for Government Clouds:** The OneDrive Sync health dashboard now supports GCC, GCC High, and DoD environments, enabling administrators to proactively monitor sync health, identify issues, and streamline support operations.
- **Copilot Actions in File Explorer and OneDrive Activity Center:** Users with a work or school account and a Microsoft 365 Copilot license can now use Copilot in File Explorer and OneDrive Activity Center to summarize documents, generate FAQs, compare files, or get answers about their files saved in OneDrive.
- **SharePoint Server Subscription Edition Version 23H2 Support with OIDC Authentication:** OneDrive Sync now supports SharePoint Server Subscription Edition Version 23H2 with OIDC authentication using Entra ID, enabling modern authentication for on-premises SharePoint environments.

#### 25.179.0914.0003 (January 20, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Refreshed OneDrive Icon**: The updated OneDrive icon introduces a cleaner, more modern look across all devices and apps.
- **Improved Folder Backup Opt-Out Experience:** The PC Folder Backup (Known Folder Move) opt-out process is now more intuitive, letting users choose whether to keep files in OneDrive or move them back to their PC for greater clarity and control.
- **LocalNetworkAccess Support:** Chromium v142+ requires browsers to prompt users or admins for access to OneDrive and SharePoint URLs to enable offline mode. For per-machine installations, OneDrive Sync automatically applies the required permissions and policies for existing users in Chrome and Edge. For per-user installations, OneDrive Sync prompts users via a notification to enable these permissions. Available for work or school accounts.
- **OneDrive offline mode process update:** On Windows, the process for offline mode is now called Microsoft OneDrive Sync Service (OneDrive.Sync.Service.exe), replacing Microsoft SharePoint (Microsoft.SharePoint.exe). The icon changed from SharePoint to OneDrive for improved clarity.

#### 25.137.0715.0004 (October 13, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Copilot Actions in File Explorer:** Users with Microsoft 365 Personal, Family, or Premium accounts can now use Copilot in File Explorer to summarize documents, generate FAQs, compare files, or get answers about their files saved in OneDrive.

#### 25.095.0518.0002 (August 18, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.056.0324.0003 (June 9, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Unlicensed OneDrive accounts:** OneDrive Sync now shows a warning when a user does not have a license assigned. Accounts start in read-only mode and then they will be archived. [Learn more](unlicensed-onedrive-accounts)

#### 25.005.0112.0003 (April 10, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Improved experience when adding a Folder Shortcut to an already syncing folder:** Users will be able to directly replace their existing syncing locations with the new Folder Shortcut.

# [macOS](#tab/macos)
## Current Version

| Ring | Released | Rolling Out |
| --- | --- | --- |
| Production | 26.173.0906.0008 ([universal](https://go.microsoft.com/fwlink/?linkid=823060)) |  |
| Deferred | 26.123.0628.0001 ([universal](https://go.microsoft.com/fwlink/?linkid=861009)) | 26.189.0928.0005 *Target Date: Nov 12, 2026* |

**Download:**[Standalone](https://go.microsoft.com/fwlink/?linkid=823060) | [Mac App Store](https://go.microsoft.com/fwlink/p/?LinkId=248255)

**What's New**

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Manage login item registration via command line:** Administrators can register or unregister the OneDrive login item using command-line arguments, enabling programmatic control over auto-start behavior on managed devices. [Learn more](deploy-and-configure-on-macos#manage-login-item-registration-via-command-line) (Version 26.032.0217.0003)
- **Redesigned Activity Center:** The Activity Center has been rebuilt in SwiftUI with a streamlined interface showing sync status, a compact activity feed with thumbnail previews, and one-click access to errors. On macOS 26 and later, it supports Liquid Glass. [Learn more](https://techcommunity.microsoft.com/blog/onedriveblog/onedrive-on-mac-gets-liquid-glass-with-an-all-new-activity-center/4495501) (Version 26.017.0126.0002)
- **Copilot Actions in Finder and OneDrive Activity Center:** Users with a Microsoft 365 Copilot license, or a Microsoft 365 Personal, Family, or Premium subscription, can now use Copilot in Finder and the OneDrive Activity Center to summarize documents, generate FAQs, compare files, or get answers about their files saved in OneDrive. (Version 26.007.0112.0002)

## macOS Production Ring

#### 26.173.0906.0008 (September 25, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.168.0830.0006 (September 18, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.163.0823.0004 (September 11, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.158.0816.0002 (September 4, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.153.0809.0004 (August 28, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.150.0804.0011 (August 21, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Check in and check out synced files:** Users with work or school accounts can now check files in and out of SharePoint document libraries that require check-out. When you check out a file, its synced copy becomes editable locally instead of read-only, and Check In and Check Out commands are available from the right-click menu in Finder. Checking a file back in restores the read-only state.

#### 26.145.0728.0011 (August 14, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.139.0720.0007 (August 7, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Self-service file exclusions:** Users with work or school accounts can now exclude specific files from syncing to OneDrive or SharePoint. Administrators can hide these controls with the DisableChangesToODIgnoreList policy to keep exclusions organization-managed.
    - **Control the default exclusion list:** The new DisableDefaultODIgnoreList policy lets administrators opt out of Microsoft's built-in default exclusion list, which is expanding to include more file types over time.

#### 26.134.0713.0007 (July 31, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Exclude specific folders from syncing:** Administrators can use the EnableODIgnoreFolders managed preference to keep folders with specific names on the device rather than uploading them to OneDrive or SharePoint. Existing synced content is not affected.

#### 26.129.0706.0004 (July 24, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.123.0628.0001 (July 17, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.119.0622.0003 (July 10, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.113.0614.0004 (July 3, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.108.0607.0002 (June 26, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.106.0603.0003 (June 19, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.098.0524.0004 (June 12, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.095.0519.0003 (June 5, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.088.0510.0004 (May 29, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.084.0504.0007 (May 26, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.078.0426.0002 (May 15, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.070.0414.0001 (May 1, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.063.0405.0002 (April 24, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.062.0402.0002 (April 17, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.055.0323.0004 (April 10, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.051.0316.0004 (April 4, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.045.0308.0003 (March 27, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.040.0301.0001 (March 20, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.035.0222.0002 (March 13, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.032.0217.0003 (March 6, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Manage login item registration via command line:** Administrators can register or unregister the OneDrive login item using command-line arguments, enabling programmatic control over auto-start behavior on managed devices. [Learn more](deploy-and-configure-on-macos#manage-login-item-registration-via-command-line)

#### 26.026.0209.0004 (February 27, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.022.0203.0006 (February 20, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- Folders that contain only content excluded from sync now remain on disk as local-only when deleted from the cloud.

#### 26.017.0126.0002 (February 13, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Redesigned Activity Center:** The Activity Center has been rebuilt in SwiftUI with a streamlined interface showing sync status, a compact activity feed with thumbnail previews, and one-click access to errors. On macOS 26 and later, it supports Liquid Glass. [Learn more](https://techcommunity.microsoft.com/blog/onedriveblog/onedrive-on-mac-gets-liquid-glass-with-an-all-new-activity-center/4495501)

#### 26.012.0119.0002 (February 6, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.007.0112.0002 (January 30, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Copilot Actions in Finder and OneDrive Activity Center:** Users with a Microsoft 365 Copilot license, or a Microsoft 365 Personal, Family, or Premium subscription, can now use Copilot in Finder and the OneDrive Activity Center to summarize documents, generate FAQs, compare files, or get answers about their files saved in OneDrive.

#### 26.002.0105.0001 (January 23, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.243.1211.0001 (January 19, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Native macOS dialogs:** OneDrive dialogs and alerts now use native macOS system controls, providing a more familiar look and feel that aligns with other macOS applications.

#### 25.238.1204.0001 (January 12, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.224.1116.0003 (January 5, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

2025 releases

#### 25.222.1112.0002 (December 9, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.216.1104.0002 (December 3, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.209.1026.0002 (November 17, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.206.1021.0003 (November 10, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.199.1012.0002 (November 3, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **OneDrive Sync Health Dashboard for Government Clouds:** The OneDrive Sync health dashboard now supports GCC, GCC High, and DoD environments, enabling administrators to proactively monitor sync health, identify issues, and streamline support operations.

#### 25.194.1005.0003 (October 27, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.189.0928.0002 (October 20, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **SharePoint Server Subscription Edition Version 23H2 Support with OIDC Authentication:** OneDrive Sync now supports SharePoint Server Subscription Edition Version 23H2 with OIDC authentication using Entra ID, enabling modern authentication for on-premises SharePoint environments.

#### 25.184.0921.0004 (October 13, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.179.0914.0003 (October 6, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.174.0907.0003 (September 29, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Refreshed OneDrive Icon**: The updated OneDrive icon introduces a cleaner, more modern look across all devices and apps.

#### 25.170.0901.0003 (September 19, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.164.0824.0003 (September 12, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.159.0817.0003 (September 5, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **OneDrive offline mode process update:** The offline mode process, visible in Activity Monitor, is now called OneDrive Sync Service, replacing Microsoft SharePoint. The icon changed from SharePoint to OneDrive for improved clarity.

#### 25.140.0720.0001 (August 8, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.137.0715.0001 (July 31, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.130.0706.0004 (July 25, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.127.0701.0005 (July 18, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Syncing files to a removable non-home volume:** OneDrive on macOS now supports selecting a removable non-home volume to store OneDrive content. [Learn more](https://techcommunity.microsoft.com/blog/onedriveblog/onedrive-for-mac-now-supports-removable-drives/4419685)

#### 25.122.0624.0003 (July 11, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.115.0615.0002 (July 7, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.110.0608.0001 (June 30, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.105.0601.0002 (June 23, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.095.0518.0002 (June 9, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.091.0512.0001 (June 3, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.085.0504.0002 (May 26, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.080.0427.0003 (May 19, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.075.0420.0002 (May 12, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.070.0413.0001 (May 5, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.065.0406.0002 (April 25, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.060.0330.0003 (April 18, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.056.0324.0003 (April 14, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- Fixed an issue causing error -99 for users upgrading to macOS 15 who were previously on macOS 14, with OneDrive syncing files on a non-home non-encrypted volume.

#### 25.051.0317.0003 (March 29, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.046.0310.0005 (March 21, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.041.0303.0002 (March 17, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.035.0223.0003 (March 7, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Syncing files to a non-removable non-home volume:** OneDrive on macOS now supports selecting a **non-removable** non-home volume to store OneDrive content. [Learn more](https://techcommunity.microsoft.com/blog/onedriveblog/improved-filename-and-external-drive-support-for-onedrive-mac/4372026)

#### 25.031.0217.0003 (February 28, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.025.0209.0001 (February 20, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.020.0202.0001 (February 14, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Unlicensed OneDrive accounts:** OneDrive Sync now shows a warning when a user does not have a license assigned. Accounts start in read-only mode and then they will be archived. [Learn more](unlicensed-onedrive-accounts)

## macOS Deferred Ring

#### 26.189.0928.0005 (Target Date: Nov 12, 2026)

- This build is planned for the Deferred ring.

#### 26.123.0628.0001 (October 6, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.078.0426.0002 (August 5, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 26.040.0301.0001 (June 1, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Manage login item registration via command line:** Administrators can register or unregister the OneDrive login item using command-line arguments, enabling programmatic control over auto-start behavior on managed devices. [Learn more](deploy-and-configure-on-macos#manage-login-item-registration-via-command-line)
- **Redesigned Activity Center:** The Activity Center has been rebuilt in SwiftUI with a streamlined interface showing sync status, a compact activity feed with thumbnail previews, and one-click access to errors. On macOS 26 and later, it supports Liquid Glass. [Learn more](https://techcommunity.microsoft.com/blog/onedriveblog/onedrive-on-mac-gets-liquid-glass-with-an-all-new-activity-center/4495501)
- **Copilot Actions in Finder and OneDrive Activity Center:** Users with a Microsoft 365 Copilot license, or a Microsoft 365 Personal, Family, or Premium subscription, can now use Copilot in Finder and the OneDrive Activity Center to summarize documents, generate FAQs, compare files, or get answers about their files saved in OneDrive.
- **Native macOS dialogs:** OneDrive dialogs and alerts now use native macOS system controls, providing a more familiar look and feel that aligns with other macOS applications.

#### 25.224.1116.0003 (March 24, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **OneDrive Sync Health Dashboard for Government Clouds:** The OneDrive Sync health dashboard now supports GCC, GCC High, and DoD environments, enabling administrators to proactively monitor sync health, identify issues, and streamline support operations.
- **SharePoint Server Subscription Edition Version 23H2 Support with OIDC Authentication:** OneDrive Sync now supports SharePoint Server Subscription Edition Version 23H2 with OIDC authentication using Entra ID, enabling modern authentication for on-premises SharePoint environments.

#### 25.179.0914.0003 (January 20, 2026)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- **Refreshed OneDrive Icon**: The updated OneDrive icon introduces a cleaner, more modern look across all devices and apps.
- **OneDrive offline mode process update:** The offline mode process, visible in Activity Monitor, is now called OneDrive Sync Service, replacing Microsoft SharePoint. The icon changed from SharePoint to OneDrive for improved clarity.

#### 25.137.0715.0004 (October 13, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.095.0518.0002 (August 18, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.

#### 25.056.0324.0003 (June 9, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Unlicensed OneDrive accounts:** OneDrive Sync now shows a warning when a user does not have a license assigned. Accounts start in read-only mode and then they will be archived. [Learn more](unlicensed-onedrive-accounts)
    - **Syncing files to a non-home volume:** OneDrive on macOS now supports selecting a non-home volume to store OneDrive content. [Learn more](https://techcommunity.microsoft.com/blog/onedriveblog/improved-filename-and-external-drive-support-for-onedrive-mac/4372026)

#### 25.005.0112.0003 (April 10, 2025)

- We resolved product issues to improve the reliability and performance of the OneDrive sync app.
- New features gradually rolling out:
    - **Improved experience when adding a Folder Shortcut to an already syncing folder:** Users will be able to directly replace their existing syncing locations with the new Folder Shortcut.

---