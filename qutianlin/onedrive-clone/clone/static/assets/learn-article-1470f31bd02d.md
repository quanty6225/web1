---
layout: Conceptual
title: Data retention, deletion, and destruction in Microsoft 365 - Microsoft Service Assurance | Microsoft Learn
canonicalUrl: https://learn.microsoft.com/en-us/compliance/assurance/assurance-data-retention-deletion-and-destruction-overview
breadcrumb_path: /compliance/breadcrumb/toc.json
uhfHeaderId: MSDocsHeader-Compliance
feedback_system: Standard
recommendations: false
description: An overview of Microsoft policies for Microsoft 365 regarding data retention, deletion, and destruction.
ms.author: danielgluck
author: gluckd
manager: keerthak
ms.reviewer: danielgluck
audience: ITPro
ms.topic: article
ms.service: compliance
ms.subservice: compliance-assurance
search.appverid:
- MET150
ms.collection:
- MS-Compliance
- MS-Compliance-Assurance
- MCAT
f1.keywords:
- NOCSH
ms.date: 2024-06-24T00:00:00.0000000Z
locale: en-us
document_id: f2b209f4-f4bd-2542-7315-877c270362c8
document_version_independent_id: 3f0863b1-9116-ba14-f821-6d4e240c028a
updated_at: 2026-05-28T22:32:00.0000000Z
original_content_git_url: https://github.com/MicrosoftDocs/Compliance-pr/blob/live/compliance/assurance/assurance-data-retention-deletion-and-destruction-overview.md
gitcommit: https://github.com/MicrosoftDocs/Compliance-pr/blob/b0ca0b0602b3cdbb138ab2341ee6f16a81711a01/compliance/assurance/assurance-data-retention-deletion-and-destruction-overview.md
git_commit_id: b0ca0b0602b3cdbb138ab2341ee6f16a81711a01
site_name: Docs
depot_name: MSDN.compliance-docs
page_type: conceptual
toc_rel: toc.json
pdf_url_template: https://learn.microsoft.com/pdfstore/en-us/MSDN.compliance-docs/{branchName}{pdfName}
feedback_product_url: ''
feedback_help_link_type: ''
feedback_help_link_url: ''
word_count: 502
asset_id: assurance/assurance-data-retention-deletion-and-destruction-overview
moniker_range_name: 
monikers: []
item_type: Content
source_path: compliance/assurance/assurance-data-retention-deletion-and-destruction-overview.md
cmProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/1dd701e0-441f-4b0a-9806-aa47decc4e35
spProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/0a2fc935-5977-4aa6-9f55-0be03bd2acb8
platformId: 3b2e9488-4aa1-b91e-ce2c-9a4a54c531c4
---

# Data retention, deletion, and destruction in Microsoft 365 - Microsoft Service Assurance | Microsoft Learn

Microsoft has a Data Handling Standard policy for Microsoft 365 that specifies how long customer data is retained after deletion. Generally, customer data is deleted in two scenarios:

- **Active Deletion**: The tenant has an active subscription and a user or administrator deletes data, or administrators delete a user.
- **Passive Deletion**: The tenant subscription ends.

## Data retention

For each of these deletion scenarios, the following table shows the maximum data retention period, by data category and classification:

| Data Category | Data Classification | Description | Examples | Retention Period |
| --- | --- | --- | --- | --- |
| Customer Data | Customer Content | Content directly provided or created by admins and users  Includes all text, sound, video, image files, and software created and stored in Microsoft data centers when using the services in Microsoft 365 | Examples of the most commonly used Microsoft 365 applications that allow users to author data include Word, Excel, PowerPoint, Outlook, and OneNote  Customer content also includes customer-owned or provided secrets (passwords, certificates, encryption keys, storage keys) | **Active Deletion Scenario:** at most 30 days **Passive Deletion Scenario:** at most 180 days |
| Customer Data | End User Identifiable Information (EUII) | Data that identifies or could be used to identify the user of a Microsoft service. EUII doesn't contain Customer content | User name or display name (DOMAIN\UserName)  User principal name (name@domain)  User-specific IP addresses | **Active Deletion Scenario:** at most 180 days (only a tenant administrator action) **Passive Deletion Scenario:** at most 180 days |
| Personal Data  (data not included in Customer Data) | End User Pseudonymous Identifiers (EUPI) | An identifier created by Microsoft tied to the user of a Microsoft service. When combined with other information, such as a mapping table, EUPI identifies the end user  EUPI doesn't contain information uploaded or created by the customer | User GUIDs, PUIDs, or SIDs  Session IDs | **Active Deletion Scenario:** at most 30 days **Passive Deletion Scenario:** at most 180 days |

## Subscription retention

During an active subscription, a subscriber can access, extract, or delete customer data stored in Microsoft 365. If a paid subscription ends or is terminated, Microsoft retains customer data stored in Microsoft 365 in a limited-function account for 90 days to enable the subscriber to extract the data. After the 90-day retention period ends, Microsoft disables the account and deletes the customer data. No more than 180 days after expiration or termination of a subscription to Microsoft 365, Microsoft disables the account and deletes all customer data from the account. Once the maximum retention period for any data elapses, the data is rendered commercially unrecoverable.

For a free trial, your account moves into a grace status for 30 days in most countries and regions. During this grace period, you can purchase Microsoft 365. If you decide not to buy Microsoft 365, you can either cancel your trial or let the grace period expire, and your trial account information and data is deleted.

## Related links

- [Data lifecycle and records management in Microsoft Purview](/en-us/purview/manage-data-governance)
- [Data-bearing device destruction](assurance-data-bearing-device-destruction)
- [Immutability in Office 365](assurance-data-immutability)
- [Exchange Online Data Deletion](/en-us/exchange/reference/data-deletion)
- [SharePoint Online Data Deletion](/en-us/sharepoint/sharepoint-data-deletion)
- [Microsoft Defender for Endpoint and Defender for Business data storage and privacy](/en-us/defender-endpoint/data-storage-privacy)